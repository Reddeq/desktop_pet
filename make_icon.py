from pathlib import Path
from PIL import Image

SOURCE_PNG = Path("assets/icon.png")
OUTPUT_ICO = Path("assets/icon.ico")

ICON_SIZES = [
    (16, 16),
    (24, 24),
    (32, 32),
    (48, 48),
    (256, 256),
]

def main():
    if not SOURCE_PNG.exists():
        raise FileNotFoundError(f"Не найден файл: {SOURCE_PNG}")

    img = Image.open(SOURCE_PNG).convert("RGBA")

    max_side = max(img.width, img.height)
    square = Image.new("RGBA", (max_side, max_side), (0, 0, 0, 0))

    x = (max_side - img.width) // 2
    y = (max_side - img.height) // 2
    square.paste(img, (x, y), img)

    square.save(
        OUTPUT_ICO,
        format="ICO",
        sizes=ICON_SIZES,
    )

    print(f"Готово: {OUTPUT_ICO}")


if __name__ == "__main__":
    main()