"""Build a multi-resolution Windows .ico from the project artwork.

Accepts icon.jpg or icon.png. Run it after replacing the artwork; the generated
icon.ico is what loginmg.py loads at runtime and what PyInstaller stamps into
the executable.
"""

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
DST = HERE / "icon.ico"
SOURCES = ("icon.jpg", "icon.png")
SIZES = (16, 24, 32, 48, 64, 128, 256)


def find_artwork():
    for name in SOURCES:
        candidate = HERE / name
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    source_path = find_artwork()
    if source_path is None:
        print(f"no artwork found; looked for {', '.join(SOURCES)} in {HERE}")
        return 1

    source = Image.open(source_path)
    print(f"origen  : {source_path.name}  {source.size[0]}x{source.size[1]}  {source.mode}")

    # Centre-crop to a square so the logo is not distorted.
    width, height = source.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    square = source.convert("RGB").crop((left, top, left + side, top + side))
    print(f"recorte : {side}x{side} desde ({left},{top})")

    master = square.resize((256, 256), Image.LANCZOS)
    master.save(DST, format="ICO", sizes=[(n, n) for n in SIZES])

    check = Image.open(DST)
    print(f"destino : {DST.name}  {DST.stat().st_size} bytes")
    print("resoluciones:")
    for width_px, height_px in sorted(check.ico.sizes(), reverse=True):
        print(f"   {width_px}x{height_px}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
