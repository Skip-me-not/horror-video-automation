from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .assets import _font


def _face_center(image: Image.Image) -> tuple[float, float] | None:
    try:
        import cv2
        import numpy as np
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        if len(faces):
            x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
            return (x + w / 2) / image.width, (y + h / 2) / image.height
    except (ImportError, OSError, ValueError):
        pass
    return None


def prepare_vertical(source: Path, destination: Path, variant: int = 0,
                     credit: str = "") -> dict[str, object]:
    """Face-prioritized portrait over a blurred fill; never remove an existing watermark."""
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    width, height = 1080, 1920
    face = _face_center(image)
    center_x, center_y = face or (0.5, 0.43)
    drift = (-0.06, 0.0, 0.06)[variant % 3]
    center_x = min(0.85, max(0.15, center_x + drift))
    background = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS,
                              centering=(center_x, center_y)).filter(ImageFilter.GaussianBlur(46))
    background = Image.blend(background, Image.new("RGB", (width, height), (8, 5, 18)), 0.43)
    foreground = image.copy()
    foreground.thumbnail((1000, 1640), Image.Resampling.LANCZOS)
    x = max(40, min(width - foreground.width - 40, int(width * center_x - foreground.width / 2)))
    y = max(165, min(1540 - foreground.height, int(775 - foreground.height * center_y)))
    background.paste(foreground, (x, y))
    draw = ImageDraw.Draw(background, "RGBA")
    draw.rounded_rectangle((60, 1620, 1020, 1850), radius=30, fill=(8, 4, 20, 185))
    draw.text((540, 1700), "Lululala", anchor="mm", font=_font(45, True), fill="white")
    if credit:
        draw.text((540, 1790), "Source: " + credit[:45], anchor="mm", font=_font(25), fill=(235, 225, 245))
    destination.parent.mkdir(parents=True, exist_ok=True)
    background.save(destination, optimize=True)
    return {"path": str(destination), "face_detected": face is not None,
            "subject_center": [round(center_x, 3), round(center_y, 3)], "variant": variant}


def video_focus_x(source: Path) -> float:
    """Estimate horizontal subject position from a source clip's opening frame."""
    try:
        import cv2
        capture = cv2.VideoCapture(str(source))
        try:
            success, frame = capture.read()
        finally:
            capture.release()
        if success:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face = _face_center(Image.fromarray(rgb))
            if face:
                return round(face[0], 3)
    except (ImportError, OSError, ValueError):
        pass
    return 0.5
