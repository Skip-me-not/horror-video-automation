from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Caption:
    start: float
    end: float
    text: str


_TAG = re.compile(r"<[^>]+>")


def _seconds(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_vtt(path: Path) -> list[Caption]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    captions: list[Caption] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if "-->" not in line:
            index += 1
            continue
        start_raw, end_raw = (part.strip().split()[0] for part in line.split("-->", 1))
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index].strip())
            index += 1
        text = html.unescape(_TAG.sub("", " ".join(text_lines)))
        text = re.sub(r"\s+", " ", text).strip()
        if text and (not captions or text != captions[-1].text or _seconds(start_raw) > captions[-1].end + 0.2):
            captions.append(Caption(_seconds(start_raw), _seconds(end_raw), text))
        index += 1
    return captions


def slice_captions(captions: list[Caption], start: float, end: float, speed: float) -> list[Caption]:
    result: list[Caption] = []
    for caption in captions:
        if caption.end <= start or caption.start >= end:
            continue
        result.append(Caption(max(0.0, caption.start - start) / speed,
                              (min(end, caption.end) - start) / speed,
                              caption.text))
    return result
