"""Static Telegram stickers (.webp) -> WhatsApp-compliant WebP."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..config import MAX_STATIC_BYTES
from .canvas import fit_square

# The reference pack's stickers all landed between 8 and 51 KB against a 100 KB
# ceiling, so in practice the first step of this ladder is the one that wins.
QUALITY_LADDER = (95, 90, 85, 80, 70, 60, 50, 40, 30, 20)


def convert_static(src: Path, dst: Path) -> int:
    """Write `dst` at or under the static size limit; return its size in bytes.

    Raises ValueError if even the lowest quality stays over the limit.
    """
    with Image.open(src) as opened:
        opened.load()
        im = fit_square(opened)

    for quality in QUALITY_LADDER:
        # lossy + alpha, matching the VP8X/ALPH/VP8 layout of the reference pack
        im.save(dst, format="WEBP", lossless=False, quality=quality, method=6)
        size = dst.stat().st_size
        if size <= MAX_STATIC_BYTES:
            return size

    raise ValueError(f"still {dst.stat().st_size // 1024} KB at quality 20")
