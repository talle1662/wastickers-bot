"""Telegram video stickers (.webm, VP9 with alpha) -> animated WebP."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..config import FFMPEG
from .fit import encode_animated


def _probe_fps(src: Path) -> float:
    """Frame rate of the source, or 30 if ffprobe isn't available/parsable."""
    probe = FFMPEG.replace("ffmpeg", "ffprobe")
    cmd = [
        probe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate", "-of", "json", str(src),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        rate = json.loads(out.stdout)["streams"][0]["r_frame_rate"]
        num, den = rate.split("/")
        return float(num) / float(den) if float(den) else 30.0
    except Exception:
        return 30.0


def convert_video(src: Path, dst: Path) -> int:
    """Decode with libvpx-vp9 explicitly, which is what preserves the alpha channel."""
    return encode_animated(
        ["-c:v", "libvpx-vp9", "-i", str(src)],
        dst,
        native_fps=_probe_fps(src),
    )
