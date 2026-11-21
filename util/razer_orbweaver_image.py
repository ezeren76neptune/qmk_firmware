#!/usr/bin/env python3
"""Build a full 24 KiB flash image for the Razer Orbweaver: Razer's USB
bootloader from the stock backup, QMK at 0x1000, Razer's sector 5.

Flash this image once over UART ISP (util/lpc_isp_flash.py). After that, QMK
updates go over USB with util/razer_orbweaver_usb_flash.py.

    0x0000-0x0FFF  Razer bootloader (USB 1532:110D), incl. the factory serial
    0x1000-0x4FFF  QMK built for razer/orbweaver/stock (linked at 0x1000)
    0x5000-0x5FFF  Razer settings + "application valid" marker at 0x5FFC

Unless --no-key01-patch is given, the bootloader's entry keys are changed from
thumb Space + Alt to key 01 (or key 04: same column) held while plugging in,
so the bootloader can be reached without the thumb module, even when the
firmware behind it does not start. The patch is one instruction and two
literal words; every byte is checked against the stock values first.

usage: razer_orbweaver_image.py STOCK_BACKUP.bin QMK.bin -o OUT.bin [--no-key01-patch]
"""

import argparse
import hashlib
import struct
import sys

FLASH = 24 * 1024
APP_BASE, APP_END = 0x1000, 0x5000  # what the bootloader can erase and write
MARKER_ADDR, MARKER_VALID = 0x5FFC, 0x12305670

# (offset, size, stock value, patched value, what it is)
KEY01_PATCH = [
    (0x00EE, 2, 0x670A, 0x640A, "str r2,[r1,#0x70] -> #0x40: pull-up on PIO1_16 (key 01 column) instead of PIO1_28"),
    (0x0178, 4, 0x5000101C, 0x500010C0, "column read 1: PIO0_7 (thumb Alt) -> PIO1_16 (key 01)"),
    (0x017C, 4, 0x500010F0, 0x500010C0, "column read 2: PIO1_28 (thumb Space) -> PIO1_16 (key 01)"),
]


def fail(msg):
    sys.exit(f"error: {msg}")


def check_stock(img):
    if len(img) != FLASH:
        fail(f"backup is {len(img)} bytes, expected {FLASH}")
    if sum(struct.unpack_from("<8I", img, 0)) & 0xFFFFFFFF:
        fail("backup vector checksum is wrong: not a valid LPC11U image")
    vid, pid = struct.unpack_from("<HH", img, 0x0BF0)
    if img[0x0BE8:0x0BEA] != b"\x12\x01" or (vid, pid) != (0x1532, 0x110D):
        fail("no Razer bootloader device descriptor (1532:110D) at 0x0BE8: is this an Orbweaver stock backup?")
    if struct.unpack_from("<I", img, 0x0198)[0] != APP_BASE:
        fail("the bootloader in this backup does not start its application at 0x1000")


def check_app(app):
    if not 0x100 <= len(app) <= APP_END - APP_BASE:
        fail(f"QMK image is {len(app)} bytes; it must fit in 0x{APP_BASE:X}-0x{APP_END - 1:X} ({APP_END - APP_BASE} bytes)")
    sp, reset = struct.unpack_from("<II", app, 0)
    if not 0x10000000 < sp <= 0x10001000:
        fail(f"QMK initial SP 0x{sp:08X} is not in SRAM: wrong .bin?")
    if not (reset & 1 and APP_BASE <= (reset & ~1) < APP_BASE + len(app)):
        fail(f"QMK reset vector 0x{reset:08X} is not inside 0x1000+: build razer/orbweaver/stock (linked at 0x1000)")


def apply_patch(img):
    for off, size, stock, new, what in KEY01_PATCH:
        fmt = "<H" if size == 2 else "<I"
        cur = struct.unpack_from(fmt, img, off)[0]
        if cur == new:
            print(f"  0x{off:04X} already patched")
            continue
        if cur != stock:
            fail(f"0x{off:04X} holds 0x{cur:X}, expected stock 0x{stock:X}; not patching an unknown bootloader")
        struct.pack_into(fmt, img, off, new)
        print(f"  0x{off:04X}: 0x{stock:X} -> 0x{new:X}  ({what})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stock", help="24 KiB stock flash backup (lpc_isp_backup.py)")
    ap.add_argument("qmk", help="razer_orbweaver_stock_*.bin, linked at 0x1000")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--no-key01-patch", action="store_true", help="keep Razer's thumb Space + Alt entry keys")
    args = ap.parse_args()

    stock = bytearray(open(args.stock, "rb").read())
    app = open(args.qmk, "rb").read()
    check_stock(stock)
    check_app(app)

    img = bytearray(stock)
    if args.no_key01_patch:
        print("bootloader left as stock (enter it with thumb Space + Alt held while plugging in)")
    else:
        print("bootloader entry keys -> key 01 held while plugging in:")
        apply_patch(img)
    img[APP_BASE:APP_END] = app + b"\xFF" * (APP_END - APP_BASE - len(app))

    marker = struct.unpack_from("<I", img, MARKER_ADDR)[0]
    if marker != MARKER_VALID:
        print(f"warning: marker at 0x{MARKER_ADDR:X} is 0x{marker:08X}, not 0x{MARKER_VALID:08X}; "
              "the bootloader may stay in update mode until an update finishes")
    if sum(struct.unpack_from("<8I", img, 0)) & 0xFFFFFFFF:
        fail("internal error: vector checksum broke")

    open(args.out, "wb").write(img)
    print(f"QMK {len(app)} bytes at 0x{APP_BASE:X} ({APP_END - APP_BASE - len(app)} bytes left)")
    print(f"wrote {args.out}: {len(img)} bytes, sha256 {hashlib.sha256(img).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
