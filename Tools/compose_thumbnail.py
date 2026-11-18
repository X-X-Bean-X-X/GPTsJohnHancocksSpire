"""Compose the Chicago GPT preview from the two rendered views."""

from math import exp
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont


root = Path(__file__).resolve().parents[1]
renders = Path(sys.argv[1])
size = 1024
palette = {
    "gold": (222, 174, 91),
    "title": (254, 229, 172),
    "body": (212, 223, 236),
}
backdrop = Image.new("RGB", (size, size))
pixels = []
for y in range(size):
    for x in range(size):
        halo = exp(-((x - 282) / 255) ** 2 - ((y - 490) / 420) ** 2)
        horizon = exp(-((y - 811) / 155) ** 2 - ((x - 205) / 455) ** 2)
        pixels.append((int(9 + 19 * halo + 13 * horizon), int(18 + 40 * halo + 8 * horizon),
                       int(37 + 77 * halo + 2 * horizon)))
backdrop.putdata(pixels)
cover = backdrop.convert("RGBA")
main = Image.open(renders / "full.png").convert("RGBA")
main_x, main_y = 80, 40
tip = main.getbbox()
top = main.crop((0, tip[1], main.width, tip[1] + 2)).getbbox()
light_x = main_x + (top[0] + top[2]) / 2
light_y = main_y + tip[1] + 23
halo = Image.new("RGBA", cover.size)
ImageDraw.Draw(halo).ellipse((light_x - 5, light_y - 5, light_x + 5, light_y + 5),
                             fill=(255, 40, 52, 155))
cover.alpha_composite(halo.filter(ImageFilter.GaussianBlur(9)))
cover.alpha_composite(main, (main_x, main_y))

font_dir = Path("C:/Windows/Fonts")
serif = lambda points: ImageFont.truetype(str(font_dir / "georgia.ttf"), points)
sans = lambda points: ImageFont.truetype(str(font_dir / "segoeuisl.ttf"), points)


def tracking(draw, label, at, font, color, spacing):
    x, y = at
    for letter in label:
        draw.text((x, y), letter, font=font, fill=color, anchor="lt")
        x += font.getlength(letter) + spacing


draw = ImageDraw.Draw(cover)
draw.line((430, 165, 951, 165), fill=palette["gold"], width=2)
tracking(draw, "CHICAGO GPT", (430, 124), sans(23), palette["gold"], 4)
draw.text((427, 209), "GPT’s John", font=serif(68), fill=palette["title"], anchor="lt")
draw.text((427, 299), "Hancock’s Spire", font=serif(61), fill=palette["title"], anchor="lt")
tracking(draw, "ROOFTOP PROP", (430, 425), sans(23), palette["body"], 3)
draw.line((430, 485, 951, 485), fill=(146, 113, 66), width=1)
inset = (430, 537, 951, 864)
draw.rectangle(inset, fill=(18, 33, 57), outline=(100, 91, 78), width=1)
mount = Image.open(renders / "mount.png").convert("RGBA")
beacon = Image.open(renders / "tip.png").convert("RGBA")
cover.alpha_composite(mount, (436, 538))
cover.alpha_composite(beacon, (698, 538))
draw.line((690, 537, 690, 864), fill=(100, 91, 78), width=1)
draw.line((430, 914, 951, 914), fill=palette["gold"], width=2)
draw.text((429, 941), "by X_Bean_X", font=sans(24), fill=palette["body"], anchor="lt")
cover.convert("RGB").save(root / "Preview.png", optimize=True)

icon = Image.new("RGBA", (256, 256), (17, 31, 54, 255))
main.thumbnail((208, 236), Image.Resampling.LANCZOS)
icon.alpha_composite(main, ((256 - main.width) // 2, (256 - main.height) // 2))
icon.save(root / "Icon.png", optimize=True)
