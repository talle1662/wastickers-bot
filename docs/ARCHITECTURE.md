# Architecture

*[🇮🇹 Versione italiana](ARCHITETTURA.md)*

## 1. What the bot actually does

A Telegram sticker pack and a WhatsApp sticker pack are not the same object. One
Telegram pack becomes *n* WhatsApp packs, and the mapping is constrained by rules
that are easy to violate and produce a single unhelpful error when violated.

The whole design follows from three constraints:

| Constraint | Source | Consequence |
|---|---|---|
| 3–30 stickers per pack | WhatsApp | a 108-sticker pack must be split |
| No mixing animated and static | WhatsApp | it must be split by nature *first* |
| 100 000 / 500 000 bytes per sticker | WhatsApp | every sticker must be re-encoded to fit |

## 2. Data flow

```
sticker message
    │
    ├─ sticker.set_name ──► getStickerSet()          metadata only, no download
    │                          │
    │                          └─ is_animated / is_video per sticker
    │                               │
    │                               ├─ family split: static | animated
    │                               └─ batching: chunks of ≤30 within each family
    │                                    │
    │                                    └─ inline keyboard, one button per batch
    │
    └─[button]─► download the requested slice only   asyncio, semaphore of 6
                     │
                     └─ convert                       ProcessPoolExecutor
                          │  ├─ .webp  → Pillow
                          │  ├─ .webm  → ffmpeg (libvpx-vp9 → libwebp_anim)
                          │  └─ .tgs   → rlottie → PNG frames → ffmpeg
                          │
                          └─ pack into .wastickers    zip
                               │
                               └─ send_document
```

The important property: **`getStickerSet` already reports whether each sticker is
animated**, so classification costs nothing and happens before any download. The
batch menu appears instantly even for a 300-sticker pack, and each button then
fetches only its own 30 files.

## 3. Module map

```
run.py                  entry point; the __main__ guard matters on Windows
src/
├─ main.py              handler wiring, timeouts, the process pool
├─ config.py            credentials, WhatsApp limits, tunables
├─ texts.py             every user-facing string (currently Italian)
├─ jobs.py              StickerRef / Family / Job, the splitting algorithm, job store
├─ keyboard.py          inline keyboard construction, per-family numbering
├─ telegram_fetch.py    getStickerSet + concurrent downloads with retry
├─ handlers.py          /start, /clear, sticker intake, the conversion run
├─ packer.py            the .wastickers container — the only module that knows the format
├─ util.py              logging, filename sanitising
└─ convert/
   ├─ __init__.py       convert_one(): the process-pool entry point
   ├─ canvas.py         fitting any image onto the 512×512 canvas
   ├─ static.py         static → WebP under 100 000 bytes
   ├─ video.py          .webm → animated WebP
   ├─ lottie.py         .tgs → animated WebP
   └─ fit.py            the shared animated encoder and its size ladder
```

Two deliberate boundaries:

- **`packer.py` is the only module that knows the container layout.** If the
  format changes, one file changes.
- **`texts.py` holds every string shown to a user.** Translating the bot touches
  nothing else.

## 4. The splitting algorithm

In [`src/jobs.py`](../src/jobs.py).

**Step A — split by nature.** WhatsApp refuses a pack that mixes animated and
static stickers, so the two families are separated before anything else and are
numbered independently. This is why the buttons read `🖼 1–30` and `🎬 1–30`
rather than a single run across the pack: a batch straddling the boundary would
build a file that fails to import.

**Step B — greedy chunks of 30**, then one fix-up:

```python
batches = [items[i:i + 30] for i in range(0, len(items), 30)]

if len(batches) >= 2 and len(batches[-1]) < 3:
    merged = batches[-2] + batches[-1]
    half = (len(merged) + 1) // 2
    batches[-2:] = [merged[:half], merged[half:]]
```

Greedy alone is what you want — 100 stickers should be `30+30+30+10`, not four
packs of 25 — but it can emit a tail of one or two, which is under WhatsApp's
minimum of three and gets rejected at import. The fix-up rebalances only the last
two chunks, so every other case is untouched:

| input | result |
|---|---|
| 100 | `[30, 30, 30, 10]` |
| 45 | `[30, 15]` |
| 31 | `[16, 15]` |
| 32 | `[16, 16]` |
| 61 | `[30, 16, 15]` |
| 241 | `[30 × 7, 16, 15]` |

A family holding fewer than three stickers in total cannot be fixed by splitting.
The file is built anyway and the caption warns that WhatsApp may reject it.

## 5. The `.wastickers` container

Reverse-engineered from a file produced by the Sticker Maker app itself and
confirmed to import. It is a plain ZIP (DEFLATE, no subdirectories):

```
title.txt              UTF-8, no trailing newline, no BOM, ≤128 chars
author.txt             same
tray.png               PNG, exactly 96×96, ≤50 000 bytes
<prefix>_01.webp       prefix is a Unix timestamp; index zero-padded to 2 digits
<prefix>_02.webp
...
```

Observations that are easy to get wrong:

- **`author.txt` holds the converter bot's own handle**, not the original pack
  author. That is what Sticker Maker's own exports contain.
- **The sticker prefix is the pack's creation timestamp.** When one Telegram pack
  is split into several files generated in the same second, each file needs a
  *distinct* prefix or two packs end up carrying identical sticker names.
- **The WebP payload is lossy with alpha** — RIFF `VP8X` + `ALPH` + `VP8`, not
  lossless `VP8L`. Save with `lossless=False` and a quality value.
- **Alpha is optional.** In a real export, photographic stickers with no
  transparency are plain RGB and import fine. Forcing RGBA is harmless but
  unnecessary.
- **There is no emoji metadata anywhere in the archive.** Telegram's per-sticker
  emoji cannot survive the conversion. This is a property of the format.

