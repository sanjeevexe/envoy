"""Draw Envoy's app icons (Home Screen, manifest, notifications) into web/public/icons/.

  uv run --project backend python scripts/make_icons.py

The mark: an "E" of three bars on a dark tile, the middle bar green, an agent acting between the other two. Drawn at
4x and scaled down for clean edges. iOS fills transparent icon pixels with black, so the Home Screen icons are opaque.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "web" / "public" / "icons"
DARK, WHITE, GREEN = (28, 28, 26), (250, 250, 247), (16, 185, 129)


def mark(size: int, *, pad: float, rounded: bool, mono: bool = False) -> Image.Image:
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0) if mono else DARK + (255,))
    d = ImageDraw.Draw(img)
    if rounded and not mono:
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=DARK + (255,))
    inner = s * (1 - 2 * pad)
    x0, y0 = s * pad + inner * 0.18, s * pad + inner * 0.14
    w, h = inner * 0.64, inner * 0.72
    bar = h * 0.19
    r = int(bar * 0.45)
    ink = WHITE + (255,)
    d.rounded_rectangle([x0, y0, x0 + bar, y0 + h], radius=r, fill=ink)  # spine
    d.rounded_rectangle([x0, y0, x0 + w, y0 + bar], radius=r, fill=ink)  # top
    d.rounded_rectangle([x0, y0 + h - bar, x0 + w, y0 + h], radius=r, fill=ink)  # bottom
    mid = y0 + (h - bar) / 2
    d.rounded_rectangle([x0 + bar * 1.45, mid, x0 + w * 0.86, mid + bar], radius=r, fill=(WHITE if mono else GREEN) + (255,))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mark(180, pad=0.1, rounded=False).convert("RGB").save(OUT / "apple-touch-icon.png")
    mark(192, pad=0.1, rounded=True).save(OUT / "icon-192.png")
    mark(512, pad=0.1, rounded=True).save(OUT / "icon-512.png")
    mark(512, pad=0.2, rounded=False).convert("RGB").save(OUT / "maskable-512.png")  # content inside the safe zone
    mark(96, pad=0.05, rounded=False, mono=True).save(OUT / "badge-96.png")  # notification badge: shape only
    mark(64, pad=0.08, rounded=True).save(OUT / "favicon-64.png")
    print("icons in", OUT)


if __name__ == "__main__":
    main()
