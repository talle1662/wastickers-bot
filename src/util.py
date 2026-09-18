"""Small shared helpers."""

from __future__ import annotations

import logging
import re
import sys

_UNSAFE = re.compile(r"[^\w\-. ]+", re.UNICODE)


def setup_logging(level: int = logging.INFO) -> None:
    # The Windows console defaults to cp1252, which raises on any emoji that
    # reaches a log line. Sticker packs are full of them, so make stdout total.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-7s %(name)-18s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # httpx logs every Bot API call at INFO, which drowns everything else.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def sanitize_filename(name: str, fallback: str = "stickers") -> str:
    """Turn a pack title into something safe for a filename on any OS."""
    cleaned = _UNSAFE.sub("", name).strip().strip(".")
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:60] or fallback


def truncate(text: str, limit: int) -> str:
    """Clip to `limit` characters, used for title.txt / author.txt (128 max)."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
