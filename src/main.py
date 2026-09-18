"""Entry point: wires the handlers and owns the conversion process pool."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from . import texts
from .config import (
    BOT_TOKEN,
    CONNECT_TIMEOUT,
    MEDIA_WRITE_TIMEOUT,
    POOL_TIMEOUT,
    READ_TIMEOUT,
    WRITE_TIMEOUT,
)
from .handlers import clear, on_callback, on_clear_callback, on_other, on_sticker, start
from .util import setup_logging

log = logging.getLogger(__name__)


async def _post_init(app: Application) -> None:
    """author.txt carries the converter bot's own handle, matching the reference pack."""
    me = await app.bot.get_me()
    app.bot_data["author"] = f"@{me.username}"
    log.info("running as @%s", me.username)

    await app.bot.set_my_commands(
        [
            BotCommand("start", texts.CMD_START),
            BotCommand("clear", texts.CMD_CLEAR),
        ]
    )


def main() -> None:
    setup_logging()

    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is missing. Put it in .env next to run.py:\n"
            "    BOT_TOKEN=123456:ABC-your-token-here"
        )

    # Conversion is CPU-bound (Pillow, rlottie, ffmpeg), so it runs off the event
    # loop; one core is left free so the bot keeps answering during a long pack.
    workers = max(1, (os.cpu_count() or 2) - 1)
    executor = ProcessPoolExecutor(max_workers=workers)
    log.info("conversion pool: %d workers", workers)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(CONNECT_TIMEOUT)
        .read_timeout(READ_TIMEOUT)
        .write_timeout(WRITE_TIMEOUT)
        .media_write_timeout(MEDIA_WRITE_TIMEOUT)
        .pool_timeout(POOL_TIMEOUT)
        .post_init(_post_init)
        .build()
    )
    app.bot_data["executor"] = executor

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.Sticker.ALL, on_sticker))
    # Patterns keep the two callback families apart: "c:"/"p:" carry a job token,
    # "x:" does not, and the job handler would trip over its own parsing.
    app.add_handler(CallbackQueryHandler(on_clear_callback, pattern=r"^x:"))
    app.add_handler(CallbackQueryHandler(on_callback, pattern=r"^[cp]:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_other))

    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
