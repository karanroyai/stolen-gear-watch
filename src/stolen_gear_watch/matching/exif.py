"""Extract a camera/lens serial number from a photo's metadata.

Generic EXIF tags (BodySerialNumber / LensSerialNumber) cover a lot of
cameras, but plenty of vendor-specific serial fields only live in the
MakerNote block, which generic Python EXIF libraries parse poorly or not
at all. `exiftool` (Phil Harvey's, https://exiftool.org/) has by far the
best MakerNote coverage, so it's the preferred path here. It's a system
binary, not a pip package - if it's missing we fall back to Pillow, which
still catches the standard tags.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Tag names, in priority order, that commonly hold a body/lens serial
# across exiftool's normalized output.
_SERIAL_TAGS = (
    "BodySerialNumber",
    "SerialNumber",
    "InternalSerialNumber",
    "LensSerialNumber",
)

# Standard EXIF tag IDs for the same fields, for the Pillow fallback.
_PILLOW_SERIAL_TAG_IDS = {
    0xA431: "BodySerialNumber",
    0xA435: "LensSerialNumber",
}


def extract_serial(photo_path: str | Path) -> str | None:
    """Best-effort serial extraction. Returns None if no serial tag is
    present or the file can't be read - callers should treat that as
    "unknown", not an error, since plenty of photos legitimately lack it."""
    photo_path = Path(photo_path)
    if shutil.which("exiftool"):
        serial = _extract_via_exiftool(photo_path)
        if serial:
            return serial
    else:
        logger.info(
            "exiftool not found on PATH; falling back to Pillow for EXIF "
            "reading, which misses vendor MakerNote serial fields on some "
            "cameras. Install exiftool for better coverage.",
        )
    return _extract_via_pillow(photo_path)


def _extract_via_exiftool(photo_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["exiftool", "-json", "-G0:1", str(photo_path)],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("exiftool failed on %s: %s", photo_path, exc)
        return None

    try:
        data = json.loads(result.stdout)[0]
    except (json.JSONDecodeError, IndexError):
        return None

    for tag in _SERIAL_TAGS:
        for key, value in data.items():
            if (key.endswith(f":{tag}") or key == tag) and value:
                return str(value)
    return None


def _extract_via_pillow(photo_path: Path) -> str | None:
    try:
        from PIL import Image
    except ImportError:
        logger.warning(
            "Pillow is not installed and exiftool is unavailable; cannot "
            "read EXIF data from %s",
            photo_path,
        )
        return None

    try:
        with Image.open(photo_path) as img:
            exif = img.getexif()
            # BodySerialNumber/LensSerialNumber live in the "Exif" sub-IFD
            # (pointer tag 0x8769), not the top-level IFD0 that getexif()
            # returns directly.
            exif_ifd = exif.get_ifd(0x8769) if exif else {}
    except (OSError, ValueError) as exc:
        logger.warning("Could not open %s for EXIF reading: %s", photo_path, exc)
        return None

    if not exif_ifd:
        return None
    for tag_id in _PILLOW_SERIAL_TAG_IDS:
        value = exif_ifd.get(tag_id)
        if value:
            return str(value).strip()
    return None
