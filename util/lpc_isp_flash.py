#!/usr/bin/env python3
"""Write a firmware image to an NXP LPC11U1x over UART ISP and verify it.

This is the writing counterpart of lpc_isp_backup.py: same wiring, same way
into ISP mode. Back the chip up with that tool first; the backup it makes is
also what you flash with this tool to go back to the stock firmware.

It refuses images with a bad vector checksum or a code read protection word,
so the chip stays reachable over ISP after flashing.

The order of work keeps a reset or a dropped link recoverable at any point:
  1. identify the chip (the part id must be a known one, or pass --any-part)
  2. erase all flash. With no valid user code, the boot ROM enters ISP on
     every reset, so from here on a reset needs no ISP bridge.
  3. write and read back every 1 KiB chunk, leaving the first chunk (the one
     with the vector table) for last, so the chip only has valid code once
     everything else is in place
  4. read back the whole flash and compare it with the image
If the link drops, the tool re-synchronises (tap RST to GND if it asks you to),
then erases and rewrites the sector it was working on.

usage: lpc_isp_flash.py PORT IMAGE.bin [--wait S] [--baud N (19200)] [--xtal KHZ] [--dry-run] [--resume] [--sectors N,..]
restore the stock firmware:  lpc_isp_flash.py PORT orbweaver_stock_flash.bin
needs: pip install pyserial
"""

import argparse
import binascii
import hashlib
import os
import struct
import sys
import time

import serial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lpc_isp_backup import CRP_PATTERNS, Isp  # noqa: E402

RETURN_CODES = {
    0: "CMD_SUCCESS",
    1: "INVALID_COMMAND",
    2: "SRC_ADDR_ERROR",
    3: "DST_ADDR_ERROR",
    4: "SRC_ADDR_NOT_MAPPED",
    5: "DST_ADDR_NOT_MAPPED",
    6: "COUNT_ERROR",
    7: "INVALID_SECTOR",
    8: "SECTOR_NOT_BLANK",
    9: "SECTOR_NOT_PREPARED_FOR_WRITE_OPERATION",
    10: "COMPARE_ERROR",
    11: "BUSY",
    12: "PARAM_ERROR",
    13: "ADDR_ERROR",
    14: "ADDR_NOT_MAPPED",
    15: "CMD_LOCKED",
    16: "INVALID_CODE",
    17: "INVALID_BAUD_RATE",
    18: "INVALID_STOP_BIT",
    19: "CODE_READ_PROTECTION_ENABLED",
}

# part id -> (name, flash bytes). Only ids seen on real hardware are listed.
KNOWN_PARTS = {
    0x297A802B: ("LPC11U13FBD48/201", 24 * 1024),
}

SECTOR = 4096  # LPC11U1x flash sector
CHUNK = 1024  # RAM -> flash copy size; must be 256, 512, 1024 or 4096
READ_PIECE = 900  # R replies are checksummed every 20 UU lines (900 bytes)
UU_BLOCK = 900  # W data is checksummed every 20 UU lines as well
RAM_BUFFER = 0x10000400  # clear of the ISP's own RAM (0x1000017C-0x1000025B) and its stack at the top
UNLOCK_CODE = 23130
RECOVER_WAIT = 90  # seconds to wait for the chip after a dropped link
SECTOR_ATTEMPTS = 6
CHUNK_ATTEMPTS = 8


class LinkLost(Exception):
    """The boot ROM stopped answering sensibly (reset, noise, loose wire)."""


class IspError(Exception):
    def __init__(self, cmd, code):
        super().__init__(f"{cmd!r} answered {code} {RETURN_CODES.get(code, '?')}")
        self.code = code


class Mismatch(Exception):
    pass


