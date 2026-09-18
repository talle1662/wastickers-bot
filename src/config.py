"""Configuration, credentials and the hard limits imposed by WhatsApp.

The limits in the second block are not tunable preferences: they come from the
Sticker Maker / WhatsApp sticker spec and were confirmed by inspecting a real
.wastickers file that imports successfully (see PLAN.md section 3).
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Minimal .env reader, so we don't pull in python-dotenv for four lines."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BOT_USERNAME_FALLBACK = "@WhatsAppStickerConverterBot"
FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")

# --- WhatsApp / Sticker Maker limits -------------------------------------
STICKER_SIZE = 512
TRAY_SIZE = 96

# These ceilings are decimal, not binary: WhatsApp means 100000 and 500000
# bytes, not 100*1024 and 500*1024. Using the binary values let through files
# up to 12000 bytes over the real limit, which WhatsApp rejects at import time
# with a generic error naming no sticker in particular.
MAX_STATIC_BYTES = 100_000
MAX_ANIMATED_BYTES = int(os.environ.get("ANIMATED_TARGET_KB", "500")) * 1000
MAX_TRAY_BYTES = 50_000
MAX_PER_PACK = 30
MIN_PER_PACK = 3
ANIM_MAX_SECONDS = 9.8  # spec says 10 s; stay just under it

# --- behaviour -----------------------------------------------------------
DOWNLOAD_CONCURRENCY = 6
JOB_TTL_SECONDS = 3600
PROGRESS_THROTTLE_S = 2.0
MAX_BATCH_BUTTONS = 8  # per family, before the rest goes behind a pager

# /clear walks message ids backwards from the command instead of keeping a
# ledger, so it also reaches messages sent before the bot was last restarted.
# Telegram refuses anything older than 48 hours anyway, which bounds the damage
# a large number here could do.
CLEAR_SWEEP_DEPTH = 1000
CLEAR_CHUNK = 100  # deleteMessages takes at most 100 ids per call

# Uploading an animated pack means pushing up to ~15 MB. The library's default
# timeouts are sized for small API calls and were cutting the upload off while
# it was still succeeding server-side, so give the media calls real room.
CONNECT_TIMEOUT = 30.0
READ_TIMEOUT = 60.0
WRITE_TIMEOUT = 120.0
MEDIA_WRITE_TIMEOUT = 900.0
POOL_TIMEOUT = 60.0
UPLOAD_READ_TIMEOUT = 300.0
UPLOAD_WRITE_TIMEOUT = 900.0
