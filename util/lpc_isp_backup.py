#!/usr/bin/env python3
"""Read-only NXP LPC11Uxx UART ISP client: identify the chip and back up its flash.

It only sends ISP commands that read: sync, A (echo off), J (part id),
K (boot code version), N (serial number) and R (read memory). There is no
unlock, erase, write or go command in here, so it cannot change the chip.

Wiring (3.3 V USB-serial adapter, never 5 V):
    adapter GND -> board GND
    adapter TX  -> board RXD (PIO0_18)
    adapter RX  -> board TXD (PIO0_19)
Enter ISP: hold ISP (PIO0_1) at GND while the MCU comes out of reset (plug in
USB, or tap RST to GND), then let go. On boot code 7.0 parts PIO0_3/USB_VBUS
must be low as well, i.e. power the board from the adapter's 3.3 V on VCC3_3
with the USB cable unplugged.

usage: lpc_isp_backup.py PORT [--out FILE] [--size BYTES] [--baud N] [--info]
needs: pip install pyserial
"""

import argparse
import hashlib
import struct
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial is missing: pip install pyserial")

RETURN_CODES = {
    0: "CMD_SUCCESS",
    1: "INVALID_COMMAND",
    2: "SRC_ADDR_ERROR",
    3: "DST_ADDR_ERROR",
    4: "SRC_ADDR_NOT_MAPPED",
    5: "DST_ADDR_NOT_MAPPED",
    6: "COUNT_ERROR",
    13: "ADDR_ERROR",
    14: "ADDR_NOT_MAPPED",
    15: "CMD_LOCKED",
    18: "PARAM_ERROR",
    19: "CODE_READ_PROTECTION_ENABLED",
}

CRP_PATTERNS = {
    0x12345678: "CRP1",
    0x87654321: "CRP2",
    0x43218765: "CRP3",
    0x4E697370: "NO_ISP",
}

CHUNK = 900  # 20 UU lines of 45 bytes; a multiple of 4 as R requires


