"""Generate the simple geometric Engram beta icon. Requires Pillow."""

from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1] / "assets"
SIZE = 1024
SCALE = 2
BG = (12, 20, 32, 255)
CYAN = (124, 202, 255, 255)


def symbol(background: bool, monochrome: bool = False) -> Image.Image:
    image = Image.new("RGBA", (SIZE * SCALE, SIZE * SCALE), BG if background else (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = (255, 255, 255, 255) if monochrome else CYAN
    s = SCALE
    # Three memory nodes share one spine; each branch is its own retrievable fact.
    draw.rounded_rectangle((292*s, 250*s, 352*s, 774*s), radius=30*s, fill=color)
    for y, length in [(280, 430), (512, 350), (744, 430)]:
        draw.rounded_rectangle((320*s, (y-30)*s, (320+length)*s, (y+30)*s), radius=30*s, fill=color)
        draw.ellipse(((320+length-34)*s, (y-34)*s, (320+length+34)*s, (y+34)*s), fill=color)
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def save(name: str, image: Image.Image, size: int = SIZE):
    image.resize((size, size), Image.Resampling.LANCZOS).save(ROOT / name)


save("icon.png", symbol(True))
save("android-icon-foreground.png", symbol(False))
save("android-icon-monochrome.png", symbol(False, True))
save("android-icon-background.png", Image.new("RGBA", (SIZE, SIZE), BG))
save("splash-icon.png", symbol(False), 512)
save("favicon.png", symbol(True), 64)
