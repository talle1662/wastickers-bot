"""Job model, the static/animated split and the batching algorithm.

This is where the two WhatsApp pack rules live:
  * at most 30 stickers per pack, and at least 3;
  * a pack may not mix animated and static stickers.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field

from .config import JOB_TTL_SECONDS, MAX_PER_PACK, MIN_PER_PACK

STATIC = "static"
VIDEO = "video"
LOTTIE = "lottie"

_SUFFIX = {STATIC: ".webp", VIDEO: ".webm", LOTTIE: ".tgs"}


@dataclass(slots=True)
class StickerRef:
    """One sticker as advertised by getStickerSet, before any download."""

    pos: int  # 1-based position in the Telegram pack, for user-facing messages
    file_id: str
    emoji: str
    kind: str  # STATIC | VIDEO | LOTTIE

    @property
    def animated(self) -> bool:
        return self.kind != STATIC

    @property
    def suffix(self) -> str:
        return _SUFFIX[self.kind]


@dataclass(slots=True)
class Family:
    """All stickers of one nature, plus how they divide into packs."""

    key: str  # "s" or "a", used in callback_data
    label: str  # emoji shown on the buttons
    items: list[StickerRef]
    batches: list[list[StickerRef]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.batches = split_into_batches(self.items)

    def range_label(self, index: int) -> str:
        """Human range of batch `index`, numbered within this family."""
        start = sum(len(b) for b in self.batches[:index]) + 1
        return f"{start}–{start + len(self.batches[index]) - 1}"


@dataclass
class Job:
    token: str
    user_id: int
    chat_id: int
    set_name: str
    title: str
    static: Family
    animated: Family
    created_at: float = field(default_factory=time.time)
    done: set[str] = field(default_factory=set)  # callback keys already converted
    expanded: set[str] = field(default_factory=set)  # families showing all batches

    @property
    def total(self) -> int:
        return len(self.static.items) + len(self.animated.items)

    @property
    def families(self) -> list[Family]:
        return [f for f in (self.static, self.animated) if f.items]

    def family(self, key: str) -> Family | None:
        return {"s": self.static, "a": self.animated}.get(key)

    def expired(self) -> bool:
        return time.time() - self.created_at > JOB_TTL_SECONDS


def split_into_batches(
    items: list[StickerRef],
    max_per: int = MAX_PER_PACK,
    min_per: int = MIN_PER_PACK,
) -> list[list[StickerRef]]:
    """Greedy chunks of `max_per`, with a fix-up so no pack ends up under `min_per`.

    Greedy alone is what the user asked for (100 -> 30+30+30+10) but it can emit
    an unimportable tail: 31 -> 30+1, and WhatsApp rejects a pack of one. When
    that happens the last two chunks are rebalanced, which touches only the
    affected sizes and leaves every other case exactly as the greedy result.

        100 -> [30, 30, 30, 10]
         31 -> [16, 15]           (not [30, 1])
         61 -> [30, 16, 15]       (not [30, 30, 1])

    A total below `min_per` cannot be fixed by splitting; it is returned as a
    single short batch and the caller warns the user.
    """
    if not items:
        return []

    batches = [items[i : i + max_per] for i in range(0, len(items), max_per)]

    if len(batches) >= 2 and len(batches[-1]) < min_per:
        merged = batches[-2] + batches[-1]
        half = (len(merged) + 1) // 2
        batches[-2:] = [merged[:half], merged[half:]]

    return batches


def build_job(
    user_id: int,
    chat_id: int,
    set_name: str,
    title: str,
    refs: list[StickerRef],
) -> Job:
    """Split a pack into its two families. Order within each family is preserved."""
    return Job(
        token=secrets.token_hex(4),
        user_id=user_id,
        chat_id=chat_id,
        set_name=set_name,
        title=title,
        static=Family("s", "\U0001f5bc", [r for r in refs if not r.animated]),
        animated=Family("a", "\U0001f3ac", [r for r in refs if r.animated]),
    )


class JobStore:
    """In-memory, TTL'd. Jobs are cheap to rebuild: the user resends the sticker."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._busy: set[int] = set()

    def put(self, job: Job) -> None:
        self.purge()
        self._jobs[job.token] = job

    def get(self, token: str) -> Job | None:
        job = self._jobs.get(token)
        if job and job.expired():
            self._jobs.pop(token, None)
            return None
        return job

    def purge(self) -> None:
        for token in [t for t, j in self._jobs.items() if j.expired()]:
            self._jobs.pop(token, None)

    def claim(self, user_id: int) -> bool:
        """One conversion at a time per user; returns False if already running."""
        if user_id in self._busy:
            return False
        self._busy.add(user_id)
        return True

    def release(self, user_id: int) -> None:
        self._busy.discard(user_id)
