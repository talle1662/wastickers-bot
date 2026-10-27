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

# How the alpha channel is simplified before encoding. WebP stores alpha
# losslessly, and the alpha decoded from Telegram's VP9 stickers is full of
# near-0 and near-255 noise: on a typical video sticker it was ~75% of the file,
# so lowering `quality` (which only touches colour) could not get it under the
# limit. Measured on one sticker at q60: 499 KB raw, 371 KB CLEAN, 232 KB
# QUANT, 158 KB BINARY.
CLEAN = r"if(lt(val\,16)\,0\,if(gt(val\,239)\,255\,val))"  # snap the noise, invisible
QUANT = r"if(lt(val\,16)\,0\,if(gt(val\,239)\,255\,floor(val/32)*32+16))"  # 8 edge levels
BINARY = r"if(lt(val\,128)\,0\,255)"  # hard edges, last resort

# (quality, fps, alpha) attempts, best first. Alpha is simplified before
# quality is given up, then smoothness, then both together. `None` fps means
# "keep the source frame rate, capped at 30".
LADDER: tuple[tuple[int, int | None, str], ...] = (
    (80, None, CLEAN),
    (70, None, CLEAN),
    (70, None, QUANT),
    (60, None, QUANT),
    (55, 24, QUANT),
    (50, 20, QUANT),
    (45, 15, QUANT),
    (40, 12, QUANT),
    (40, 12, BINARY),
    (30, 10, BINARY),
    # The rungs below are ugly on purpose: a rough sticker beats a skipped one.
    (25, 10, BINARY),
    (20, 8, BINARY),
    (15, 8, BINARY),
)


class EncodeError(RuntimeError):
    pass


def _filters(fps: int | None, native_fps: float, alpha: str) -> str:
    rate = min(fps or native_fps or MAX_FPS, MAX_FPS)
    return (
        f"fps={rate:g},"
        f"scale={STICKER_SIZE}:{STICKER_SIZE}:force_original_aspect_ratio=decrease,"
        f"format=rgba,"
        f"pad={STICKER_SIZE}:{STICKER_SIZE}:-1:-1:color=#00000000,"
        f"lutrgb=a='{alpha}'"
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

    for quality, fps, alpha in LADDER:
        cmd = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            *input_args,
            "-vf", _filters(fps, native_fps, alpha),
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
