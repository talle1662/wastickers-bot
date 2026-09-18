# Contributing · Come contribuire

*English first, italiano sotto.*

---

## English

Contributions are welcome. A few things that will save you time:

### Read the architecture doc first

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) explains why the code is shaped the
way it is — in particular the splitting algorithm and the `.wastickers` container
format, both of which have non-obvious constraints that are easy to break by
"simplifying".

### Before you change anything about the output format

The `.wastickers` layout was reverse-engineered from a file produced by the
Sticker Maker app and verified by actually importing the result on a phone.
**Unit tests cannot tell you whether a pack imports.** If you touch
[`src/packer.py`](src/packer.py) or any of `src/convert/`, import the result into
WhatsApp before opening the PR, and say in the PR that you did.

Be especially careful with the byte limits: they are decimal (100 000 / 500 000),
not binary. Using `* 1024` produces files that pass every local check and are
rejected by WhatsApp with an error that names nothing.

### Setup

```bash
pip install -r requirements.txt
```

You need ffmpeg with `libwebp_anim` and a VP9 decoder. Verify with
`ffmpeg -encoders | grep libwebp_anim`.

Copy `.env.example` to `.env` and add a token from [@BotFather](https://t.me/BotFather).
**Never commit `.env`,** and never paste a bot token into an issue or PR — it is a
full credential for that bot.

### Style

- Match the surrounding code. No formatter is enforced.
- Comments explain *why*, not *what*. Most comments in this codebase exist because
  something non-obvious bit us.
- User-facing strings go in [`src/texts.py`](src/texts.py), never inline.

### Translations

The bot currently speaks Italian. `src/texts.py` is the only file holding
user-facing text, so adding a language is a contained change. If you add one,
please also say in the PR which locale you tested it in.

---

## Italiano

I contributi sono benvenuti. Qualche cosa che ti farà risparmiare tempo:

### Leggi prima il documento di architettura

[`docs/ARCHITETTURA.md`](docs/ARCHITETTURA.md) spiega *perché* il codice ha questa
forma — in particolare l'algoritmo di divisione e il formato del contenitore
`.wastickers`, entrambi con vincoli poco ovvi che è facile rompere
"semplificando".

### Prima di cambiare qualcosa nel formato di output

Il layout `.wastickers` è stato ricavato da un file prodotto dall'app Sticker Maker
e verificato importando davvero il risultato su un telefono. **Nessun test
automatico può dirti se un pacchetto si importa.** Se tocchi
[`src/packer.py`](src/packer.py) o qualcosa in `src/convert/`, importa il risultato
in WhatsApp prima di aprire la PR, e scrivi nella PR che l'hai fatto.

Attenzione soprattutto ai limiti in byte: sono decimali (100 000 / 500 000), non
binari. Usare `* 1024` produce file che passano ogni controllo locale e vengono
rifiutati da WhatsApp con un errore che non nomina nulla.

### Preparazione

```bash
pip install -r requirements.txt
```

Serve ffmpeg con `libwebp_anim` e un decoder VP9. Verifica con
`ffmpeg -encoders | grep libwebp_anim`.

Copia `.env.example` in `.env` e aggiungi un token da
[@BotFather](https://t.me/BotFather). **Non committare mai `.env`**, e non
incollare mai un token in una issue o in una PR: è una credenziale completa per
quel bot.

### Stile

- Uniformati al codice circostante. Non è imposto alcun formatter.
- I commenti spiegano il *perché*, non il *cosa*. Quasi tutti i commenti di questo
  progetto esistono perché qualcosa di poco ovvio ci ha morso.
- Le stringhe rivolte all'utente vanno in [`src/texts.py`](src/texts.py), mai
  scritte inline.

### Traduzioni

Il bot parla italiano. `src/texts.py` è l'unico file che contiene testo rivolto
all'utente, quindi aggiungere una lingua è una modifica contenuta. Se ne aggiungi
una, indica nella PR in quale locale l'hai provata.
