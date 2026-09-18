"""Fitting an arbitrary image onto the 512x512 canvas WhatsApp requires."""

from __future__ import annotations

from PIL import Image

from ..config import STICKER_SIZE


def fit_square(im: Image.Image, size: int = STICKER_SIZE) -> Image.Image:
    """Scale to fit inside `size` x `size` and centre on a transparent canvas.

    Telegram stickers are already bounded by 512 on their longest side but the
    other side is often shorter (512x384 is common), so this mostly letterboxes
    rather than rescales. No extra padding is added: the source art already
    carries its own margins.
    """
    im = im.convert("RGBA")

    if im.size != (size, size):
        scaled = im.copy()
        scaled.thumbnail((size, size), Image.LANCZOS)
    else:
        scaled = im

    if scaled.size == (size, size):
        return scaled

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(scaled, ((size - scaled.width) // 2, (size - scaled.height) // 2))
    return canvas
