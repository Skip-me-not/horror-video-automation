from __future__ import annotations

import json
import re
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


def _font_size(words: list[dict[str, Any]]) -> int:
    """Keep captions inside a 1080px portrait safe area, even for long words."""
    characters = len(" ".join(str(word.get("text", "")) for word in words))
    longest_word = max((len(str(word.get("text", ""))) for word in words), default=0)
    if characters >= 25 or longest_word > 14:
        return 50
    if characters > 20 or longest_word > 11:
        return 56
    if characters > 15:
        return 62
    return 68


class SubtitleWriter:
    def from_timings(self, timings: list[dict[str, Any]], output: Path,
                     emphasis_terms: list[str] | None = None, *,
                     hook_text: str = "", hook_duration: float = 0.0) -> Path:
        if not timings:
            raise ValueError("word timings are empty")
        header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,DejaVu Sans,68,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,5,1,5,120,120,0,1
Style: Hook,DejaVu Sans,78,&H000000FF,&H000000FF,&H00101010,&HA0000000,-1,0,0,0,100,100,1,0,1,7,2,5,110,110,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines = [header]
        if hook_text and hook_duration > 0:
            hook_words = hook_text.upper().split()
            wrapped = r"\N".join(
                _escape(" ".join(hook_words[index:index + 4]))
                for index in range(0, len(hook_words), 4)
            )
            lines.append(
                f"Dialogue: 2,{_ass_time(0)},{_ass_time(hook_duration)},Hook,,0,0,0,,"
                + r"{\fad(70,100)\t(0,160,\fscx104\fscy104)}" + wrapped + "\n"
            )
        for words in _chunk(timings):
            start = float(words[0]["offset"])
            last = words[-1]
            end = float(last["offset"]) + float(last.get("duration", 0.2))
            terms = {
                token.casefold() for phrase in (emphasis_terms or [])
                for token in re.findall(r"[A-Za-z0-9]+", phrase)
                if len(token) > 2
            }
            rendered: list[str] = []
            for word in words:
                value = str(word["text"]).upper()
                normalized = re.sub(r"[^A-Za-z0-9]", "", value).casefold()
                if normalized in terms or any(character.isdigit() for character in normalized):
                    rendered.append(r"{\c&H000000FF&}" + _escape(value) + r"{\c&H00FFFFFF&}")
                else:
                    rendered.append(_escape(value))
            # The explicit size is a final guard for unusually long names/dates.
            # libass can now wrap at the 120px safe margins because WrapStyle is 0.
            styled = rf"{{\fad(35,70)\fs{_font_size(words)}}}" + " ".join(rendered)
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Main,,0,0,0,,{styled}\n")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("".join(lines), encoding="utf-8")
        return output

    def from_json(self, timing_path: Path, output: Path,
                  emphasis_terms: list[str] | None = None, *,
                  hook_text: str = "", hook_duration: float = 0.0) -> Path:
        return self.from_timings(
            json.loads(timing_path.read_text(encoding="utf-8")), output, emphasis_terms,
            hook_text=hook_text, hook_duration=hook_duration,
        )