def check_image(img, flash_size):
    """Reasons not to flash this image (empty list = fine)."""
    if len(img) < 0x300:
        return [f"only {len(img)} bytes: too small to be a firmware image for this chip"]
    problems = []
    if len(img) > flash_size:
        problems.append(f"{len(img)} bytes does not fit in {flash_size} bytes of flash")
    words = struct.unpack_from("<8I", img, 0)
    if sum(words) & 0xFFFFFFFF:
        want = (-sum(words[:7])) & 0xFFFFFFFF
        problems.append(f"vector checksum is wrong (word 7 = 0x{words[7]:08X}, needs 0x{want:08X}): the boot ROM would not run it")
    sp, reset = words[0], words[1]
    if not 0x10000000 < sp <= 0x10008000:
        problems.append(f"initial stack pointer 0x{sp:08X} is not in SRAM")
    if not (reset & 1 and (reset & ~1) < len(img)):
        problems.append(f"reset vector 0x{reset:08X} is not a Thumb address inside the image")
    crp = struct.unpack_from("<I", img, 0x2FC)[0]
    if crp in CRP_PATTERNS:
        problems.append(f"word at 0x2FC is 0x{crp:08X} ({CRP_PATTERNS[crp]}): it would lock the chip")
    return problems


def uu_lines(block):
    return b"".join(binascii.b2a_uu(block[i:i + 45], backtick=True).rstrip(b"\n") + b"\r\n" for i in range(0, len(block), 45))


class Writer(Isp):
    def __init__(self, port, baud, xtal):
        super().__init__(port, baud)
        self.xtal = xtal
        self.erased = False

    def code_reply(self, text, timeout=1.0):
        self.s.reset_input_buffer()
        self.send(text)
        for _ in range(2):
            reply = self.line(timeout)
            if reply.isdigit():
                return int(reply)
        raise LinkLost(f"no answer to {text!r}")

    def run(self, text, timeout=1.0):
        code = self.code_reply(text, timeout)
        if code != 0:
            raise IspError(text, code)

    def unlock(self):
        self.run(f"U {UNLOCK_CODE}")

    def erase(self, first, last):
        self.run(f"P {first} {last}")
        self.run(f"E {first} {last}", timeout=10.0)
        code = self.code_reply(f"I {first} {last}", timeout=5.0)
        if code == 8:
            offset, content = self.line(), self.line()
            raise Mismatch(f"sectors {first}-{last} not blank after erase (offset {offset}, word {content})")
        if code != 0:
            raise IspError(f"I {first} {last}", code)

    def write_ram(self, addr, data):
        self.run(f"W {addr} {len(data)}")
        for off in range(0, len(data), UU_BLOCK):
            block = data[off:off + UU_BLOCK]
            payload = uu_lines(block) + f"{sum(block)}\r\n".encode("ascii")
            kicked = False
            for _ in range(5):
                self.write(payload)
                reply = self.line(3.0)
                if reply == "OK":
                    break
                if reply == "" and len(block) < UU_BLOCK and not kicked:
                    # A garbled line in the last, short block leaves the ROM a few bytes
                    # short and reading our checksum as data. One more line of zeros
                    # completes its count; the checksum after it fails, so the ROM asks
                    # for the block again and the loop resends it.
                    kicked = True
                    self.write(uu_lines(b"\0" * 45) + b"0\r\n")
                    reply = self.line(3.0)
                if reply != "RESEND":
                    raise LinkLost(f"W data at 0x{addr + off:08X}: got {reply!r} instead of OK")
            else:
                # The ROM is waiting for this block again. Fill the rest of the W with
                # zeros (checksum 0) so it goes back to command mode, then let the
                # caller redo the sector.
                for rest in range(off, len(data), UU_BLOCK):
                    self.write(uu_lines(b"\0" * min(UU_BLOCK, len(data) - rest)) + b"0\r\n")
                    self.line(3.0)
                raise LinkLost(f"W data at 0x{addr + off:08X}: checksum failed 5 times")

    def ram_selftest(self):
        """Write a pattern to the RAM buffer and read it back: proves the W
        protocol works on this chip before anything is erased."""
        pattern = bytes((i * 37 + 11) & 0xFF for i in range(CHUNK))
        self.write_ram(RAM_BUFFER, pattern)
        if self.read(RAM_BUFFER, CHUNK) != pattern:
            raise Mismatch("RAM write test read back different data")

    def copy(self, flash_addr, count):
        sector = flash_addr // SECTOR
        self.run(f"P {sector} {sector}")
        self.run(f"C {flash_addr} {RAM_BUFFER} {count}", timeout=3.0)

    def read(self, addr, count):
        out = b""
        for off in range(0, count, READ_PIECE):
            n = min(READ_PIECE, count - off)
            self.s.reset_input_buffer()
            try:
                code, data = self.read_memory(addr + off, n)
            except RuntimeError as e:
                raise LinkLost(str(e))
            if code == -1:
                raise LinkLost(f"no answer to R at 0x{addr + off:X} (got {getattr(self, 'last_reply', '')!r})")
            if code != 0:
                raise IspError(f"R {addr + off} {n}", code)
            out += data
        return out

    def recover(self, valid_code):
        """Get back into a working, unlocked ISP session after a failure."""
        how = "hold the ISP bridge and tap RST to GND" if valid_code else "tap RST to GND once"
        for _ in range(6):
            self.drain(0.3)
            for _ in range(3):  # the session is usually still there; a garbled command is no reason to resync
                try:
                    if not self.rejoin():
                        break
                    self.unlock()
                    return
                except (LinkLost, IspError):
                    pass
            print(f"\n  link lost; re-synchronising. If it does not come back within ~10 s, {how}.", flush=True)
            try:
                self.sync(self.xtal, RECOVER_WAIT)
                self.unlock()
                return
            except (LinkLost, IspError):
                continue  # dropped again straight after syncing, or the unlock was garbled
            except RuntimeError as e:
                if str(e).startswith("no 'Synchronized'"):
                    raise SystemExit(f"\ngave up: {e}\n" + self.state_note())
                continue  # reset in the middle of the handshake
        raise SystemExit("\ncould not get a stable ISP session back; check the power and serial wires.\n" + self.state_note())

    def state_note(self):
        if self.erased:
            return "The chip has no complete firmware yet; it enters ISP on any reset. Tap RST and run this again."
        return "Nothing was erased: the old firmware is still on the chip. Put it back into ISP and run this again."


