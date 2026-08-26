from __future__ import annotations

import subprocess
import sys
import os
import random
from pathlib import Path
from typing import Any


class ExistingMediaPipelineRenderer:
    """Runs the repository's tested TTS/visual/audio/FFmpeg stages."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _run(self, *arguments: str) -> None:
        subprocess.run([sys.executable, *arguments], cwd=self.root, check=True)

    def render(self, job_path: Path) -> Path:
        provider = os.getenv("TTS_PROVIDER", "edge").casefold()
        narration = self.root / "output" / "narration.wav"
        if provider == "edge":
            import json
            from .config import Settings
            from .subtitles import SubtitleWriter
            from .tts import EdgeTTSNarrator, audio_duration
            job = json.loads(job_path.read_text(encoding="utf-8"))
            settings = Settings.from_env(self.root)
            narration = self.root / "output" / "narration.mp3"
            timing = self.root / "output" / "word-timings.json"
            timings = EdgeTTSNarrator(settings.tts_voice, settings.tts_rate).synthesize(job["story"], narration, timing)
            SubtitleWriter().from_json(
                timing, self.root / "output" / "captions.ass",
                emphasis_terms=[str(value) for value in job.get("important_terms", [])],
            )
            duration = audio_duration(narration)
            (self.root / "output" / "voice-report.json").write_text(json.dumps({
                "provider": "edge", "seed": None, "chunks": 1,
                "chunk_durations_seconds": [round(duration, 3)], "pauses_ms": [],
                "duration_seconds": round(duration, 3), "runtime_seconds": None,
                "narration_file": str(narration),
                "captions_file": str(self.root / "output" / "captions.ass"),
                "word_boundaries": len(timings),
            }, indent=2), encoding="utf-8")
        else:
            self._run("scripts/generate_voice.py", "--job", str(job_path), "--provider", provider)
        self._run("scripts/fetch_background.py", "--job", str(job_path))
        self._run("scripts/prepare_visual_track.py", "--job", str(job_path), "--narration", str(narration))
        self._run("scripts/generate_sfx.py", "--job", str(job_path), "--output", "output/horror-sfx.wav")
        self._run("scripts/generate_music.py", "--job", str(job_path), "--output", "output/horror-music.wav")
        self._run("scripts/render_video.py", "--job", str(job_path), "--narration", str(narration), "--captions", "output/captions.ass")
        import json
        report = json.loads((self.root / "output/render-report.json").read_text(encoding="utf-8"))
        return Path(report["output_file"])


class InteractiveRenderer:
    """Renders a complete 9:16 game from local procedural assets and FFmpeg."""

    SAFE_LEFT = 80
    SAFE_RIGHT = 870
    SAFE_TOP = 170
    SAFE_BOTTOM = 1540
    CENTER_X = (SAFE_LEFT + SAFE_RIGHT) // 2

    def __init__(self, root: Path, width: int = 1080, height: int = 1920,
                 fps: int = 30, ffmpeg: str | None = None) -> None:
        self.root = root
        self.width = width
        self.height = height
        self.fps = fps
        self.ffmpeg = ffmpeg or os.getenv("FFMPEG_BIN", "ffmpeg")

    @staticmethod
    def _font(size: int):
        from PIL import ImageFont
        candidates = (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
        )
        for candidate in candidates:
            if candidate.exists():
                return ImageFont.truetype(str(candidate), size=size)
        return ImageFont.load_default()

    def _fitted_font(self, draw: Any, text: str, maximum: int, start: int = 100):
        for size in range(start, 35, -4):
            font = self._font(size)
            box = draw.textbbox((0, 0), text, font=font, stroke_width=2)
            if box[2] - box[0] <= maximum:
                return font
        return self._font(36)

    def _background(self, game: dict[str, Any], rng: random.Random):
        from PIL import Image, ImageDraw
        from .effects import horror_texture, scanlines
        image = Image.new("RGBA", (self.width, self.height), (5, 7, 11, 255))
        draw = ImageDraw.Draw(image)
        # A readable corridor/room built from perspective planes.
        draw.polygon([(0, 0), (self.width, 0), (790, 1420), (280, 1420)], fill=(13, 17, 24, 255))
        draw.polygon([(0, 0), (280, 1420), (0, self.height)], fill=(7, 10, 15, 255))
        draw.polygon([(self.width, 0), (790, 1420), (self.width, self.height)], fill=(8, 10, 14, 255))
        draw.polygon([(280, 1420), (790, 1420), (self.width, self.height), (0, self.height)], fill=(10, 11, 14, 255))
        for y in range(360, 1440, 220):
            shade = 20 + (y // 220) % 2 * 7
            draw.line((60, y, 1020, y + 30), fill=(shade, shade + 3, shade + 8, 150), width=5)
        draw.rectangle((350, 500, 710, 1420), fill=(4, 5, 8, 255), outline=(52, 57, 65, 255), width=10)
        draw.ellipse((425, 630, 635, 900), fill=(0, 0, 0, 70))
        image = horror_texture(image, rng)
        if game["game_type"] == "moving_entity":
            image = scanlines(image)
        return image

    def _center_text(self, draw: Any, text: str, y: int, size: int = 92,
                     fill: str = "#f5f5f5", stroke: int = 5) -> None:
        maximum = self.SAFE_RIGHT - self.SAFE_LEFT
        font = self._fitted_font(draw, text, maximum, size)
        draw.text((self.CENTER_X, y), text, font=font, fill=fill, stroke_width=stroke,
                  stroke_fill="#080808", anchor="mm", align="center")

    def _draw_choices(self, draw: Any, game: dict[str, Any], reveal: bool = False) -> None:
        choices = game.get("choices", [])
        count = len(choices)
        gap = 28
        total_width = self.SAFE_RIGHT - self.SAFE_LEFT
        card_width = (total_width - gap * (count - 1)) // count
        top, bottom = 700, 1160
        for index, choice in enumerate(choices):
            left = self.SAFE_LEFT + index * (card_width + gap)
            right = left + card_width
            correct = reveal and choice["id"] == game.get("correct_choice")
            outline = "#d7b35c" if correct else "#9fa5ad"
            draw.rounded_rectangle((left, top, right, bottom), radius=18, fill="#11141a",
                                   outline=outline, width=12 if correct else 5)
            font = self._font(72)
            draw.text(((left + right) // 2, top + 95), f"[{choice['id']}]", font=font,
                      fill=outline, anchor="mm", stroke_width=3, stroke_fill="#050505")
            label_font = self._fitted_font(draw, str(choice["label"]), card_width - 30, 50)
            draw.text(((left + right) // 2, bottom - 90), str(choice["label"]), font=label_font,
                      fill="#f5f5f5", anchor="mm", stroke_width=3, stroke_fill="#050505")
            if game["game_type"] in {"choose_door", "escape_room"}:
                draw.rectangle((left + 32, top + 155, right - 32, bottom - 165), fill="#08090c",
                               outline="#343841", width=5)
                draw.ellipse((right - 62, (top + bottom) // 2, right - 45, (top + bottom) // 2 + 17),
                             fill="#b89b55")

    def _draw_search(self, draw: Any, game: dict[str, Any], reveal: bool) -> None:
        x, y = (int(value) for value in game["target_position"])
        if game["game_type"] == "moving_entity":
            for index, entity_x in enumerate((250, 475, 700), 1):
                draw.ellipse((entity_x - 60, 760, entity_x + 60, 900), fill="#101218", outline="#626772")
                draw.polygon([(entity_x - 85, 1240), (entity_x - 55, 900), (entity_x + 55, 900),
                              (entity_x + 85, 1240)], fill="#090a0d", outline="#555a63")
                self._center_text(draw, f"0{index}", 1310, 48, "#aeb3bb", 3)
            x, y = 700, 820
        elif game["game_type"] == "spot_change":
            draw.ellipse((x - 100, y - 100, x + 100, y + 100), fill="#11141a", outline="#8d9198", width=7)
            hand_angle = -45 if reveal else -90
            end_x = x + (70 if hand_angle == -45 else 0)
            end_y = y - 70
            draw.line((x, y, end_x, end_y), fill="#d8d8d8", width=8)
        else:
            # The face is visible but deliberately low contrast during the search.
            shade = "#444851" if reveal else "#171a20"
            draw.ellipse((x - 55, y - 75, x + 55, y + 75), fill=shade)
            draw.ellipse((x - 28, y - 22, x - 10, y - 4), fill="#ddd7c6" if reveal else "#262a32")
            draw.ellipse((x + 10, y - 22, x + 28, y - 4), fill="#ddd7c6" if reveal else "#262a32")
        if reveal:
            draw.ellipse((x - 125, y - 135, x + 125, y + 135), outline="#dc1f2e", width=14)

    def _frame(self, game: dict[str, Any], phase: dict[str, Any], index: int):
        from PIL import ImageDraw
        rng = random.Random(f"{game['setting']}:{game['monster']}:{index}")
        image = self._background(game, rng)
        draw = ImageDraw.Draw(image)
        kind = phase["kind"]
        draw.rounded_rectangle((self.SAFE_LEFT - 20, self.SAFE_TOP - 40, self.SAFE_RIGHT + 20, 430),
                               radius=28, fill=(0, 0, 0, 150))
        if kind == "hook":
            self._center_text(draw, str(phase["text"]), 285, 94, "#dc1f2e")
            self._center_text(draw, "CHOOSE NOW", 650, 68)
        elif kind == "challenge":
            self._center_text(draw, str(phase["text"]), 270, 84)
        elif kind == "countdown":
            self._center_text(draw, "TIME IS RUNNING OUT", 265, 62, "#dc1f2e")
            self._center_text(draw, str(phase["number"]), 520, 210, "#f5f5f5", 9)
        elif kind == "reveal":
            self._center_text(draw, "ANSWER", 245, 68, "#dc1f2e")
            self._center_text(draw, str(phase["text"]), 1420, 62)
        elif kind == "outcome":
            self._center_text(draw, str(phase["text"]), 520, 112, "#d7b35c")
            self._center_text(draw, "DID YOU CHOOSE RIGHT?", 720, 58)
        else:
            self._center_text(draw, str(phase["text"]), 530, 66, "#dc1f2e")
        if game["game_type"] in {"choose_door", "escape_room", "safe_object"} and kind in {
            "challenge", "countdown", "reveal"
        }:
            self._draw_choices(draw, game, reveal=kind == "reveal")
        elif game["game_type"] in {"find_ghost", "spot_change", "moving_entity"} and kind in {
            "challenge", "countdown", "reveal"
        }:
            self._draw_search(draw, game, reveal=kind == "reveal")
        footer_font = self._font(30)
        draw.text((self.SAFE_LEFT, self.SAFE_BOTTOM), game["setting"].upper(), font=footer_font,
                  fill="#737985", stroke_width=2, stroke_fill="#050505")
        return image.convert("RGB")

    def render(self, game: dict[str, Any], phases: list[dict[str, Any]], destination: Path) -> dict[str, Any]:
        from .audio import InteractiveAudioGenerator
        work = destination.parent / "interactive-frames"
        work.mkdir(parents=True, exist_ok=True)
        frame_paths: list[Path] = []
        for index, phase in enumerate(phases):
            path = work / f"frame-{index:02d}.png"
            self._frame(game, phase, index).save(path, optimize=True)
            frame_paths.append(path)
        timeline = work / "timeline.txt"
        entries: list[str] = []
        for path, phase in zip(frame_paths, phases):
            escaped = path.resolve().as_posix().replace("'", "'\\''")
            entries.extend((f"file '{escaped}'", f"duration {float(phase['duration']):.3f}"))
        entries.append(f"file '{frame_paths[-1].resolve().as_posix()}'")
        timeline.write_text("\n".join(entries) + "\n", encoding="utf-8")
        total = sum(float(phase["duration"]) for phase in phases)
        countdown_start = sum(float(phase["duration"]) for phase in phases[:2])
        reveal_at = countdown_start + int(game["countdown_seconds"])
        audio = destination.parent / "interactive-audio.wav"
        InteractiveAudioGenerator().generate(audio, total, countdown_start,
                                             int(game["countdown_seconds"]), reveal_at,
                                             f"{game['setting']}:{game['hook']}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(timeline),
            "-i", str(audio), "-t", f"{total:.3f}",
            "-vf", f"fps={self.fps},scale={self.width}:{self.height}:flags=lanczos,format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(destination),
        ]
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
        log = destination.parent / "render.log"
        log.write_text("$ " + " ".join(command) + "\n\n" + result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"FFmpeg render failed; see {log}")
        return {"output_file": str(destination), "duration": total, "frames": len(frame_paths),
                "render_log": str(log)}
