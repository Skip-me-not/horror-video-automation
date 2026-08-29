from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


_PROBE_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}


def run(command: list[str], *, cwd: Path | None = None, check: bool = True,
        timeout: float = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=check, capture_output=True, text=True,
                          timeout=timeout)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ffprobe(path: Path, binary: str | None = None) -> dict[str, Any]:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    fallback = Path(__file__).resolve().parents[1] / ".test-tools" / "ffprobe.exe"
    executable = binary or os.getenv("FFPROBE_BIN") or shutil.which("ffprobe")
    if not executable and fallback.is_file():
        executable = str(fallback)
    if not executable:
        raise FileNotFoundError("ffprobe is required")
    result = run([executable, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    payload = json.loads(result.stdout)
    _PROBE_CACHE[key] = payload
    return payload


def safe_filename(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "-_" else "-" for character in value)
    return cleaned.strip("-")[:80] or "asset"
