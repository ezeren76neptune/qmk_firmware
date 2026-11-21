#!/usr/bin/env python3
"""Sanity-check (and optionally fix) an NXP LPC11Uxx firmware image before flashing.

  * Vector checksum: the boot ROM only runs user code if the first 8 vector
    words sum to zero (word 7 holds the two's complement). The QMK linker
    script computes it; this re-verifies the .bin that will actually be flashed.
  * Code Read Protection: the word at 0x2FC must not be one of NXP's CRP/NO_ISP
    patterns, or the chip locks out SWD and/or ISP after the next reset.

usage: lpc11u_image_check.py firmware.bin [--fix-checksum]
exit status 0 = safe to flash, 1 = problem found.
"""
import struct
import sys

CRP_PATTERNS = {
    0x12345678: "CRP1 (SWD disabled, partial ISP)",
    0x87654321: "CRP2 (SWD disabled, ISP mass-erase only)",
    0x43218765: "CRP3 (SWD and ISP entry pin disabled - permanent lock)",
    0x4E697370: "NO_ISP (ISP entry pin disabled)",
}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = sys.argv[1]
    fix = "--fix-checksum" in sys.argv[2:]
    data = bytearray(open(path, "rb").read())
    ok = True

    if len(data) < 32:
        print(f"{path}: too small to be a Cortex-M image")
        return 1

    words = list(struct.unpack_from("<8I", data, 0))
    total = sum(words) & 0xFFFFFFFF
    if total == 0:
        print(f"vector checksum OK (word 7 = 0x{words[7]:08X})")
    else:
        want = (-sum(words[:7])) & 0xFFFFFFFF
        if fix:
            struct.pack_into("<I", data, 0x1C, want)
            open(path, "wb").write(data)
            print(f"vector checksum fixed: word 7 = 0x{want:08X}")
        else:
            print(f"vector checksum BAD: word 7 is 0x{words[7]:08X}, should be 0x{want:08X} (use --fix-checksum)")
            ok = False

    if len(data) >= 0x300:
        crp = struct.unpack_from("<I", data, 0x2FC)[0]
        if crp in CRP_PATTERNS:
            print(f"DANGER: word at 0x2FC = 0x{crp:08X} = {CRP_PATTERNS[crp]}. Do not flash this image.")
            ok = False
        else:
            print(f"CRP word at 0x2FC = 0x{crp:08X} (no protection)")

    print(f"image size {len(data)} bytes")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
