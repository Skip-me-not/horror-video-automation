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

    def _background(self, game: dict[str, Any], rng: random.Random, kind: str):
        from PIL import Image, ImageDraw, ImageEnhance, ImageOps
        from .effects import horror_texture, scanlines
        asset_names = {
            "choose_door": "hospital-two-doors.png",
            "find_ghost": "haunted-bedroom.png", "spot_change": "haunted-bedroom.png",
            "escape_room": "haunted-bedroom.png", "safe_object": "haunted-bedroom.png",
            "moving_entity": "cctv-parking-entities.png",
        }
        asset = self.root / "assets" / "interactive" / asset_names[game["game_type"]]
        if asset.is_file():
            source = Image.open(asset).convert("RGB")
            image = ImageOps.fit(source, (self.width, self.height), method=Image.Resampling.LANCZOS).convert("RGBA")
            image = ImageEnhance.Contrast(image).enhance(1.12)
            image = ImageEnhance.Color(image).enhance(0.82)
        else:
            image = Image.new("RGBA", (self.width, self.height), (5, 7, 11, 255))
            draw = ImageDraw.Draw(image)
            draw.polygon([(0, 0), (self.width, 0), (790, 1500), (280, 1500)], fill=(13, 17, 24, 255))
            draw.rectangle((260, 520, 480, 1450), fill=(3, 4, 7), outline=(70, 74, 82), width=8)
            draw.rectangle((590, 520, 810, 1450), fill=(3, 4, 7), outline=(70, 74, 82), width=8)
            image = horror_texture(image, rng)
        tint = Image.new("RGBA", image.size, (0, 0, 0, 0))
        tint_draw = ImageDraw.Draw(tint)
        if kind == "hook":
            tint_draw.rectangle((0, 0, self.width, self.height), fill=(95, 0, 8, 52))
        elif kind in {"outcome", "loop"}:
            tint_draw.rectangle((0, 0, self.width, self.height), fill=(0, 0, 0, 88))
        else:
            tint_draw.rectangle((0, 0, self.width, self.height), fill=(0, 8, 18, 25))
        image = Image.alpha_composite(image, tint)
        if game["game_type"] == "moving_entity":
            image = scanlines(image, opacity=34)
        return image

    @staticmethod
    def _wrap(text: str, limit: int = 23) -> str:
        words = text.split()
        lines: list[str] = []
        current: list[str] = []
        for word in words:
            candidate = " ".join(current + [word])
            if current and len(candidate) > limit:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))
        return "\n".join(lines[:3])

    def _center_text(self, draw: Any, text: str, y: int, size: int = 92,
                     fill: str = "#f5f5f5", stroke: int = 5, wrap: int = 23) -> None:
        rendered = self._wrap(text, wrap)
        maximum = self.SAFE_RIGHT - self.SAFE_LEFT
        font = self._font(size)
        while font.size > 36:
            box = draw.multiline_textbbox((0, 0), rendered, font=font, stroke_width=stroke,
                                          spacing=6, align="center")
            if box[2] - box[0] <= maximum:
                break
            font = self._font(font.size - 4)
        draw.multiline_text((self.CENTER_X, y), rendered, font=font, fill=fill, stroke_width=stroke,
                            stroke_fill="#050506", anchor="mm", align="center", spacing=6)

    def _draw_hud(self, draw: Any, game: dict[str, Any], phase: dict[str, Any], index: int,
                  total_phases: int) -> None:
        label_font = self._font(27)
        draw.text((self.SAFE_LEFT, 85), f"NIGHT TEST  //  LEVEL {int(game['level']):02d}",
                  font=label_font, fill="#d7d9de", stroke_width=2, stroke_fill="#050505")
        bar_y = 138
        draw.rounded_rectangle((self.SAFE_LEFT, bar_y, self.SAFE_RIGHT, bar_y + 10), radius=5, fill=(50, 53, 60, 190))
        progress = max(18, round((self.SAFE_RIGHT - self.SAFE_LEFT) * (index + 1) / total_phases))
        draw.rounded_rectangle((self.SAFE_LEFT, bar_y, self.SAFE_LEFT + progress, bar_y + 10),
                               radius=5, fill="#d81f32")
        if phase["kind"] == "countdown":
            number = int(phase["number"])
            draw.ellipse((self.CENTER_X - 76, 195, self.CENTER_X + 76, 347),
                         fill=(3, 4, 7, 205), outline="#e3263c", width=8)
            font = self._font(105)
            draw.text((self.CENTER_X, 267), str(number), font=font, fill="#ffffff", anchor="mm",
                      stroke_width=6, stroke_fill="#050505")

    def _draw_choices(self, draw: Any, game: dict[str, Any], reveal: bool = False) -> None:
        choices = game.get("choices", [])
        positions = (260, 700) if len(choices) == 2 else (175, 475, 775)
        y = 1125 if len(choices) == 2 else 1210
        for choice, x in zip(choices, positions):
            correct = reveal and choice["id"] == game.get("correct_choice")
            wrong = reveal and not correct
            outline = "#e5bd55" if correct else ("#8b2430" if wrong else "#e8e9eb")
            fill = (20, 21, 26, 225 if reveal else 185)
            left, right = x - 125, x + 125
            draw.rounded_rectangle((left, y - 58, right, y + 58), radius=24, fill=fill,
                                   outline=outline, width=10 if correct else 4)
            label = f"{choice['id']}  {choice['label']}"
            font = self._fitted_font(draw, label, 220, 47)
            draw.text((x, y), label, font=font, fill="#ffffff" if not wrong else "#a9a9ad",
                      anchor="mm", stroke_width=3, stroke_fill="#050505")
            if correct:
                safe_font = self._font(29)
                draw.text((x, y - 88), "SAFE", font=safe_font, fill="#e5bd55", anchor="mm",
                          stroke_width=3, stroke_fill="#050505")

    def _draw_search(self, draw: Any, game: dict[str, Any], reveal: bool, changed: bool = False) -> None:
        x, y = (int(value) for value in game["target_position"])
        game_type = game["game_type"]
        if game_type == "moving_entity":
            for label, label_x in (("01", 265), ("02", 580), ("03", 870)):
                draw.rounded_rectangle((label_x - 48, 1090, label_x + 48, 1144), radius=12,
                                       fill=(0, 0, 0, 180), outline="#8ea29a", width=3)
                draw.text((label_x, 1117), label, font=self._font(30), fill="#d9e4df", anchor="mm")
        elif game_type == "spot_change":
            if changed or reveal:
                if "MIRROR" in game["target"]:
                    draw.line((x - 38, y - 90, x + 25, y + 75), fill="#dce8ef", width=7)
                    draw.line((x + 20, y - 60, x - 45, y + 15), fill="#dce8ef", width=5)
                elif "DOLL" in game["target"]:
                    draw.ellipse((x - 35, y - 18, x - 12, y + 5), fill="#e4d9bd")
                    draw.ellipse((x + 12, y - 18, x + 35, y + 5), fill="#e4d9bd")
                else:
                    draw.arc((x - 80, y - 90, x + 80, y + 90), 200, 340, fill="#dce8ef", width=8)
        elif game_type == "find_ghost":
            # The target is already embedded in the cinematic bedroom plate.
            # Only add barely visible eye reflections before the answer, then a
            # clean locator on reveal; this avoids a pasted-on graphic look.
            if not reveal:
                draw.ellipse((x - 12, y - 7, x - 3, y + 1), fill=(140, 150, 150, 65))
                draw.ellipse((x + 3, y - 7, x + 12, y + 1), fill=(140, 150, 150, 65))
        else:
            shade = "#b9b5aa" if reveal else "#262a31"
            draw.ellipse((x - 48, y - 66, x + 48, y + 66), fill=shade, outline="#090a0c")
            eye = "#160408" if reveal else "#343942"
            draw.ellipse((x - 26, y - 16, x - 8, y + 2), fill=eye)
            draw.ellipse((x + 8, y - 16, x + 26, y + 2), fill=eye)
        if reveal:
            draw.ellipse((x - 112, y - 122, x + 112, y + 122), outline="#e3263c", width=13)
            draw.line((x - 150, y, x - 115, y), fill="#e3263c", width=8)
            draw.line((x + 115, y, x + 150, y), fill="#e3263c", width=8)

    def _frame(self, game: dict[str, Any], phase: dict[str, Any], index: int, total_phases: int):
        from PIL import Image, ImageDraw, ImageFilter
        kind = phase["kind"]
        rng = random.Random(f"{game['setting']}:{game['monster']}:{index}")
        image = self._background(game, rng, kind)
        draw = ImageDraw.Draw(image, "RGBA")
        self._draw_hud(draw, game, phase, index, total_phases)
        # Localized text scrims protect readability without hiding the cinematic scene.
        if kind in {"hook", "challenge", "choice", "observe", "warning", "decision",
                    "escalation", "reveal", "outcome", "loop"}:
            draw.rounded_rectangle((self.SAFE_LEFT - 20, 175, self.SAFE_RIGHT + 20, 480),
                                   radius=30, fill=(0, 0, 0, 145))
        if kind == "hook":
            self._center_text(draw, str(phase["text"]), 305, 102, "#ffffff", 7, 20)
            # A blurred, half-hidden threat interrupts the first frame while the
            # cinematic scene remains visible. The tiny eyes reward a second look.
            threat = Image.new("RGBA", image.size, (0, 0, 0, 0))
            threat_draw = ImageDraw.Draw(threat, "RGBA")
            threat_draw.ellipse((self.CENTER_X - 72, 720, self.CENTER_X + 72, 1010),
                                fill=(0, 0, 0, 135))
            threat = threat.filter(ImageFilter.GaussianBlur(24))
            image = Image.alpha_composite(image, threat)
            draw = ImageDraw.Draw(image, "RGBA")
            eye_y = 827
            draw.ellipse((self.CENTER_X - 46, eye_y, self.CENTER_X - 19, eye_y + 15),
                         fill=(239, 31, 48, 215))
            draw.ellipse((self.CENTER_X + 19, eye_y, self.CENTER_X + 46, eye_y + 15),
                         fill=(239, 31, 48, 215))
        elif kind == "challenge":
            self._center_text(draw, str(phase["text"]), 310, 78, "#ffffff", 6, 22)
            self._center_text(draw, "LOCK YOUR ANSWER", 525, 39, "#e3263c", 3, 28)
        elif kind in {"choice", "observe"}:
            self._center_text(draw, str(phase["text"]), 300, 88, "#ffffff", 6, 24)
            self._center_text(draw, "MEMORIZE EVERY DETAIL", 440, 37, "#e3263c", 3, 30)
        elif kind == "warning":
            self._center_text(draw, str(phase["text"]), 300, 76, "#ffffff", 6, 22)
            self._center_text(draw, "IT MAY HAVE MOVED", 440, 39, "#e3263c", 3, 28)
        elif kind == "decision":
            self._center_text(draw, str(phase["text"]), 300, 78, "#ffffff", 6, 22)
            self._center_text(draw, "DON'T SECOND-GUESS IT", 440, 37, "#e5bd55", 3, 28)
        elif kind == "escalation":
            self._center_text(draw, str(phase["text"]), 300, 78, "#ffffff", 6, 22)
            self._center_text(draw, "THE TIMER STARTS NOW", 440, 37, "#e3263c", 3, 27)
        elif kind == "countdown":
            self._center_text(draw, "LOCK IT IN", 410, 48, "#ffffff", 4, 24)
        elif kind == "reveal":
            self._center_text(draw, "ANSWER", 245, 45, "#e3263c", 4, 20)
            self._center_text(draw, str(phase["text"]), 360, 64, "#ffffff", 5, 24)
        elif kind == "outcome":
            self._center_text(draw, str(phase["text"]), 320, 68, "#ffffff", 6, 22)
            self._center_text(draw, "DID YOU SURVIVE?", 525, 49, "#e5bd55", 4, 24)
        else:
            self._center_text(draw, str(phase["text"]), 320, 67, "#ffffff", 6, 22)
            self._center_text(draw, "LOOK AGAIN", 530, 45, "#e3263c", 4, 24)

        interactive_kinds = {"challenge", "choice", "observe", "warning", "decision",
                             "escalation", "countdown", "reveal"}
        if game["game_type"] in {"choose_door", "escape_room", "safe_object"} and kind in interactive_kinds:
            self._draw_choices(draw, game, reveal=kind == "reveal")
        elif game["game_type"] in {"find_ghost", "spot_change", "moving_entity"} and kind in interactive_kinds:
            changed = game["game_type"] == "spot_change" and kind == "countdown" and int(phase.get("number", 9)) <= 2
            self._draw_search(draw, game, reveal=kind == "reveal", changed=changed)
        if kind == "loop":
            draw.ellipse((self.CENTER_X - 52, 793, self.CENTER_X - 20, 808), fill=(225, 26, 43, 215))
            draw.ellipse((self.CENTER_X + 20, 793, self.CENTER_X + 52, 808), fill=(225, 26, 43, 215))
        return image.convert("RGB")

    def render(self, game: dict[str, Any], phases: list[dict[str, Any]], destination: Path) -> dict[str, Any]:
        from .audio import InteractiveAudioGenerator
        work = destination.parent / "interactive-frames"
        work.mkdir(parents=True, exist_ok=True)
        frame_paths: list[Path] = []
        for index, phase in enumerate(phases):
            path = work / f"frame-{index:02d}.jpg"
            self._frame(game, phase, index, len(phases)).save(path, quality=94, optimize=True)
            frame_paths.append(path)
        total = sum(float(phase["duration"]) for phase in phases)
        countdown_index = next(index for index, phase in enumerate(phases) if phase["kind"] == "countdown")
        countdown_start = sum(float(phase["duration"]) for phase in phases[:countdown_index])
        reveal_at = countdown_start + int(game["countdown_seconds"])
        audio = destination.parent / "interactive-audio.wav"
        InteractiveAudioGenerator().generate(audio, total, countdown_start,
                                             int(game["countdown_seconds"]), reveal_at,
                                             f"{game['setting']}:{game['hook']}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [self.ffmpeg, "-y"]
        for path, phase in zip(frame_paths, phases):
            command.extend(["-loop", "1", "-framerate", str(self.fps), "-t",
                            f"{float(phase['duration']):.3f}", "-i", str(path)])
        command.extend(["-i", str(audio)])
        filters: list[str] = []
        video_labels: list[str] = []
        scaled_width = self.width + 80
        scaled_height = round(scaled_width * self.height / self.width)
        for index, phase in enumerate(phases):
            duration = float(phase["duration"])
            amplitude = 16 if phase["kind"] in {"hook", "reveal"} else (9 if phase["kind"] in {"warning", "escalation"} else 6)
            frequency = 10.0 if phase["kind"] == "hook" else 1.1 + (index % 3) * 0.22
            label = f"v{index}"
            filters.append(
                f"[{index}:v]scale={scaled_width}:{scaled_height}:flags=lanczos,"
                f"crop={self.width}:{self.height}:"
                f"x='(iw-ow)/2+{amplitude}*sin(t*{frequency})':"
                f"y='(ih-oh)/2+{max(3, amplitude // 2)}*cos(t*{frequency * 0.83:.3f})',"
                f"eq=contrast=1.08:saturation=0.86:brightness='0.012*sin(t*7)',"
                f"fps={self.fps},trim=duration={duration:.3f},setpts=PTS-STARTPTS[{label}]"
            )
            video_labels.append(f"[{label}]")
        filters.append("".join(video_labels) + f"concat=n={len(phases)}:v=1:a=0,format=yuv420p[vout]")
        filters.append(
            f"[{len(phases)}:a]highpass=f=25,lowpass=f=12000,"
            "loudnorm=I=-18:TP=-1.5:LRA=10,aresample=48000[aout]"
        )
        command.extend([
            "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
            "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-shortest", str(destination),
        ])
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
        log = destination.parent / "render.log"
        log.write_text("$ " + " ".join(command) + "\n\n" + result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"FFmpeg render failed; see {log}")
        return {"output_file": str(destination), "duration": total, "keyframes": len(frame_paths),
                "motion_frames": round(total * self.fps), "render_log": str(log)}
