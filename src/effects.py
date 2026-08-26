from __future__ import annotations

import random

from PIL import Image, ImageDraw, ImageFilter


def horror_texture(image: Image.Image, rng: random.Random) -> Image.Image:
    """Cheap procedural fog, grain, and vignette; no downloaded assets required."""
    width, height = image.size
    noise = Image.effect_noise((max(1, width // 5), max(1, height // 5)), rng.uniform(18, 34))
    noise = noise.resize(image.size).convert("L")
    grain = Image.merge("RGBA", (noise, noise, noise, noise.point(lambda value: value // 8)))
    image = Image.alpha_composite(image.convert("RGBA"), grain)
    fog = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(fog)
    for _ in range(6):
        x = rng.randint(-300, width)
        y = rng.randint(250, height)
        draw.ellipse((x, y, x + rng.randint(400, 900), y + rng.randint(120, 300)), fill=(105, 120, 135, 14))
    image = Image.alpha_composite(image, fog.filter(ImageFilter.GaussianBlur(70)))
    vignette = Image.new("L", image.size, 255)
    mask = ImageDraw.Draw(vignette)
    for inset in range(0, 280, 20):
        alpha = max(0, 210 - inset)
        mask.rectangle((inset, inset, width - inset, height - inset), outline=alpha, width=24)
    dark = Image.new("RGBA", image.size, (0, 0, 0, 225))
    dark.putalpha(vignette.point(lambda value: 255 - value))
    return Image.alpha_composite(image, dark)


def scanlines(image: Image.Image, opacity: int = 22) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(0, image.height, 7):
        draw.line((0, y, image.width, y), fill=(0, 0, 0, opacity), width=2)
    return Image.alpha_composite(image.convert("RGBA"), overlay)
