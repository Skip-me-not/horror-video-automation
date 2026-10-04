from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int, text: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    myanmar = any("\u1000" <= char <= "\u109f" for char in text)
    paths = ([Path("/usr/share/fonts/truetype/noto/NotoSansMyanmar-Regular.ttf"),
              Path("C:/Windows/Fonts/mmrtext.ttf")] if myanmar else [
                  Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                  Path("C:/Windows/Fonts/arialbd.ttf")])
    for path in paths:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _fit_lines(draw: ImageDraw.ImageDraw, value: str, limit: int, font: ImageFont.ImageFont,
               max_lines: int = 3) -> str:
    words = value.split() if " " in value else list(value)
    lines: list[str] = []
    current = ""
    separator = " " if " " in value else ""
    for word in words:
        trial = (current + separator + word).strip()
        if draw.textbbox((0, 0), trial, font=font)[2] > limit and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return "\n".join(lines[:max_lines])


def generate(person: str, hook: str, destination: Path, count: int = 24) -> list[dict]:
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    palette = [(23, 9, 45), (10, 27, 48), (41, 9, 37), (12, 34, 42)]
    for index in range(count):
        image = Image.new("RGB", (1080, 1920), palette[index % len(palette)])
        draw = ImageDraw.Draw(image, "RGBA")
        for stripe in range(12):
            y = stripe * 160
            draw.rectangle((0, y, 1080, y + 80), fill=(220, 45, 150, 7 + (stripe % 4) * 5))
        for dot in range(25):
            x = (dot * 277 + index * 161) % 1080
            y = (dot * 419 + index * 97) % 1920
            radius = 3 + dot % 10
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 255, 255, 18))
        draw.text((80, 170), person[:35].upper(), font=_font(45, person), fill=(255, 185, 220, 255))
        draw.rounded_rectangle((80, 260, 1000, 268), radius=4, fill=(235, 65, 160, 200))
        if index == 0:
            font = _font(70, hook)
            wrapped = _fit_lines(draw, hook.upper(), 900, font)
            draw.multiline_text((540, 650), wrapped, font=font, fill="white", anchor="ma",
                                align="center", spacing=24, stroke_width=5, stroke_fill=(0, 0, 0))
        else:
            center = 1140
            for bar in range(19):
                height = int(20 + 85 * abs(math.sin(index * 0.8 + bar * 0.56)))
                x = 90 + bar * 50
                draw.rounded_rectangle((x, center - height, x + 22, center + height), radius=11,
                                       fill=(255, 78, 174, 75))
        draw.text((540, 1775), "Lululala", font=_font(38, "Lululala"), fill="white", anchor="mm")
        path = destination / f"card-{index:03d}.png"
        image.save(path, optimize=True)
        records.append({"id": f"telegram-card-{index}", "path": str(path), "type": "image",
                        "license": "original-generated", "approved": True,
                        "source_url": "", "attribution": "Original Lululala graphic"})
    return records
