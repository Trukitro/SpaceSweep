"""Render spacesweep/ui/logo.svg into a Windows .ico for the PyInstaller build.

The SVG stays the only logo in the repository; this script redraws the same
geometry (keep the numbers below in sync with logo.svg) with a small
anti-aliased rasterizer, so no image library is needed.

    python tools/make_icon.py out.ico
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from spacesweep.imaging import ico, png  # noqa: E402

TOP, BOTTOM = (0x2D, 0xD4, 0xBF), (0x25, 0x63, 0xEB)
ARC_END = math.atan2(26.8 - 32, 48.2 - 32)  # path end point of the bright arc
LINES = [((46, 42), (52, 48)), ((41, 47), (45, 51)), ((50, 37), (55, 39))]


def in_round_rect(x, y, x0=2, y0=2, w=60, h=60, r=16):
    cx = min(max(x, x0 + r), x0 + w - r)
    cy = min(max(y, y0 + r), y0 + h - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r and x0 <= x <= x0 + w and y0 <= y <= y0 + h


def seg_dist(px, py, a, b):
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def sample(x, y):
    """Colour (r, g, b, a in 0..1) of the logo at viewBox coordinates x, y."""
    if not in_round_rect(x, y):
        return None
    t = ((x - 2) + (y - 2)) / 120
    col = [TOP[i] + (BOTTOM[i] - TOP[i]) * t for i in range(3)]

    def over(alpha):
        for i in range(3):
            col[i] = col[i] * (1 - alpha) + 255 * alpha

    d = math.hypot(x - 32, y - 32)
    if abs(d - 17) <= 3:
        over(0.35)
    ang = math.atan2(y - 32, x - 32)
    start = (32, 15)
    end = (32 + 17 * math.cos(ARC_END), 32 + 17 * math.sin(ARC_END))
    if (abs(d - 17) <= 3 and -math.pi / 2 <= ang <= ARC_END) or math.hypot(x - start[0], y - start[1]) <= 3 \
            or math.hypot(x - end[0], y - end[1]) <= 3:
        over(1)
    if d <= 4.5 or any(seg_dist(x, y, a, b) <= 1.5 for a, b in LINES):
        over(1)
    return col


def render(size, ss=4):
    out = bytearray(size * size * 4)
    scale = 64 / size
    for py in range(size):
        for px in range(size):
            r = g = b = a = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    c = sample((px + (sx + 0.5) / ss) * scale, (py + (sy + 0.5) / ss) * scale)
                    if c:
                        r += c[0]
                        g += c[1]
                        b += c[2]
                        a += 1
            i = (py * size + px) * 4
            if a:
                out[i:i + 4] = bytes((round(r / a), round(g / a), round(b / a), round(255 * a / (ss * ss))))
    return bytes(out)


def main(path):
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [(s, png(s, s, render(s, 4 if s <= 64 else 2))) for s in sizes]
    with open(path, "wb") as fh:
        fh.write(ico(images))
    print(f"wrote {path} ({len(sizes)} sizes)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "SpaceSweep.ico")
