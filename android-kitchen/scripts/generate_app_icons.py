from PIL import Image, ImageDraw
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "ui", "static", "ui", "img", "cafe-de-paris-logo.png")
RES = os.path.join(ROOT, "android-kitchen", "app", "src", "main", "res")
BG = (0x8B, 0x45, 0x13, 255)

DENSITIES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def make_square_icon(logo, size, padding_ratio=0.12, round_mask=False):
    canvas = Image.new("RGBA", (size, size), BG)
    inner = int(size * (1 - 2 * padding_ratio))
    lw, lh = logo.size
    scale = min(inner / lw, inner / lh)
    nw, nh = int(lw * scale), int(lh * scale)
    resized = logo.resize((nw, nh), Image.Resampling.LANCZOS)
    x = (size - nw) // 2
    y = (size - nh) // 2
    canvas.paste(resized, (x, y), resized)
    if round_mask:
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size - 1, size - 1), fill=255)
        result = Image.new("RGBA", (size, size), BG)
        result.paste(canvas, (0, 0), mask)
        return result
    return canvas


def main():
    logo = Image.open(SRC).convert("RGBA")

    drawable_nodpi = os.path.join(RES, "drawable-nodpi")
    os.makedirs(drawable_nodpi, exist_ok=True)
    make_square_icon(logo, 432, padding_ratio=0.18).save(
        os.path.join(drawable_nodpi, "ic_launcher_foreground.png")
    )

    for folder, size in DENSITIES.items():
        out_dir = os.path.join(RES, folder)
        os.makedirs(out_dir, exist_ok=True)
        make_square_icon(logo, size).save(os.path.join(out_dir, "ic_launcher.png"))
        make_square_icon(logo, size, round_mask=True).save(
            os.path.join(out_dir, "ic_launcher_round.png")
        )


if __name__ == "__main__":
    main()
