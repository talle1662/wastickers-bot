"""Sticker conversion, dispatched by source kind.

`convert_one` is the process-pool entry point, so it takes and returns only
plain picklable values and never raises: a sticker that cannot be made to fit is
reported back as a failure and skipped, not allowed to kill the batch.
"""

from __future__ import annotations

from pathlib import Path

from ..jobs import LOTTIE, STATIC, VIDEO
from .lottie import convert_lottie
from .static import convert_static
from .video import convert_video

_DISPATCH = {STATIC: convert_static, VIDEO: convert_video, LOTTIE: convert_lottie}


def convert_one(src: str, kind: str, dst: str) -> tuple[bool, int, str]:
    """Returns (ok, size_in_bytes, reason_if_failed)."""
    try:
        size = _DISPATCH[kind](Path(src), Path(dst))
        return True, size, ""
    except Exception as exc:  # noqa: BLE001 - one bad sticker must not sink the pack
        return False, 0, str(exc) or exc.__class__.__name__


__all__ = ["convert_one", "convert_static", "convert_video", "convert_lottie"]