class Isp:
    # Pause before each transmission. Without it the ROM lost bytes sent right
    # after one of its replies (it seems slow to go back to reading its 16-byte
    # receive FIFO), which showed up as unanswered commands.
    GAP = 0.01

    def __init__(self, port, baud):
        self.s = serial.Serial(port, baud, timeout=1.0)

    def write(self, data):
        time.sleep(self.GAP)
        self.s.write(data)

    def line(self, timeout=1.0):
        """One reply line. The ROM echoes input with a bare CR before its own
        answer (e.g. 'Synchronized<CR>OK<CR><LF>'), so keep the last CR-separated part."""
        self.s.timeout = timeout
        data = self.s.read_until(b"\n")
        return data.decode("ascii", "replace").strip().split("\r")[-1].strip()

    def send(self, text):
        self.write(text.encode("ascii") + b"\r\n")

    def drain(self, idle=0.3):
        """Read until the line has been quiet for `idle` seconds."""
        self.s.timeout = idle
        buf = b""
        while True:
            chunk = self.s.read(4096)
            if not chunk:
                return buf
            buf += chunk

    def already_synced(self):
        """True if the ROM is past autobaud already (e.g. a previous run synced it)."""
        self.s.reset_input_buffer()
        self.send("")  # terminate whatever partial line the ROM holds
        self.drain(0.2)
        self.send("A 0")
        for _ in range(3):
            if self.line(0.3) == "0":
                return True
        return False

    def rejoin(self):
        """True if the ROM is still in a session from an earlier run. A blank
        line ends any partial command; "OK" then acknowledges an R block the
        ROM may still be waiting on (in command mode both are just ignored or
        answered as invalid commands)."""
        self.send("")
        self.drain(0.3)
        self.send("OK")
        self.drain(0.3)
        return self.already_synced()

    def sync(self, xtal_khz, wait_s=0):
        """Autobaud with '?', then finish the handshake in the same session.

        With wait_s > 0, keep sending '?' until the chip answers or the time is
        up, so the chip can be powered into ISP mode while this is running."""
        deadline = time.time() + max(wait_s, 0)
        attempts = 0
        while True:
            attempts += 1
            self.s.reset_input_buffer()
            self.s.write(b"?")
            if self.line(0.5) == "Synchronized":
                break
            if attempts == 5 and self.rejoin():
                # no answer to '?': an earlier run may have left the ROM in a session
                print("boot ROM is still in an ISP session from an earlier run", flush=True)
                return
            if attempts >= 5 and time.time() >= deadline:
                raise RuntimeError("no 'Synchronized' reply: check wiring, ISP pin low at reset, and baud rate")
            time.sleep(0.2)
        print("boot ROM answered 'Synchronized'", flush=True)
        self.send("Synchronized")
        replies = [self.line(), self.line()]
        if "OK" not in replies:
            raise RuntimeError(f"sync handshake failed: {replies}")
        self.send(str(xtal_khz))
        replies = [self.line(), self.line()]
        if "OK" not in replies:
            raise RuntimeError(f"frequency handshake failed: {replies}")
        # turn echo off so every reply starts with the return code
        self.send("A 0")
        for _ in range(3):
            if self.line() == "0":
                return
        raise RuntimeError("could not turn echo off")

    def command(self, text, extra_lines=0):
        self.send(text)
        code = self.line()
        if not code.isdigit():
            code = self.line()  # skip a stray echo
        code = int(code) if code.isdigit() else -1
        lines = [self.line() for _ in range(extra_lines)] if code == 0 else []
        return code, lines

    def resync(self):
        """Get back to command mode after a garbled reply. If the ROM is still
        waiting for a checksum acknowledgement, "OK" completes it; in command
        mode it is just an invalid command. Then flush everything."""
        self.send("OK")
        self.drain(0.5)
        self.send("")
        self.drain(0.5)
        self.s.reset_input_buffer()

    def read_memory(self, addr, length):
        self.send(f"R {addr} {length}")
        code = self.line()
        if not code.isdigit():
            code = self.line()
        self.last_reply = code
        code = int(code) if code.isdigit() else -1
        if code != 0:
            return code, None
        for attempt in range(3):
            raw = self.drain()
            data = decode_uu_block(raw)
            if data is None:
                # boot ROMs that answer in binary send exactly `length` bytes
                if len(raw) == length:
                    return 0, raw
                raise RuntimeError(f"unrecognised R reply ({len(raw)} bytes) at 0x{addr:X}")
            payload, checksum, pad = data
            # whether the ROM's checksum covers the padding is undocumented: accept both
            if checksum in (sum(payload), sum(payload) + pad) and len(payload) == length:
                self.send("OK")
                return 0, payload
            self.send("RESEND")
        raise RuntimeError(f"checksum kept failing at 0x{addr:X}")


def uu_decode_line(line):
    """One UU line -> (data, padding bytes of its last group).

    Unlike binascii.a2b_uu this accepts any padding: when a line's length is
    not a multiple of 3, the boot ROM fills the last group from whatever memory
    follows the requested range, not with zeros."""
    n = (line[0] - 0x20) & 0x3F
    vals = [(c - 0x20) & 0x3F for c in line[1:]]
    vals += [0] * (-len(vals) % 4)
    out = bytearray()
    for i in range(0, len(vals), 4):
        c0, c1, c2, c3 = vals[i:i + 4]
        out += bytes(((c0 << 2 | c1 >> 4) & 0xFF, (c1 << 4 | c2 >> 2) & 0xFF, (c2 << 6 | c3) & 0xFF))
    if len(out) < n:
        raise ValueError("UU line shorter than its length byte says")
    return bytes(out[:n]), bytes(out[n:n + (-n % 3)])


def decode_uu_block(raw):
    """UU-encoded lines followed by a decimal checksum line -> (data, checksum,
    sum of padding bytes), or None."""
    lines = [l for l in raw.replace(b"\r", b"").split(b"\n") if l]
    if len(lines) < 2 or not lines[-1].isdigit():
        return None
    out, pad = b"", 0
    try:
        for l in lines[:-1]:
            data, padding = uu_decode_line(l)
            out += data
            pad += sum(padding)
    except ValueError:
        return None
    return out, int(lines[-1]), pad


