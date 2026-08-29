from __future__ import annotations

import re
import textwrap
from pathlib import Path

from .captions import Caption


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{fraction:02d}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _highlight(words: list[str], triggers: set[str]) -> str:
    rendered: list[str] = []
    for word in words:
        normalized = re.sub(r"[^a-z0-9]", "", word.casefold())
        variants = {normalized, normalized.rstrip("s"), normalized.rstrip("ed"), normalized.rstrip("ing")}
        if normalized and variants.intersection(triggers):
            rendered.append(r"{\1c&H3030E3&}" + _escape(word.upper()) + r"{\1c&HFFFFFF&}")
        else:
            rendered.append(_escape(word.upper()))
    return " ".join(rendered)


def _wrap_hook(value: str, width: int = 18) -> str:
    lines = textwrap.wrap(
        value.upper(),
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return r"\N".join(_escape(line) for line in lines)


def write_ass(destination: Path, captions: list[Caption], hook: dict[str, object],
              trigger_words: set[str], width: int = 1080, height: int = 1920) -> Path:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Caption,DejaVu Sans,76,&H00FFFFFF,&H000000FF,&H00101010,&H78000000,-1,0,0,0,100,100,0,0,1,6,2,2,90,90,310,1
Style: Hook,DejaVu Sans,82,&H00FFFFFF,&H000000FF,&H00101010,&HA0000000,-1,0,0,0,100,100,0,0,1,7,3,5,100,100,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events = [
        f"Dialogue: 2,{_ass_time(0)},{_ass_time(float(hook['duration']))},Hook,,0,0,0,,"
        + r"{\fad(80,120)\t(0,180,\fscx103\fscy103)}" + _wrap_hook(str(hook["text"]))
    ]
    for caption in captions:
        words = caption.text.split()
        if not words:
            continue
        groups = [words[index:index + 4] for index in range(0, len(words), 4)]
        duration = max(0.12, caption.end - caption.start)
        for index, group in enumerate(groups):
            start = caption.start + duration * index / len(groups)
            end = caption.start + duration * (index + 1) / len(groups)
            text = _highlight(group, trigger_words)
            events.append(f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Caption,,0,0,0,,"
                          + r"{\fad(50,70)\t(0,100,\fscx108\fscy108)}" + text)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return destination
