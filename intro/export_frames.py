"""Turn the rendered Remotion frames into the small PNGs the app plays at launch.

    cd intro
    npm run render                                   # -> intro/out/frames/*.png
    uv run --with pillow python export_frames.py     # -> assets/intro/*.png

The intro has flat colours on a flat background, so a 256-colour palette looks
identical and cuts the size by ~75%.
"""
import os
import shutil

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "out", "frames")
TARGET = os.path.join(HERE, "..", "assets", "intro")


def main():
    names = sorted(n for n in os.listdir(SOURCE) if n.endswith(".png"))
    if not names:
        raise SystemExit("No frames found. Run `npm run render` first.")
    shutil.rmtree(TARGET, ignore_errors=True)
    os.makedirs(TARGET)
    total = 0
    for i, name in enumerate(names):
        image = Image.open(os.path.join(SOURCE, name)).convert("RGB")
        small = image.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        path = os.path.join(TARGET, f"frame_{i:03d}.png")
        small.save(path, optimize=True)
        total += os.path.getsize(path)
    print(f"Wrote {len(names)} frames, {total // 1024} KB, to {os.path.normpath(TARGET)}")


if __name__ == "__main__":
    main()
