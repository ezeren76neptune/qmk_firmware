#!/usr/bin/env python3
"""Draw orbweaver_keymap.ico (a small keypad) with the standard library only:
PNG images inside an ICO container, which Windows Vista and later read."""

import struct
import sys
import zlib
from pathlib import Path

BG = (31, 36, 48)
KEY = (232, 232, 226)
ACCENT = (47, 111, 222)


def rounded_rect_cov(x, y, rx0, ry0, rx1, ry1, r):
    """Is (x, y) inside the rounded rectangle?"""
    if not (rx0 <= x <= rx1 and ry0 <= y <= ry1):
        return False
    cx = min(max(x, rx0 + r), rx1 - r)
    cy = min(max(y, ry0 + r), ry1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def draw(size):
    s = 4  # supersampling
    cols, rows = (3, 3) if size <= 24 else (5, 4)
    pad = size * 0.06
    shapes = [((pad, pad, size - pad, size - pad), size * 0.18, BG)]
    inner = size * (0.17 if size <= 24 else 0.14)
    gap = size * (0.07 if size <= 24 else 0.045)
    kw = (size - 2 * inner - (cols - 1) * gap) / cols
    kh = (size - 2 * inner - (rows - 1) * gap) / rows
    for r in range(rows):
        for c in range(cols):
            x0, y0 = inner + c * (kw + gap), inner + r * (kh + gap)
            color = ACCENT if (r, c) == (0, 0) else KEY
            shapes.append(((x0, y0, x0 + kw, y0 + kh), min(kw, kh) * 0.22, color))
    px = bytearray()
    for y in range(size):
        px.append(0)  # PNG filter byte
        for x in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(s):
                for sx in range(s):
                    fx, fy = x + (sx + 0.5) / s, y + (sy + 0.5) / s
                    col = None
                    for rect, rad, color in shapes:
                        if rounded_rect_cov(fx, fy, *rect, rad):
                            col = color
                    if col:
                        acc[0] += col[0]; acc[1] += col[1]; acc[2] += col[2]; acc[3] += 255
            n = s * s
            a = acc[3] // n
            if a:
                cover = acc[3] // 255
                px += bytes((acc[0] // cover, acc[1] // cover, acc[2] // cover, a))
            else:
                px += b"\0\0\0\0"
    return png(size, size, bytes(px))


def png(w, h, raw):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico(images):
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    dirs, blobs = b"", b""
    for size, data in images:
        dim = 0 if size >= 256 else size
        dirs += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    return head + dirs + blobs


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("orbweaver_keymap.ico"))
    images = [(n, draw(n)) for n in (16, 24, 32, 48, 64, 256)]
    out.write_bytes(ico(images))
    Path(out.with_suffix(".png")).write_bytes(images[-1][1])  # preview
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
