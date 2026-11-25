"""Draws the app icon (Resources/icon/icon.png, icon.icns, icon.ico).   python tools/make_icon.py

An open book (the colour of the app) with a green arrow badge that says "get Bibles". Needs Pillow.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "Resources" / "icon"
S = 2048                      # drawn big, then made smaller (smooth edges)
ORANGE, ORANGE_D = (255, 138, 30), (214, 104, 8)
BG1, BG2 = (42, 45, 52), (23, 24, 27)
GREEN = (52, 199, 89)
INK = (23, 24, 27)


def gradient(size, top, bottom):
    img = Image.new("RGB", (size, size), top)
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(size):
            px[x, y] = c
    return img


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # rounded square background (Apple's icon shape: about 82% of the canvas, centred)
    m = int(S * 0.09)
    box = (m, m, S - m, S - m)
    bg = gradient(S, BG1, BG2).convert("RGBA")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=int(S * 0.19), fill=255)
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((m, m + 30, S - m, S - m + 30), radius=int(S * 0.19), fill=(0, 0, 0, 120))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(28)))
    img.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=int(S * 0.19), outline=(255, 255, 255, 28), width=6)

    # open book: a cover, two curved pages, a spine, lines of text
    def bez(p0, p1, p2, n=40):
        out = []
        for i in range(n + 1):
            t = i / n
            out.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                        (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]))
        return out

    cx = S // 2
    left, right = int(S * 0.17), int(S * 0.83)
    top_in, top_out = int(S * 0.33), int(S * 0.285)       # top edge: at the spine, at the outer edge
    bot_in, bot_out = int(S * 0.70), int(S * 0.655)
    bow = int(S * 0.06)                                    # how much the pages bow up in the middle
    cover = int(S * 0.03)
    # cover (the dark orange behind and under the pages)
    d.rounded_rectangle((left - cover, top_out - cover + bow // 2, right + cover, bot_in + cover * 2), radius=int(S * 0.035),
                        fill=ORANGE_D)
    for side in (-1, 1):
        outer = left if side < 0 else right
        mid = (cx + outer) // 2
        top = bez((cx, top_in), (mid, top_out - bow), (outer, top_out))
        bottom = bez((outer, bot_out), (mid, bot_out - bow + int(S * 0.02)), (cx, bot_in))
        page = top + bottom
        # a thin darker edge under the page gives it thickness
        d.polygon([(x, y + int(S * 0.02)) for x, y in page], fill=(255, 205, 140))
        d.polygon(page, fill=(255, 244, 228))
        # lines of text, following the bow
        for i in range(5):
            f = 0.17 + i * 0.12
            y_in = top_in + (bot_in - top_in) * f
            y_out = top_out + (bot_out - top_out) * f
            ym = (y_in + y_out) / 2 - bow * 0.10
            x_a = cx + side * int(S * 0.045)
            x_b = cx + side * int(S * (0.27 if i < 4 else 0.16))
            pts = bez((x_a, y_in), ((x_a + x_b) / 2, ym), (x_b, y_out + (y_in - y_out) * (0.55 if i < 4 else 0.7)))
            d.line(pts, fill=(214, 120, 30), width=20, joint="curve")
    # spine
    d.rounded_rectangle((cx - 13, top_in - 6, cx + 13, bot_in + 10), radius=10, fill=(140, 62, 4))

    # badge: a green circle with a down arrow (bottom right)
    r = int(S * 0.15)
    bx, by = int(S * 0.72), int(S * 0.72)
    d.ellipse((bx - r - 14, by - r - 14, bx + r + 14, by + r + 14), fill=BG2)
    d.ellipse((bx - r, by - r, bx + r, by + r), fill=GREEN)
    a = int(r * 0.52)
    w = int(r * 0.2)
    d.rounded_rectangle((bx - w // 2, by - a, bx + w // 2, by + a // 3), radius=w // 2, fill=(255, 255, 255))
    d.polygon([(bx - a * 0.9, by - a * 0.05), (bx + a * 0.9, by - a * 0.05), (bx, by + a * 0.95)], fill=(255, 255, 255))
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    big = draw()
    png = big.resize((1024, 1024), Image.LANCZOS)
    png.save(OUT / "icon.png")
    # Mac: .icns (Pillow writes the sizes the Mac uses)
    png.save(OUT / "icon.icns", format="ICNS")
    # Windows: .ico with the usual sizes
    png.save(OUT / "icon.ico", format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("saved", [p.name for p in sorted(OUT.iterdir())])


if __name__ == "__main__":
    main()
