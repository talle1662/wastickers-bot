"""Telegram handlers: the start message, the batch menu and the conversion run."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from . import texts
from .config import (
    BOT_USERNAME_FALLBACK,
    CLEAR_CHUNK,
    CLEAR_SWEEP_DEPTH,
    MIN_PER_PACK,
    PROGRESS_THROTTLE_S,
    UPLOAD_READ_TIMEOUT,
    UPLOAD_WRITE_TIMEOUT,
)
from .convert import convert_one
from .jobs import Family, Job, JobStore, build_job
from .keyboard import CONVERT_ALL, batch_key, build_header, build_keyboard
from .packer import write_wastickers
from .telegram_fetch import download_all, load_pack
from .util import sanitize_filename

log = logging.getLogger(__name__)

store = JobStore()


class ProgressReporter:
    """Edits one status message on a timer, so progress never trips the flood limit."""

    def __init__(self, message) -> None:
        self._message = message
        self._pending = ""
        self._shown = ""
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    def update(self, text: str) -> None:
        self._pending = text

    async def _flush(self) -> None:
        if self._pending and self._pending != self._shown:
            self._shown = self._pending
            try:
                await self._message.edit_text(self._shown)
            except Exception:  # a failed progress edit must never break the run
                pass

    async def _loop(self) -> None:
        while not self._stop.is_set():
            await self._flush()
            try:
                await asyncio.wait_for(self._stop.wait(), PROGRESS_THROTTLE_S)
            except asyncio.TimeoutError:
                pass
        await self._flush()

    async def __aenter__(self) -> "ProgressReporter":
        self._task = asyncio.create_task(self._loop())
        return self

    async def __aexit__(self, *_exc) -> None:
        self._stop.set()
        if self._task:
            await self._task


async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(texts.START, disable_web_page_preview=True)


async def on_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sticker = update.message.sticker

    if not sticker.set_name:
        await update.message.reply_text(texts.NO_PACK)
        return

    status = await update.message.reply_text(texts.READING)
    try:
        title, refs = await load_pack(context.bot, sticker.set_name)
    except Exception as exc:  # noqa: BLE001
        log.warning("getStickerSet(%s) failed: %s", sticker.set_name, exc)
        await status.edit_text(texts.READ_FAILED.format(error=exc))
        return

    if not refs:
        await status.edit_text(texts.EMPTY_PACK)
        return

    job = build_job(
        update.effective_user.id,
        update.effective_chat.id,
        sticker.set_name,
        title,
        refs,
    )
    store.put(job)
    await status.edit_text(build_header(job), reply_markup=build_keyboard(job))


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    action, token = parts[0], parts[1]

    job = store.get(token)
    if job is None:
        await query.answer(texts.EXPIRED, show_alert=True)
        return
    if update.effective_user.id != job.user_id:
        await query.answer(texts.NOT_YOURS, show_alert=True)
        return

    if action == "p":  # expand / collapse a family's batch buttons
        job.expanded ^= {parts[2]}
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=build_keyboard(job))
        return

    if parts[2] == CONVERT_ALL:
        targets = [(f, i) for f in job.families for i in range(len(f.batches))]
    else:
        family = job.family(parts[2])
        if family is None or not (0 <= int(parts[3]) < len(family.batches)):
            await query.answer(texts.GONE, show_alert=True)
            return
        targets = [(family, int(parts[3]))]

    if not store.claim(job.user_id):
        await query.answer(texts.BUSY, show_alert=True)
        return

    await query.answer()
    try:
        await _run(context, query, job, targets)
    except Exception as exc:  # noqa: BLE001
        log.exception("conversion run failed")
        await context.bot.send_message(job.chat_id, texts.RUN_FAILED.format(error=exc))
    finally:
        store.release(job.user_id)


def _nature(family: Family) -> str:
    return texts.NATURE_ANIMATED if family.key == "a" else texts.NATURE_STATIC


def _compose_title(job: Job, family: Family, index: int) -> str:
    parts = []
    if len(job.families) > 1:
        parts.append(_nature(family))
    if len(family.batches) > 1:
        parts.append(f"{index + 1}/{len(family.batches)}")
    return f"{job.title} ({' '.join(parts)})" if parts else job.title


async def _run_batch(
    context: ContextTypes.DEFAULT_TYPE,
    job: Job,
    family: Family,
    index: int,
    tag: str,
    step: int,
    progress: ProgressReporter,
) -> list[str]:
    """Convert and send one batch. Returns the list of skipped sticker labels."""
    refs = family.batches[index]
    author = context.bot_data.get("author", BOT_USERNAME_FALLBACK)
    executor = context.bot_data["executor"]
    loop = asyncio.get_running_loop()

    with tempfile.TemporaryDirectory(prefix="wastickers_") as workdir:
        raw = Path(workdir) / "raw"
        out = Path(workdir) / "out"
        raw.mkdir()
        out.mkdir()

        progress.update(texts.DOWNLOADING.format(tag=tag, done=0, total=len(refs)))
        downloaded = await download_all(
            context.bot,
            refs,
            raw,
            lambda d, t, _tag=tag: progress.update(
                texts.DOWNLOADING.format(tag=_tag, done=d, total=t)
            ),
        )

        progress.update(texts.CONVERTING.format(tag=tag, done=0, total=len(refs)))
        futures = []
        for ref, path in downloaded:
            dst = out / f"{ref.pos:04d}.webp"
            futures.append(
                (ref, dst, loop.run_in_executor(executor, convert_one, str(path), ref.kind, str(dst)))
            )

        good: list[Path] = []
        skipped: list[str] = []
        for finished, (ref, dst, future) in enumerate(futures, start=1):
            ok, _size, reason = await future
            if ok:
                good.append(dst)
            else:
                skipped.append(f"#{ref.pos} {ref.emoji}".strip())
                log.info("skipped #%s (%s): %s", ref.pos, ref.kind, reason)
            progress.update(
                texts.CONVERTING.format(tag=tag, done=finished, total=len(refs))
            )

        if not good:
            await context.bot.send_message(
                job.chat_id,
                texts.BATCH_ALL_FAILED.format(range=family.range_label(index)),
            )
            return skipped

        filename = (
            f"{sanitize_filename(job.title)}_{_nature(family)}"
            f"_{index + 1}di{len(family.batches)}.wastickers"
        )
        archive = Path(workdir) / filename
        title = _compose_title(job, family, index)

        progress.update(texts.BUILDING.format(tag=tag, filename=filename))
        write_wastickers(
            archive, title, author, good, prefix=f"{int(time.time())}{step:02d}"
        )

        caption = [texts.CAPTION.format(title=title, n=len(good))]
        if skipped:
            caption.append(
                texts.CAPTION_SKIPPED.format(n=len(skipped), which="  ".join(skipped))
            )
        if len(good) < MIN_PER_PACK:
            caption.append(
                texts.CAPTION_TOO_FEW.format(n=len(good), minimum=MIN_PER_PACK)
            )

        progress.update(texts.UPLOADING.format(tag=tag, filename=filename))
        await context.bot.send_chat_action(job.chat_id, ChatAction.UPLOAD_DOCUMENT)
        with archive.open("rb") as handle:
            await context.bot.send_document(
                job.chat_id,
                document=handle,
                filename=filename,
                caption="\n".join(caption),
                # A 15 MB animated pack over a slow uplink takes far longer than
                # the library's default, and a premature timeout used to abort
                # the whole run even though the file had already gone through.
                read_timeout=UPLOAD_READ_TIMEOUT,
                write_timeout=UPLOAD_WRITE_TIMEOUT,
            )

        job.done.add(batch_key(family, index))
        return skipped


async def _run(
    context: ContextTypes.DEFAULT_TYPE,
    query,
    job: Job,
    targets: list[tuple[Family, int]],
) -> None:
    status = await context.bot.send_message(job.chat_id, texts.STARTING)
    produced = 0
    skipped_overall: list[str] = []

    async with ProgressReporter(status) as progress:
        for step, (family, index) in enumerate(targets, start=1):
            tag = f"[{step}/{len(targets)}] " if len(targets) > 1 else ""
            try:
                skipped = await _run_batch(
                    context, job, family, index, tag, step, progress
                )
                skipped_overall.extend(skipped)
                if batch_key(family, index) in job.done:
                    produced += 1
            except Exception as exc:  # noqa: BLE001
                # One bad batch must not cost the user the batches after it.
                log.exception("batch %s of %s failed", index + 1, family.key)
                await context.bot.send_message(
                    job.chat_id,
                    texts.BATCH_FAILED.format(
                        range=family.range_label(index), error=exc
                    ),
                )

        summary = [texts.DONE.format(n=produced)]
        if skipped_overall:
            summary.append(texts.DONE_SKIPPED.format(n=len(skipped_overall)))
        summary.append(texts.EMOJI_NOTE)
        progress.update("\n".join(summary))

    try:
        await query.edit_message_reply_markup(reply_markup=build_keyboard(job))
    except Exception:  # the menu may be too old to edit; the files were still sent
        pass


async def on_other(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(texts.SEND_A_STICKER)


# --- /clear ---------------------------------------------------------------
#
# A bot may delete both its own and the user's messages in a private chat, but
# only for 48 hours and only by message id. Rather than keeping a ledger (which
# would be lost on restart and would miss anything sent while the bot was down),
# /clear walks ids backwards from itself: in a private chat they are sequential,
# deleteMessages takes 100 at a time and silently skips whatever it can't touch.


def _forget_later(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: float
) -> None:
    """Delete a message after `delay` seconds without blocking the handler."""

    async def worker() -> None:
        await asyncio.sleep(delay)
        try:
            await context.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    asyncio.create_task(worker())


async def clear(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(texts.BTN_CLEAR_YES, callback_data="x:go")],
            [InlineKeyboardButton(texts.BTN_CLEAR_NO, callback_data="x:no")],
        ]
    )
    await update.message.reply_text(texts.CLEAR_CONFIRM, reply_markup=keyboard)


async def _wipe(context: ContextTypes.DEFAULT_TYPE, chat_id: int, newest: int) -> None:
    ids = list(range(max(1, newest - CLEAR_SWEEP_DEPTH), newest + 1))
    ids.reverse()  # newest first, so the visible part of the chat clears at once

    for start in range(0, len(ids), CLEAR_CHUNK):
        chunk = ids[start : start + CLEAR_CHUNK]
        try:
            await context.bot.delete_messages(chat_id, chunk)
        except Exception:
            # A chunk where nothing is deletable can fail as a whole, so fall
            # back to one by one rather than losing the ids that would have gone.
            for message_id in chunk:
                try:
                    await context.bot.delete_message(chat_id, message_id)
                except Exception:
                    pass


async def on_clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()

    if query.data == "x:no":
        await query.edit_message_text(texts.CLEAR_CANCELLED)
        _forget_later(context, chat_id, query.message.message_id, 3)
        return

    await _wipe(context, chat_id, query.message.message_id)
    notice = await context.bot.send_message(chat_id, texts.CLEAR_DONE)
    _forget_later(context, chat_id, notice.message_id, 8)
