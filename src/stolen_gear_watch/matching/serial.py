"""Match a watched item's serial number against free-text (a listing title,
description, or registry page). Heuristic, not exact - sellers format
serials inconsistently (spaces, dashes, "SN:" prefixes, OCR'd from a photo),
so this returns a confidence rather than a plain boolean.
"""

from __future__ import annotations

import re

from stolen_gear_watch.core.models import normalize_serial

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

# Serials shorter than this are too likely to appear by coincidence in
# unrelated text; refuse to match them at all rather than risk a false alert.
_MIN_SAFE_SERIAL_LENGTH = 4


def serial_match_confidence(text: str, serial: str) -> float:
    """1.0 if the serial appears as its own token in the text, 0.6 if it
    only appears when adjacent tokens are joined (covers formatting like
    "SN 1234 5678"), 0.0 otherwise."""
    normalized_serial = normalize_serial(serial)
    if len(normalized_serial) < _MIN_SAFE_SERIAL_LENGTH:
        return 0.0

    tokens = [t.upper() for t in _TOKEN_RE.findall(text)]
    if normalized_serial in tokens:
        return 1.0

    # Only worth checking the joined-token form for reasonably long serials,
    # otherwise this degenerates into a substring search over the whole text.
    if len(normalized_serial) >= 6 and normalized_serial in "".join(tokens):
        return 0.6

    return 0.0
