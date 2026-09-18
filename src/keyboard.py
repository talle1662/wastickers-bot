"""The inline keyboard: one button per batch, numbered within its family.

Batches are numbered per family rather than across the whole pack because a
button spanning the static/animated boundary would produce a file WhatsApp
refuses to import.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from . import texts
from .config import MAX_BATCH_BUTTONS
from .jobs import Family, Job

CONVERT_ALL = "all"


def batch_key(family: Family, index: int) -> str:
    return f"{family.key}:{index}"


def build_keyboard(job: Job) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    total_files = sum(len(f.batches) for f in job.families)

    if total_files > 1:
        everything_done = all(
            batch_key(f, i) in job.done
            for f in job.families
            for i in range(len(f.batches))
        )
        label = (
            texts.BTN_CONVERTED_ALL
            if everything_done
            else texts.BTN_CONVERT_ALL.format(n=total_files)
        )
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"c:{job.token}:{CONVERT_ALL}")]
        )

    for family in job.families:
        expanded = family.key in job.expanded
        count = len(family.batches)
        shown = count if (expanded or count <= MAX_BATCH_BUTTONS) else MAX_BATCH_BUTTONS

        row: list[InlineKeyboardButton] = []
        for index in range(shown):
            key = batch_key(family, index)
            mark = "✅" if key in job.done else family.label
            row.append(
                InlineKeyboardButton(
                    f"{mark} {family.range_label(index)}",
                    callback_data=f"c:{job.token}:{key}",
                )
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

        if count > MAX_BATCH_BUTTONS:
            label = texts.BTN_FEWER if expanded else texts.BTN_MORE.format(n=count - shown)
            rows.append(
                [InlineKeyboardButton(label, callback_data=f"p:{job.token}:{family.key}")]
            )

    return InlineKeyboardMarkup(rows)


def build_header(job: Job) -> str:
    counts = []
    if job.static.items:
        counts.append(
            texts.COUNT_STATIC.format(label=job.static.label, n=len(job.static.items))
        )
    if job.animated.items:
        counts.append(
            texts.COUNT_ANIMATED.format(
                label=job.animated.label, n=len(job.animated.items)
            )
        )

    return "\n".join(
        [
            texts.HEADER.format(title=job.title, total=job.total),
            " · ".join(counts),
            "",
            texts.RULES,
        ]
    )
