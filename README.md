# WhatsApp Sticker Converter Bot

*[🇮🇹 Leggimi in italiano](LEGGIMI.md)*

A Telegram bot that turns any Telegram sticker pack into `.wastickers` files you
can import into WhatsApp with the [Sticker Maker](https://getstickerpack.com/)
app — splitting the pack automatically so every file WhatsApp gets is a legal one.

Send it one sticker. It reads the whole pack it belongs to, works out how many
WhatsApp packs that becomes, and gives you a button for each.

```
📦 My Sticker Pack — 108 sticker
🖼 57 statici · 🎬 51 animati

Un pacchetto WhatsApp contiene al massimo 30 sticker e non può
mischiare statici e animati.

[ ⚡ Converti tutto — 4 file ]
[ 🖼 1–30 ]   [ 🖼 31–57 ]
[ 🎬 1–30 ]   [ 🎬 31–51 ]
```

> The bot speaks Italian. Every user-facing string lives in
> [`src/texts.py`](src/texts.py), so translating it is a single-file job.

## Why the splitting is the hard part

WhatsApp imposes two rules that a Telegram pack routinely breaks:

1. **A pack holds 3 to 30 stickers.** A 108-sticker Telegram pack cannot be one
   WhatsApp pack.
2. **A pack may not mix animated and static stickers.** Telegram packs often do.

So the bot splits by nature *first*, then into chunks of 30 — which is why the
buttons are numbered per family. A button spanning the static/animated boundary
would produce a file WhatsApp silently refuses.

There is also a trap in the naive chunking. Greedy chunks of 30 turn 31 stickers
into `30 + 1`, and a pack of one is below WhatsApp's minimum of three, so it gets
rejected at import. When the last chunk would fall short, the bot rebalances the
last two:

```
100 → [30, 30, 30, 10]     ✅
 61 → [30, 16, 15]         ✅  (not 30 + 30 + 1)
 31 → [16, 15]             ✅  (not 30 + 1)
```

Everything else keeps the plain greedy result.

## Features

- **Static, video (`.webm`) and Lottie (`.tgs`) stickers**, all converted to
  WhatsApp-compliant WebP.
- **One button per batch** — convert just the range you want, or all of it.
  Each button downloads only its own slice, so a single batch is fast even on a
  300-sticker pack.
- **Automatic size fitting.** Anything over WhatsApp's byte ceiling is re-encoded
  down a quality/frame-rate ladder until it fits.
- **Stickers that cannot be made to fit are skipped, not silently dropped** — the
  bot tells you how many and which ones, by position and emoji.
- **Live progress** on one edited message, throttled so it never trips the flood
  limit.
- **`/clear`** wipes the chat (within the 48 hours Telegram allows a bot to
  delete), behind a one-tap confirmation.

## Requirements

| | |
|---|---|
| Python | 3.11+ (developed on 3.14) |
| ffmpeg | built with `libwebp_anim` and a VP9 decoder, on `PATH` |
| A bot token | from [@BotFather](https://t.me/BotFather) |

Check your ffmpeg has what it needs:

```bash
ffmpeg -encoders | grep libwebp_anim
```

If that prints nothing, the animated conversion will not work. Grab a full build
from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (Windows) or your package
manager's `ffmpeg` with extra codecs.

## Install

```bash
git clone https://github.com/talle1662/wastickers-bot.git
```

```bash
cd wastickers-bot && pip install -r requirements.txt
```

## Configure

Copy `.env.example` to `.env` and put your token in it:

```
BOT_TOKEN=123456789:AA-your-token-from-botfather
```

Optional, only if ffmpeg is not on `PATH`:

```
FFMPEG_BIN=C:\ffmpeg\bin\ffmpeg.exe
```

`ANIMATED_TARGET_KB` is also read from the environment. It defaults to `500`,
WhatsApp's real ceiling; lower it only if you are chasing a size problem.

**Never commit `.env`.** It is in `.gitignore` — keep it there. A Telegram bot
token is a full credential: anyone holding it controls the bot.

## Run

```bash
python run.py
```

The bot runs for as long as that process lives. For an always-on setup use a
systemd unit, a Windows scheduled task, or a process manager of your choice.

## Usage

1. Send the bot any sticker from the pack you want.
2. It replies with the pack's contents and a button per batch.
3. Tap a batch — or `⚡ Converti tutto`.
4. Each `.wastickers` arrives as a file. Open it with Sticker Maker on your phone
   and import.

## Limits worth knowing

- **Emoji tags are lost.** The `.wastickers` container has no field for them.
  This is a limit of the format, not of the bot.
- **`/clear` only reaches 48 hours back.** Telegram does not let a bot delete
  older messages, by any method.
- **Jobs live in memory** with a one-hour TTL and do not survive a restart. If a
  pack menu goes stale, send the sticker again.
- **`com.third-party-stickers error 1000` is not diagnostic.** WhatsApp raises it
  for validation failures *and* for transient ones, and never names the offending
  sticker. Retry the import before assuming the file is wrong — in testing, an
  identical file failed once and imported fine on the second try.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — it covers the module map, the
conversion pipelines, the concurrency model, and a **full description of the
`.wastickers` container format**, reverse-engineered from a real file and
documented there because it is poorly specified anywhere else.

## Credits

The byte-exact WhatsApp limits were confirmed against
[sticker-convert](https://github.com/laggykiller/sticker-convert) by laggykiller,
a mature implementation worth knowing about if you need conversions this bot does
not do.

## License

[MIT](LICENSE).
