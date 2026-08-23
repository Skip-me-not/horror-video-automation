from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _chunk(items: list[dict[str, Any]], size: int = 3) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for item in items:
        current.append(item)
        terminal = str(item.get("text", "")).endswith((".", "!", "?", ","))
        if len(current) >= size or (len(current) >= 2 and terminal):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


class SubtitleWriter:
    def from_timings(self, timings: list[dict[str, Any]], output: Path) -> Path:
        if not timings:
            raise ValueError("word timings are empty")
        header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,DejaVu Sans,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,7,2,5,70,70,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines = [header]
        for words in _chunk(timings):
            start = float(words[0]["offset"])
            last = words[-1]
            end = float(last["offset"]) + float(last.get("duration", 0.2))
            text = " ".join(str(word["text"]) for word in words).upper()
            styled = r"{\fad(35,70)\fscx103\fscy103}" + _escape(text)
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Main,,0,0,0,,{styled}\n")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("".join(lines), encoding="utf-8")
        return output

    def from_json(self, timing_path: Path, output: Path) -> Path:
        return self.from_timings(json.loads(timing_path.read_text(encoding="utf-8")), output)
