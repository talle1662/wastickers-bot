"""The animated-WebP encoder and its size-fitting ladder.

Both animated sources end up here: .webm packs feed ffmpeg their video stream
directly, .tgs packs feed it a rendered PNG sequence. Sharing the encoder means
both obey the same 500 KB ceiling by the same rules.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import ANIM_MAX_SECONDS, FFMPEG, MAX_ANIMATED_BYTES, STICKER_SIZE

MAX_FPS = 30

# (quality, fps) attempts, best first. Quality is given up before smoothness,
# then both together. `None` means "keep the source frame rate, capped at 30".
LADDER: tuple[tuple[int, int | None], ...] = (
    (80, None),
    (70, None),
    (60, None),
    (65, 24),
    (55, 24),
    (50, 20),
    (45, 15),
    (40, 12),
    (30, 10),
    # The rungs below only come into play when the target is set well under
    # WhatsApp's 500 KB, which is what happens while we bisect the pack-size
    # limit. They are ugly on purpose: a rough sticker beats a skipped one.
    (25, 10),
    (20, 8),
    (15, 8),
)


class EncodeError(RuntimeError):
    pass


def _filters(fps: int | None, native_fps: float) -> str:
    rate = min(fps or native_fps or MAX_FPS, MAX_FPS)
    return (
        f"fps={rate:g},"
        f"scale={STICKER_SIZE}:{STICKER_SIZE}:force_original_aspect_ratio=decrease,"
        f"format=rgba,"
        f"pad={STICKER_SIZE}:{STICKER_SIZE}:-1:-1:color=#00000000"
    )


def encode_animated(
    input_args: list[str],
    dst: Path,
    native_fps: float,
    limit: int = MAX_ANIMATED_BYTES,
) -> int:
    """Try the ladder until the output fits; return the final size in bytes.

    Raises EncodeError if even the last rung stays over `limit`.
    """
    last_size = 0
    last_error = ""

    for quality, fps in LADDER:
        cmd = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            *input_args,
            "-vf", _filters(fps, native_fps),
            "-t", str(ANIM_MAX_SECONDS),   # hard 10 s cap, applied every time
            "-an",
            "-c:v", "libwebp_anim",
            "-pix_fmt", "yuva420p",        # lossy WebP with an alpha channel
            "-lossless", "0",
            "-q:v", str(quality),
            "-loop", "0",
            "-f", "webp",
            str(dst),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not dst.exists():
            last_error = (result.stderr or "").strip().splitlines()[-1:] or ["ffmpeg failed"]
            last_error = last_error[0]
            continue

        last_size = dst.stat().st_size
        if last_size <= limit:
            return last_size

    if last_size:
        raise EncodeError(f"still {last_size // 1024} KB at the lowest setting")
    raise EncodeError(last_error or "ffmpeg produced no output")