BLANK = b"\xFF" * CHUNK


class NeedsErase(Exception):
    """A chunk holds something other than blank or the wanted data."""


def program_chunk(w, a, data):
    """Get chunk `a` to hold `data`, retrying link errors. Raises NeedsErase
    if the chunk was programmed with something else."""
    for attempt in range(1, CHUNK_ATTEMPTS + 1):
        try:
            if attempt > 1:
                got = w.read(a, CHUNK)  # what did the failed attempt leave behind?
                if got == data:
                    return
                if got != BLANK:
                    raise NeedsErase(f"0x{a:04X} holds a write that went wrong")
            if data != BLANK:
                w.write_ram(RAM_BUFFER, data)
                w.copy(a, CHUNK)
            got = w.read(a, CHUNK)
            if got == data:
                return
            if got != BLANK:
                bad = next(i for i in range(CHUNK) if got[i] != data[i])
                raise NeedsErase(f"read-back differs at 0x{a + bad:04X}")
        except (LinkLost, IspError, Mismatch) as e:
            print(f"\n  0x{a:04X}: {e}; retrying", flush=True)
            w.recover(valid_code=(a == 0))
    raise NeedsErase(f"0x{a:04X} kept failing")


def program_sector(w, image, s, erase_first=False):
    """Write and verify every chunk of sector s. The first chunk of sector 0
    (the vector table) goes last."""
    chunks = list(range(s * SECTOR, min((s + 1) * SECTOR, len(image)), CHUNK))
    if s == 0:
        chunks = chunks[1:] + chunks[:1]
    for attempt in range(1, SECTOR_ATTEMPTS + 1):
        try:
            if erase_first or attempt > 1:
                w.erase(s, s)
            for a in chunks:
                program_chunk(w, a, image[a:a + CHUNK])
                print(f"\r  wrote and checked 0x{a:04X}-0x{a + CHUNK - 1:04X}", end="", flush=True)
            return
        except (NeedsErase, LinkLost, IspError, Mismatch) as e:
            print(f"\n  sector {s}: {e}")
            if attempt == SECTOR_ATTEMPTS:
                raise SystemExit(f"sector {s} kept failing. " + w.state_note())
            print(f"  erasing and rewriting sector {s} (attempt {attempt + 1})", flush=True)
            if not isinstance(e, NeedsErase):
                w.recover(valid_code=(s == 0))


