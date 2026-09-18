"""Every user-facing string, in one place.

Kept apart from the logic so the bot's language can be changed without touching
any handler.
"""

from __future__ import annotations

START = (
    "\U0001f468‍\U0001f4bb WhatsApp Sticker Converter\n"
    "\n"
    "Mandami uno sticker Telegram qualsiasi e converto tutto il suo pacchetto "
    "in un file .wastickers che puoi importare con l'app Sticker Maker "
    "(https://getstickerpack.com/).\n"
    "\n"
    "✨ Gli sticker animati sono supportati — sia i pacchetti video "
    "(.webm) sia quelli Lottie (.tgs) vengono convertiti in WebP animato."
)

# --- pack intake ---------------------------------------------------------
NO_PACK = (
    "Questo sticker non fa parte di un pacchetto, quindi non c'è niente da "
    "convertire. Le emoji personalizzate e gli sticker singoli non "
    "appartengono a un set."
)
READING = "Leggo il pacchetto…"
READ_FAILED = "Non riesco a leggere il pacchetto: {error}"
EMPTY_PACK = "Il pacchetto è vuoto."
SEND_A_STICKER = "Mandami uno sticker e converto il suo pacchetto."

# --- menu ----------------------------------------------------------------
HEADER = "\U0001f4e6 {title} — {total} sticker"
COUNT_STATIC = "{label} {n} statici"
COUNT_ANIMATED = "{label} {n} animati"
RULES = (
    "Un pacchetto WhatsApp contiene al massimo 30 sticker e non può "
    "mischiare statici e animati."
)
BTN_CONVERT_ALL = "⚡ Converti tutto — {n} file"
BTN_CONVERTED_ALL = "✅ Convertito tutto"
BTN_MORE = "▸ Altri gruppi ({n})"
BTN_FEWER = "▾ Meno gruppi"

# --- callback answers ----------------------------------------------------
EXPIRED = "Pacchetto scaduto — rimandami lo sticker."
NOT_YOURS = "Questo pacchetto non è tuo."
GONE = "Questo gruppo non esiste più."
BUSY = "Sto già lavorando a un pacchetto, aspetta."

# --- run -----------------------------------------------------------------
STARTING = "Inizio…"
DOWNLOADING = "{tag}Scarico… {done}/{total}"
CONVERTING = "{tag}Converto… {done}/{total}"
BUILDING = "{tag}Creo {filename}…"
UPLOADING = "{tag}Carico {filename}…"

NATURE_STATIC = "statici"
NATURE_ANIMATED = "animati"

CAPTION = "{title} — {n} sticker"
CAPTION_SKIPPED = "{n} scartati: {which}"
CAPTION_TOO_FEW = (
    "⚠ Solo {n} sticker — WhatsApp ne vuole almeno {minimum}, "
    "questo file potrebbe essere rifiutato."
)

BATCH_ALL_FAILED = "Non sono riuscito a convertire nessuno sticker del gruppo {range}."
BATCH_FAILED = "Gruppo {range} non riuscito: {error}"
RUN_FAILED = "Qualcosa è andato storto: {error}"

DONE = "Fatto — {n} file."
DONE_SKIPPED = "{n} sticker scartati in totale."
EMOJI_NOTE = "Nota: il formato .wastickers non conserva le emoji degli sticker."

# --- /clear --------------------------------------------------------------
CLEAR_CONFIRM = (
    "\U0001f5d1 Cancello tutta la chat?\n"
    "\n"
    "\u26a0 Spariscono anche i file .wastickers che ti ho mandato. Se non li hai "
    "gi\u00e0 salvati sul telefono non si recuperano."
)
BTN_CLEAR_YES = "\U0001f5d1 S\u00ec, cancella"
BTN_CLEAR_NO = "Annulla"
CLEAR_CANCELLED = "Annullato."
CLEAR_DONE = (
    "\u2705 Chat pulita.\n"
    "I messaggi pi\u00f9 vecchi di 48 ore Telegram non me li lascia cancellare."
)

# --- command menu --------------------------------------------------------
CMD_START = "Come funziona"
CMD_CLEAR = "Cancella la chat"
