"""Reading a sticker set and downloading the files it points at."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from telegram import Bot
from telegram.error import RetryAfter, TimedOut

from .config import DOWNLOAD_CONCURRENCY
from .jobs import LOTTIE, STATIC, VIDEO, StickerRef

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 4


async def load_pack(bot: Bot, set_name: str) -> tuple[str, list[StickerRef]]:
    """Fetch pack metadata. No file is downloaded: getStickerSet already says
    whether each sticker is animated, so the batch menu can be built instantly."""
    sticker_set = await bot.get_sticker_set(set_name)

    refs = []
    for position, sticker in enumerate(sticker_set.stickers, start=1):
        if sticker.is_animated:
            kind = LOTTIE
        elif sticker.is_video:
            kind = VIDEO
        else:
            kind = STATIC
        refs.append(StickerRef(position, sticker.file_id, sticker.emoji or "", kind))

    return sticker_set.title, refs


async def _download_one(bot: Bot, ref: StickerRef, dest: Path) -> Path:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            handle = await bot.get_file(ref.file_id)
            target = dest / f"{ref.pos:04d}{ref.suffix}"
            await handle.download_to_drive(target)
            return target
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 0.5)
        except (TimedOut, OSError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise
            log.warning("download of #%s failed (%s), retrying", ref.pos, exc)
            await asyncio.sleep(2**attempt * 0.5)
    raise RuntimeError(f"could not download sticker #{ref.pos}")


async def download_all(
    bot: Bot,
    refs: list[StickerRef],
    dest: Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[tuple[StickerRef, Path]]:
    """Download `refs` concurrently, preserving their order in the result."""
    semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    completed = 0
    total = len(refs)

    async def worker(ref: StickerRef) -> tuple[StickerRef, Path]:
        nonlocal completed
        async with semaphore:
            path = await _download_one(bot, ref, dest)
        completed += 1
        if on_progress:
            on_progress(completed, total)
        return ref, path

    return list(await asyncio.gather(*(worker(r) for r in refs)))
