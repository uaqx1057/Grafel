"""Generate grafel.ico + grafel.png - neon node-graph logo on dark tile."""

from PIL import Image, ImageDraw, ImageFilter

BG = (5, 8, 16, 255)
CYAN = (0, 240, 255, 255)
MAGENTA = (255, 47, 214, 255)
GREEN = (57, 255, 136, 255)
EDGE = (13, 90, 110, 255)

# node layout (relative 0..1 coords) - stylized constellation "G"
NODES = [
    (0.72, 0.22), (0.42, 0.16), (0.20, 0.38), (0.22, 0.66),
    (0.46, 0.84), (0.74, 0.74), (0.76, 0.52), (0.54, 0.52),
]
EDGES = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7)]
ACCENT = {0: MAGENTA, 4: GREEN}  # a couple of colored nodes


def draw_logo(size):
    s = size * 4  # supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # rounded dark tile
    r = s // 6
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=BG,
                        outline=(0, 120, 140, 255), width=max(2, s // 96))

    pts = [(x * s, y * s) for x, y in NODES]

    # glow layer
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    lw = max(3, s // 42)
    for a, b in EDGES:
        gd.line([pts[a], pts[b]], fill=CYAN, width=lw)
    nr = max(5, s // 16)
    for i, p in enumerate(pts):
        c = ACCENT.get(i, CYAN)
        gd.ellipse([p[0] - nr, p[1] - nr, p[0] + nr, p[1] + nr], fill=c)
    glow = glow.filter(ImageFilter.GaussianBlur(s // 28))
    img.alpha_composite(glow)

    # crisp layer
    for a, b in EDGES:
        d.line([pts[a], pts[b]], fill=EDGE, width=max(2, s // 64))
    for i, p in enumerate(pts):
        c = ACCENT.get(i, CYAN)
        nr2 = max(4, s // 20)
        d.ellipse([p[0] - nr2, p[1] - nr2, p[0] + nr2, p[1] + nr2],
                  fill=c, outline=BG, width=max(1, s // 128))

    return img.resize((size, size), Image.LANCZOS)


def main():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = {sz: draw_logo(sz) for sz in sizes}
    ico = os.path.join(here, "grafel.ico")
    imgs[256].save(ico, format="ICO",
                   sizes=[(sz, sz) for sz in sizes],
                   append_images=[imgs[sz] for sz in sizes[:-1]])
    imgs[256].save(os.path.join(here, "grafel.png"))
    print(f"wrote {ico}")


if __name__ == "__main__":
    main()