def read_all(w, flash_size, start=0):
    data, failures = b"", 0
    while len(data) < flash_size - start:
        try:
            data += w.read(start + len(data), min(READ_PIECE, flash_size - start - len(data)))
        except (LinkLost, IspError) as e:
            failures += 1
            print(f"\n  read-back at 0x{start + len(data):04X}: {e}", flush=True)
            if failures > 60:
                raise SystemExit("the final read-back kept failing (every chunk was already checked as it was written)")
            w.recover(valid_code=True)
    return data


def flash_image(w, img, flash_size, resume=False, only=None):
    """Erase, write and verify. Returns the final flash contents."""
    image = bytes(img) + b"\xFF" * (-len(img) % CHUNK)
    sectors = flash_size // SECTOR
    used = (len(image) + SECTOR - 1) // SECTOR
    expect = image + b"\xFF" * (flash_size - len(image))

    if only:
        # just these sectors; the rest of the flash is left as it is
        todo = sorted(set(only), key=lambda s: (s == 0, s))  # sector 0 (vector table) last
        print(f"writing only sectors {todo}; the others are not touched", flush=True)
        if 0 in todo:
            w.erased = True
        w.unlock()
        for s in todo:
            program_sector(w, expect, s, erase_first=True)
        print()
        for check in range(1, 4):
            bad = [s for s in todo if read_all(w, (s + 1) * SECTOR, s * SECTOR) != expect[s * SECTOR:(s + 1) * SECTOR]]
            if not bad:
                print(f"read back sectors {todo}: they match the image")
                return b"".join(expect[s * SECTOR:(s + 1) * SECTOR] for s in todo)
            print(f"  sectors {bad} differ from the image; rewriting them")
            for s in bad:
                program_sector(w, expect, s, erase_first=True)
        raise SystemExit(f"VERIFY FAILED in sectors {bad}. " + w.state_note())

    if resume:
        # finish an earlier run: only the sectors that do not match yet
        print("reading the flash to find the sectors still to write ...", flush=True)
        current = read_all(w, flash_size)
        todo = [s for s in range(sectors) if current[s * SECTOR:(s + 1) * SECTOR] != expect[s * SECTOR:(s + 1) * SECTOR]]
        print(f"  already correct: {[s for s in range(sectors) if s not in todo]}, to write: {todo}", flush=True)
        if 0 in todo:
            w.erased = True
        w.unlock()
        for s in sorted(todo, key=lambda s: s == 0):  # sector 0 (vector table) last
            program_sector(w, expect, s, erase_first=True)
        print()
    else:
        _erase_all_and_write(w, image, sectors, used)

    for check in range(1, 4):
        print("reading back the whole flash ...", flush=True)
        final = read_all(w, flash_size)
        bad = sorted({i // SECTOR for i in range(flash_size) if final[i] != expect[i]})
        if not bad:
            return final
        print(f"  sectors {bad} differ from the image; rewriting them")
        for s in sorted(bad, key=lambda s: s == 0):
            program_sector(w, expect, s, erase_first=True)
        print()
    raise SystemExit(f"VERIFY FAILED in sectors {bad}. " + w.state_note())


def _erase_all_and_write(w, image, sectors, used):
    for attempt in range(1, SECTOR_ATTEMPTS + 1):
        try:
            w.unlock()
            print(f"erasing sectors 0-{sectors - 1} ...", flush=True)
            w.erase(0, sectors - 1)
            w.erased = True
            break
        except (LinkLost, IspError, Mismatch) as e:
            print(f"\n  erase: {e}")
            w.erased = True  # it may have partly happened
            if attempt == SECTOR_ATTEMPTS:
                raise SystemExit("erase kept failing; nothing more was written")
            w.recover(valid_code=True)
    print("erased. Until the last step the chip has no valid code, so a reset puts it straight back into ISP.")

    # sector 0 last, and its vector table chunk last of all: the chip only gets
    # runnable code once everything else is in place
    for s in list(range(1, used)) + [0]:
        program_sector(w, image, s)
    print()


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # garbled serial text must never crash a print
        try:
            stream.reconfigure(errors="backslashreplace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("port", help="serial port, e.g. COM3 or /dev/ttyUSB0")
    ap.add_argument("image", help="raw .bin image starting at flash address 0")
    ap.add_argument("--baud", type=int, default=19200, help="19200 is slower than the backup tool's 57600 but far more reliable for writing")
    ap.add_argument("--xtal", type=int, default=12000, help="crystal frequency in kHz")
    ap.add_argument("--wait", type=int, default=0, help="keep trying for this many seconds (put the chip into ISP meanwhile)")
    ap.add_argument("--any-part", action="store_true", help="flash an LPC11U part id this tool has not seen (needs --size)")
    ap.add_argument("--size", type=int, help="flash size in bytes, with --any-part")
    ap.add_argument("--dry-run", action="store_true", help="connect, identify and check the image, but do not erase or write")
    ap.add_argument("--sectors", help="write only these 4 KiB sectors, e.g. 0 or 0,5; leave the rest as it is")
    ap.add_argument("--resume", action="store_true", help="finish an interrupted run: read the flash and rewrite only the sectors that differ")
    args = ap.parse_args(argv)

    img = open(args.image, "rb").read()
    print(f"image {args.image}: {len(img)} bytes, sha256 {hashlib.sha256(img).hexdigest()}")
    problems = check_image(img, args.size or max(n for _, n in KNOWN_PARTS.values()))
    if problems:
        print("refusing to flash this image:\n  " + "\n  ".join(problems))
        return 1

    deadline = time.time() + args.wait
    told = False
    while True:
        try:
            w = Writer(args.port, args.baud, args.xtal)
            break
        except serial.SerialException as e:
            if time.time() >= deadline:
                print(f"cannot open {args.port}: {e}\nNothing was written.")
                return 1
            if not told:
                print(f"waiting for {args.port} to appear (plug in the serial adapter)", flush=True)
                told = True
            time.sleep(1)
    if args.wait:
        print(f"waiting up to {max(0, int(deadline - time.time()))} s: put the chip into ISP now (hold the ISP bridge, tap RST)", flush=True)
    for attempt in range(1, 6):
        try:
            w.sync(args.xtal, max(5, deadline - time.time()) if attempt == 1 else 15)
            break
        except RuntimeError as e:
            if str(e).startswith("no 'Synchronized'") or attempt == 5:
                print(f"{e}\nNothing was written.")
                return 1
            print(f"  {e}; trying again", flush=True)
    print("synchronised with the boot ROM", flush=True)

    for attempt in range(1, 6):
        code, lines = w.command("J", 1)
        if code == 0 and lines and lines[0].isdigit():
            break
        if attempt == 5:
            print(f"could not read the part id ({RETURN_CODES.get(code, code)}). Nothing was written.")
            return 1
        w.recover(valid_code=True)
    part = int(lines[0])
    if part in KNOWN_PARTS:
        name, flash_size = KNOWN_PARTS[part]
    elif args.any_part and args.size:
        name, flash_size = "unknown part", args.size
    else:
        print(f"part id 0x{part:08X} is not one this tool knows; pass --any-part --size BYTES if you are sure")
        return 1
    print(f"part id 0x{part:08X} = {name}, {flash_size} bytes of flash")
    problems = check_image(img, flash_size)
    if problems:
        print("refusing to flash this image:\n  " + "\n  ".join(problems))
        return 1

    for attempt in range(1, 7):
        try:
            w.ram_selftest()
            print("RAM write test passed (write and read-back of 1 KiB in SRAM)")
            break
        except (LinkLost, IspError, Mismatch) as e:
            print(f"RAM write test: {e}")
            if attempt == 6:
                print("stopping before the erase: the flash was not touched")
                return 1
            w.recover(valid_code=True)

    if args.dry_run:
        print("dry run: chip and image look fine; nothing was erased or written")
        return 0

    only = [int(x) for x in args.sectors.split(",")] if args.sectors else None
    final = flash_image(w, img, flash_size, resume=args.resume, only=only)
    if only:
        print(f"VERIFIED: sectors {sorted(set(only))} match the image; the other sectors were left as they were")
    else:
        print(f"VERIFIED: flash matches the image ({len(img)} bytes written, rest erased)")
        print(f"flash sha256 {hashlib.sha256(final).hexdigest()}")
    print("\nDone. Disconnect the serial adapter and the 3.3 V supply, then plug in USB to run the new firmware.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
