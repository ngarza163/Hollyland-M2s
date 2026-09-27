"""Render the app icon (orange tile, white microphone) to assets/icon.png and assets/app.ico."""
import os
import struct
import zlib

TOP, BOTTOM = (0xFF, 0x8C, 0x3A), (0xEE, 0x5E, 0x0C)
SAMPLES = 4


def inside_round_rect(x, y, x0, y0, x1, y1, r):
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r and x0 <= x <= x1 and y0 <= y <= y1


def glyph(x, y):
    if inside_round_rect(x, y, 0.37, 0.16, 0.63, 0.60, 0.13):                    # capsule
        return True
    d = ((x - 0.5) ** 2 + (y - 0.44) ** 2) ** 0.5                               # holder arc
    if y >= 0.44 and abs(d - 0.235) <= 0.03:
        return True
    if abs(x - 0.5) <= 0.03 and 0.675 <= y <= 0.80:                              # stem
        return True
    return inside_round_rect(x, y, 0.35, 0.77, 0.65, 0.83, 0.03)                 # base


def render(n):
    rows = []
    for py in range(n):
        row = bytearray([0])
        for px in range(n):
            bg = fg = 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x = (px + (sx + 0.5) / SAMPLES) / n
                    y = (py + (sy + 0.5) / SAMPLES) / n
                    if inside_round_rect(x, y, 0.03, 0.03, 0.97, 0.97, 0.22):
                        bg += 1
                        fg += glyph(x, y)
            total = SAMPLES * SAMPLES
            a = bg / total
            w = fg / bg if bg else 0
            t = py / max(n - 1, 1)
            base = [TOP[i] + (BOTTOM[i] - TOP[i]) * t for i in range(3)]
            rgb = [round(c + (255 - c) * w) for c in base]
            row += bytes(rgb + [round(a * 255)])
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    os.makedirs("assets", exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    pngs = {n: render(n) for n in sizes}
    with open("assets/icon.png", "wb") as f:
        f.write(pngs[256])
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for n in sizes:
        data = pngs[n]
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    with open("assets/app.ico", "wb") as f:
        f.write(header + entries + blobs)
    print("wrote assets/icon.png and assets/app.ico")


if __name__ == "__main__":
    main()