### Byte limits are decimal, not binary

```
static    100 000 bytes      not 100 × 1024 = 102 400
animated  500 000 bytes      not 500 × 1024 = 512 000
tray       50 000 bytes      not  50 × 1024 =  51 200
duration   10 000 ms max, 8 ms min
```

Using the binary values lets through files up to 12 000 bytes over the real
ceiling. WhatsApp then rejects the whole pack with a generic error that names no
sticker, which makes the bug intermittent and very hard to trace. Confirmed
against [sticker-convert](https://github.com/laggykiller/sticker-convert).

## 6. Conversion

### Static (`.webp`)

Pillow: open → scale to fit 512×512 preserving aspect ratio → centre on a
transparent 512×512 canvas → save WebP, walking `quality` down from 95 until the
result is at or under 100 000 bytes. No extra padding is added; Telegram sticker
art already carries its own margins.

### Video (`.webm`, VP9 with alpha)

```
ffmpeg -c:v libvpx-vp9 -i in.webm
       -vf "fps=F,scale=512:512:force_original_aspect_ratio=decrease,
            format=rgba,pad=512:512:-1:-1:color=#00000000"
       -t 9.8 -an -c:v libwebp_anim -pix_fmt yuva420p
       -lossless 0 -q:v Q -loop 0 out.webp
```

Naming `libvpx-vp9` as the decoder explicitly is what preserves the alpha channel.

### Lottie (`.tgs`)

`.tgs` is gzipped Lottie JSON — there is no video stream for ffmpeg to decode.
`rlottie` rasterises the vector animation frame by frame at 512×512, and the PNG
sequence goes to the same encoder as the video path. Frames are rendered once at
the source rate; the encoder's `fps` filter drops frames when it needs to shrink
the file.

### The size ladder

Both animated paths share [`convert/fit.py`](../src/convert/fit.py). It retries
with progressively worse settings until the output fits:

```
(80, native) (70, native) (60, native)
(65, 24) (55, 24) (50, 20) (45, 15) (40, 12) (30, 10)
(25, 10) (20, 8) (15, 8)          ← only reachable with a lowered target
```

Quality is given up before smoothness, then both together. The 9.8-second cut and
the 512×512 pad are applied on every attempt. If the last rung still does not fit,
the sticker is reported as skipped rather than shipped oversized — an oversized
sticker would fail the whole pack at import, so dropping one is the cheaper loss.

## 7. Concurrency

- **Downloads** are `asyncio` with a semaphore of 6 and backoff on `RetryAfter`.
- **Conversion is CPU-bound** (Pillow, rlottie, ffmpeg) and runs in a
  `ProcessPoolExecutor` sized to `cpu_count - 1`, driven through
  `loop.run_in_executor`. The event loop stays responsive, so the bot keeps
  answering while a 30-sticker batch is being encoded.
- **One conversion at a time per user**, enforced by `JobStore.claim`. Other
  button taps get an `answerCallbackQuery` rather than a second run.
- **Progress** is one message edited by a background task at most every two
  seconds. Handlers only set a string; nothing awaits Telegram in a hot loop.

On Windows the process pool spawns fresh interpreters that re-import the entry
module, which is why `run.py` guards on `__main__`.

## 8. Failure handling

The rule is that one bad thing should cost you exactly that thing:

- **A sticker that will not fit** is skipped; the batch still ships, and the
  caption lists what was dropped by position and emoji.
- **A batch that fails outright** is reported and the run continues with the
  remaining batches. This was a real bug: a timeout on a 9.2 MB upload used to
  abort the whole run, so the *next* batch was never even attempted.
- **Upload timeouts** are sized for media, not for small API calls
  (`MEDIA_WRITE_TIMEOUT`, 15 minutes). The default timeouts cut off uploads that
  were still succeeding server-side.
- **Progress edits never raise.** A failed cosmetic edit must not break a run.

## 9. State

Deliberately minimal. A `Job` holds the pack metadata, the computed batches, and
which batches are done; it lives in an in-memory dict with a one-hour TTL and is
lost on restart. Rebuilding it costs the user one message, so persistence would
buy little.

`/clear` follows the same reasoning: rather than keeping a ledger of message ids
— which a restart would lose, and which would miss anything sent while the bot was
down — it walks ids backwards from itself. In a private chat they are sequential,
and `deleteMessages` takes 100 at a time and skips whatever it cannot touch.
Telegram's 48-hour limit bounds the whole thing anyway.

## 10. Extending it

`convert_indices(job, indices)` is the shape the conversion path already has: a
batch is just a contiguous range of positions. A picker UI — a Telegram Mini App
showing the pack as a grid so you can choose an arbitrary 30 — would supply a
non-contiguous list and need nothing else from the conversion side.

What it *would* need is infrastructure the current bot deliberately avoids:

- A public **HTTPS** endpoint. Telegram rejects `http://` and `localhost`, so a
  local bot needs a tunnel.
- A web server sharing the bot's event loop, so the job store stays in one process.
- **Thumbnails served through a proxy.** Telegram's file URLs embed the bot token
  (`api.telegram.org/file/bot<TOKEN>/…`); linking them in a page would hand the
  token to anyone who opens it.
- **`initData` HMAC validation** on the endpoint that starts a conversion, or it
  is an open API.

Also worth knowing: from an inline keyboard, `WebApp.sendData()` does not work —
it is reply-keyboard only. The selection has to come back by an authenticated POST
to your own backend.

---

## Appendix: development log

[`PLAN.md`](PLAN.md) (Italian) is the original design document plus a record of
what the first live tests changed and why — including the upload timeout that used
to abort whole runs, and the decimal/binary byte-limit bug. Kept because the
reasoning behind a fix is usually harder to recover than the fix itself.
