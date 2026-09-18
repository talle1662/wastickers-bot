"""Telegram Lottie stickers (.tgs) -> animated WebP.

.tgs is gzipped Lottie JSON, so there is nothing to decode with ffmpeg: rlottie
rasterises the vector animation frame by frame, and the PNG sequence is then
handed to the shared encoder.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from rlottie_python import LottieAnimation

from ..config import ANIM_MAX_SECONDS, STICKER_SIZE
from .fit import MAX_FPS, encode_animated

MAX_FRAMES = 400  # safety net against a pathological animation


def convert_lottie(src: Path, dst: Path) -> int:
    anim = LottieAnimation.from_tgs(str(src))
    try:
        total = anim.lottie_animation_get_totalframe()
        fps = float(anim.lottie_animation_get_framerate() or MAX_FPS)

        # Rasterise once at the source frame rate; the encoder's ladder drops
        # frames with its own fps filter when it needs to shrink the file.
        keep = min(total, MAX_FRAMES, max(1, int(ANIM_MAX_SECONDS * fps)))

        with tempfile.TemporaryDirectory(prefix="tgs_") as tmp:
            frames_dir = Path(tmp)
            for i in range(keep):
                frame = anim.render_pillow_frame(
                    frame_num=i, width=STICKER_SIZE, height=STICKER_SIZE
                )
                frame.save(frames_dir / f"{i:05d}.png")

            return encode_animated(
                ["-framerate", f"{fps:g}", "-i", str(frames_dir / "%05d.png")],
                dst,
                native_fps=fps,
            )
    finally:
        anim.lottie_animation_destroy()
