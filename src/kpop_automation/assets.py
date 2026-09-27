from __future__ import annotations

import json
import math
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def load_approved_assets(root: Path) -> dict[str, dict[str, Any]]:
    manifest = json.loads((root / "assets" / "approved" / "manifest.json").read_text(encoding="utf-8"))
    approved: dict[str, dict[str, Any]] = {}
    for item in manifest.get("assets", []):
        required = {"id", "path", "license", "source_url", "attribution", "approved_at"}
        if not required.issubset(item) or item["license"] in {"", "unknown", "unverified"}:
            raise ValueError(f"invalid approved asset record: {item.get('id', 'unknown')}")
        path = (root / "assets" / "approved" / item["path"]).resolve()
        if not path.is_file() or root.resolve() not in path.parents:
            raise ValueError(f"approved asset file is missing or unsafe: {item['path']}")
        approved[str(item["id"])] = {**item, "resolved_path": str(path)}
    return approved


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _wrapped(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(" ".join(text.split()), width=width, break_long_words=False))


def generate_cards(topic: dict[str, Any], script: dict[str, Any], destination: Path) -> list[dict[str, Any]]:
    destination.mkdir(parents=True, exist_ok=True)
    claims = list(topic.get("claims", [])) or [topic["title"]]
    claim_words = " ".join(claims).split()
    snippets = [" ".join(claim_words[start:start + 8]) for start in range(0, len(claim_words), 8)]
    texts = [script["hook"], topic["title"], *snippets[:17], "Sources linked below"]
    records: list[dict[str, Any]] = []
    palettes = [(15, 7, 38), (36, 8, 58), (7, 25, 52), (35, 5, 30), (8, 30, 38)]
    for index, text in enumerate(texts):
        width, height = 1080, 1920
        base = Image.new("RGB", (width, height), palettes[index % len(palettes)])
        draw = ImageDraw.Draw(base, "RGBA")
        for band in range(12):
            y0 = band * 160
            alpha = 18 + band * 2
            draw.rectangle((0, y0, width, y0 + 160), fill=(255, 35 + band * 5, 150, alpha))
        for dot in range(42):
            x = (dot * 193 + index * 71) % width
            y = (dot * 317 + index * 113) % height
            radius = 4 + (dot % 8)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 255, 255, 30))
        draw.rounded_rectangle((70, 305, 1010, 1550), radius=48, fill=(5, 5, 18, 178), outline=(255, 65, 170, 220), width=5)
        label = topic["category"].replace("_", " ").upper()
        draw.text((110, 360), label, font=_font(44, True), fill=(255, 76, 174))
        content = _wrapped(" ".join(str(text).split()[:11]), 19)
        draw.multiline_text((110, 500), content, font=_font(70 if index == 0 else 65, True), fill="white", spacing=18)
        draw.text((110, 1450), str(topic["entity"]).upper(), font=_font(46, True), fill=(255, 185, 225))
        draw.text((540, 1790), "Lululala", anchor="mm", font=_font(34, True), fill=(255, 255, 255, 180))
        progress = math.floor((index + 1) / len(texts) * 860)
        draw.rounded_rectangle((110, 1640, 970, 1654), radius=7, fill=(255, 255, 255, 45))
        draw.rounded_rectangle((110, 1640, 110 + progress, 1654), radius=7, fill=(255, 65, 170, 255))
        path = destination / f"scene-{index + 1}.png"
        base.save(path, optimize=True)
        records.append({
            "id": f"generated-card-{index + 1}", "path": str(path), "license": "original-generated",
            "source_url": "", "attribution": "Original Lululala motion graphic", "approved": True,
        })
    return records
