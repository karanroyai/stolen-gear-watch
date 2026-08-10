"""Small helpers shared across adapters."""

from __future__ import annotations

_CHALLENGE_MARKERS = (
    "captcha",
    "cf-browser-verification",
    "attention required",
    "access denied",
    "are you a human",
)


def looks_like_bot_challenge(html: str) -> bool:
    """Heuristic check for whether a response is a bot-detection challenge
    page rather than real content, so adapters can log that distinction
    instead of silently returning zero results."""
    lowered = html.lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)