def describe_image(data):
    print("\n--- image analysis ---")
    sp, reset = struct.unpack_from("<II", data, 0)
    vsum = sum(struct.unpack_from("<8I", data, 0)) & 0xFFFFFFFF
    print(f"vector table @0x0: SP=0x{sp:08X} reset=0x{reset:08X} checksum {'OK' if vsum == 0 else 'BAD'}")
    if len(data) >= 0x300:
        crp = struct.unpack_from("<I", data, 0x2FC)[0]
        print(f"word @0x2FC = 0x{crp:08X} -> {CRP_PATTERNS.get(crp, 'no code read protection')}")
    # a second vector table usually marks where Razer's bootloader hands over to the app
    for off in range(0x400, len(data) - 8, 0x100):
        sp2, rv = struct.unpack_from("<II", data, off)
        if 0x10000000 < sp2 <= 0x10001000 and rv & 1 and off < (rv & ~1) < len(data):
            print(f"candidate application vector table @0x{off:04X}: SP=0x{sp2:08X} reset=0x{rv:08X}")
    used = len(data.rstrip(b"\xff"))
    print(f"flash in use: {used} of {len(data)} bytes")


def main():
    for stream in (sys.stdout, sys.stderr):  # garbled serial text must never crash a print
        try:
            stream.reconfigure(errors="backslashreplace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("port", help="serial port, e.g. COM5 or /dev/ttyUSB0")
    ap.add_argument("--out", default="orbweaver_stock_flash.bin")
    ap.add_argument("--size", type=int, default=24 * 1024, help="flash size in bytes (LPC11U13: 24576)")
    ap.add_argument("--baud", type=int, default=57600)
    ap.add_argument("--xtal", type=int, default=12000, help="crystal frequency in kHz")
    ap.add_argument("--info", action="store_true", help="identify the chip only, do not read flash")
    ap.add_argument("--wait", type=int, default=0, help="keep trying for this many seconds (power the chip into ISP meanwhile)")
    args = ap.parse_args()

    isp = Isp(args.port, args.baud)
    if args.wait:
        print(f"waiting up to {args.wait} s: power the chip up with ISP held low now", flush=True)
    isp.sync(args.xtal, args.wait)
    print("synchronised with the boot ROM", flush=True)

    code, lines = isp.command("J", 1)
    print(f"part id      : {('0x%08X' % int(lines[0])) if code == 0 else RETURN_CODES.get(code, code)}")
    code, lines = isp.command("K", 2)
    if code == 0:
        print(f"boot code    : {lines[0]}.{lines[1]} (major.minor as sent: {lines})")
    code, lines = isp.command("N", 4)
    if code == 0:
        print(f"serial number: {' '.join('%08X' % int(x) for x in lines)}")

    if args.info:
        return 0

    image = bytearray()
    partial = args.out + ".partial"
    for addr in range(0, args.size, CHUNK):
        n = min(CHUNK, args.size - addr)
        for attempt in range(5):
            try:
                code, data = isp.read_memory(addr, n)
            except RuntimeError as e:
                code, data = -1, None
                isp.last_reply = str(e)
            if code in (0, 19):
                break
            print(f"\nretry {attempt + 1} at 0x{addr:X} (reply {getattr(isp, 'last_reply', '')!r})", flush=True)
            isp.resync()
        if code == 19:
            print("\nCODE READ PROTECTION IS ENABLED: the flash cannot be read or backed up.")
            print("Nothing was written to the chip. Do not erase it unless you accept losing the stock firmware.")
            return 1
        if code != 0:
            print(f"\nread failed at 0x{addr:X}: {RETURN_CODES.get(code, code)}")
            return 1
        image += data
        with open(partial, "wb") as f:
            f.write(image)
        print(f"\rread {len(image)}/{args.size} bytes", end="", flush=True)
    print()

    with open(args.out, "wb") as f:
        f.write(image)
    print(f"saved {args.out}  sha256 {hashlib.sha256(image).hexdigest()}")
    describe_image(bytes(image))
    print("\nDone. Unplug and replug normally (ISP pin released) to run the stock firmware again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
