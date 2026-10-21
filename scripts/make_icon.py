from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE_PNG = ROOT / "assets/pixel/sit_idle/000.png"
OUTPUT_ICO = ROOT / "assets/icon.ico"

ICON_SIZES = [
    (16, 16),
    (24, 24),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
]

def main():
    if not SOURCE_PNG.exists():
        raise FileNotFoundError(f"Не найден файл: {SOURCE_PNG}")

    with Image.open(SOURCE_PNG) as source:
        img = source.convert("RGBA")
    bounds = img.getbbox()
    if bounds is None:
        raise ValueError(f"Пустой кадр: {SOURCE_PNG}")
    img = img.crop(bounds)

    max_side = max(img.width, img.height) + 2
    square = Image.new("RGBA", (max_side, max_side), (0, 0, 0, 0))

    x = (max_side - img.width) // 2
    y = (max_side - img.height) // 2
    square.paste(img, (x, y))

    # Supply each size explicitly: Pillow's automatic ICO resize smooths
    # pixel art. Keep the source colors and transparent background instead.
    frames = [square.resize(size, Image.Resampling.NEAREST) for size in ICON_SIZES]

    frames[-1].save(
        OUTPUT_ICO,
        format="ICO",
        sizes=ICON_SIZES,
        append_images=frames[:-1],
    )
    frames[-1].save(ROOT / "assets/icon.png")

    print(f"Готово: {OUTPUT_ICO}")


if __name__ == "__main__":
    main()
