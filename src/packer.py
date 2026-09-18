"""Writing the .wastickers container.

The layout here is not guesswork: it mirrors a real file exported by the
Sticker Maker app and confirmed to import (PLAN.md section 3).

    title.txt              UTF-8, no trailing newline, no BOM
    author.txt             same
    tray.png               PNG, exactly 96x96
    <prefix>_01.webp       prefix is a unix timestamp, index zero-padded to 2
    <prefix>_02.webp
    ...

Everything that knows about the container lives in this module, so adjusting to
a format change means editing one file.
"""

from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

from PIL import Image

from .config import MAX_TRAY_BYTES, TRAY_SIZE
from .util import truncate

TITLE_LIMIT = 128
AUTHOR_LIMIT = 128


def make_tray(src: Path) -> bytes:
    """Build the 96x96 tray icon from a sticker (first frame, if animated)."""
    with Image.open(src) as im:
        if getattr(im, "is_animated", False):
            im.seek(0)
        frame = im.convert("RGBA")

    frame.thumbnail((TRAY_SIZE, TRAY_SIZE), Image.LANCZOS)
    canvas = Image.new("RGBA", (TRAY_SIZE, TRAY_SIZE), (0, 0, 0, 0))
    canvas.paste(frame, ((TRAY_SIZE - frame.width) // 2, (TRAY_SIZE - frame.height) // 2))

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    if buffer.tell() > MAX_TRAY_BYTES:
        buffer = io.BytesIO()
        canvas.quantize(colors=256, method=Image.FASTOCTREE).save(
            buffer, format="PNG", optimize=True
        )
    return buffer.getvalue()


def write_wastickers(
    dst: Path,
    title: str,
    author: str,
    stickers: list[Path],
    prefix: str | None = None,
) -> Path:
    """Zip `stickers` into a .wastickers at `dst`. Returns `dst`.

    `prefix` must differ between the files of one split, otherwise two packs
    generated in the same second would carry identical sticker names.
    """
    if not stickers:
        raise ValueError("refusing to write a pack with no stickers")

    prefix = prefix or str(int(time.time()))

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("title.txt", truncate(title, TITLE_LIMIT).encode("utf-8"))
        zf.writestr("author.txt", truncate(author, AUTHOR_LIMIT).encode("utf-8"))
        zf.writestr("tray.png", make_tray(stickers[0]))
        for index, sticker in enumerate(stickers, start=1):
            zf.write(sticker, f"{prefix}_{index:02d}.webp")

    return dst
