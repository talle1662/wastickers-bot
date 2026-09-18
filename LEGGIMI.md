# WhatsApp Sticker Converter Bot

*[🇬🇧 Read this in English](README.md)*

Un bot Telegram che trasforma qualsiasi pacchetto di sticker Telegram in file
`.wastickers` importabili in WhatsApp tramite l'app
[Sticker Maker](https://getstickerpack.com/) — dividendo il pacchetto in
automatico, così che ogni file consegnato a WhatsApp sia valido.

Gli mandi uno sticker. Lui legge tutto il pacchetto a cui appartiene, calcola in
quanti pacchetti WhatsApp va diviso, e ti dà un bottone per ognuno.

```
📦 Il mio pacchetto — 108 sticker
🖼 57 statici · 🎬 51 animati

Un pacchetto WhatsApp contiene al massimo 30 sticker e non può
mischiare statici e animati.

[ ⚡ Converti tutto — 4 file ]
[ 🖼 1–30 ]   [ 🖼 31–57 ]
[ 🎬 1–30 ]   [ 🎬 31–51 ]
```

> Il bot parla italiano. Tutte le stringhe mostrate all'utente stanno in
> [`src/texts.py`](src/texts.py): tradurlo significa toccare un file solo.

## Perché la parte difficile è la divisione

WhatsApp impone due regole che un pacchetto Telegram viola di continuo:

1. **Un pacchetto contiene da 3 a 30 sticker.** Un pacchetto Telegram da 108 non
   può diventare un solo pacchetto WhatsApp.
2. **Un pacchetto non può mischiare animati e statici.** Quelli Telegram spesso lo
   fanno.

Per questo il bot divide *prima* per natura e poi in gruppi da 30 — ed è il motivo
per cui i bottoni sono numerati per famiglia. Un bottone a cavallo tra statici e
animati produrrebbe un file che WhatsApp rifiuta senza spiegazioni.

C'è anche una trappola nella divisione ingenua. I gruppi da 30 trasformano 31
sticker in `30 + 1`, e un pacchetto da uno è sotto il minimo di tre, quindi viene
rifiutato all'import. Quando l'ultimo gruppo sarebbe troppo piccolo, il bot
ribilancia solo gli ultimi due:

```
100 → [30, 30, 30, 10]     ✅
 61 → [30, 16, 15]         ✅  (non 30 + 30 + 1)
 31 → [16, 15]             ✅  (non 30 + 1)
```

In tutti gli altri casi il risultato resta quello ingenuo.

## Funzionalità

- **Sticker statici, video (`.webm`) e Lottie (`.tgs`)**, tutti convertiti in WebP
  conforme a WhatsApp.
- **Un bottone per gruppo** — converti solo l'intervallo che ti serve, o tutto.
  Ogni bottone scarica soltanto la propria fetta, quindi un singolo gruppo è
  rapido anche su un pacchetto da 300.
- **Adattamento automatico del peso.** Tutto ciò che supera il limite di byte di
  WhatsApp viene ricodificato scendendo una scala di qualità e frame rate finché
  non rientra.
- **Gli sticker che non rientrano vengono scartati, non persi in silenzio**: il
  bot ti dice quanti e quali, con posizione ed emoji.
- **Avanzamento in tempo reale** su un solo messaggio, con throttling per non
  incappare nel flood limit.
- **`/clear`** ripulisce la chat (entro le 48 ore che Telegram concede a un bot),
  dietro una conferma a un tap.

## Requisiti

| | |
|---|---|
| Python | 3.11+ (sviluppato su 3.14) |
| ffmpeg | compilato con `libwebp_anim` e un decoder VP9, nel `PATH` |
| Un token | da [@BotFather](https://t.me/BotFather) |

Verifica che il tuo ffmpeg abbia quel che serve:

```bash
ffmpeg -encoders | grep libwebp_anim
```

Se non stampa nulla, la conversione degli animati non funzionerà. Su Windows
prendi una build completa da [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).

## Installazione

```bash
git clone https://github.com/talle1662/wastickers-bot.git
```

```bash
cd wastickers-bot && pip install -r requirements.txt
```

## Configurazione

Copia `.env.example` in `.env` e metti dentro il tuo token:

```
BOT_TOKEN=123456789:AA-il-tuo-token-da-botfather
```

Opzionale, solo se ffmpeg non è nel `PATH`:

```
FFMPEG_BIN=C:\ffmpeg\bin\ffmpeg.exe
```

Viene letto dall'ambiente anche `ANIMATED_TARGET_KB`, che vale `500` — il limite
reale di WhatsApp. Abbassalo solo se stai indagando un problema di dimensioni.

**Non committare mai `.env`.** È in `.gitignore`: lascialo lì. Il token di un bot
Telegram è una credenziale completa, chi ce l'ha controlla il bot.

## Avvio

Il modo più comodo è la console di controllo: doppio clic su **`bot.bat`** su
Windows, oppure **`./bot.sh`** altrove. Si apre una finestra che mostra i log dal
vivo e accetta comandi:

```
/start      avvia il bot
/stop       lo ferma, insieme ai worker di conversione
/restart    lo riavvia
/status     stato, PID, da quanto è attivo
/logs [n]   ultime n righe da logs/bot.log
/cls        pulisce la finestra
/help       questo elenco
/quit       ferma il bot ed esce
```

L'output finisce anche in `logs/bot.log`, così puoi leggere cosa è successo mentre
non guardavi. Chiudendo la console il bot si ferma.

Per avviarlo nudo, senza supervisore:

```bash
python run.py
```

In entrambi i casi il bot vive quanto il suo processo, e solo se la macchina è
accesa e connessa. Per tenerlo sempre attivo serve un servizio systemd,
un'operazione pianificata di Windows, o un process manager.

## Uso

1. Manda al bot uno sticker qualsiasi del pacchetto che ti interessa.
2. Ti risponde con il contenuto del pacchetto e un bottone per gruppo.
3. Tocca un gruppo — oppure `⚡ Converti tutto`.
4. Ogni `.wastickers` ti arriva come file. Aprilo con Sticker Maker sul telefono e
   importalo.

## Limiti da conoscere

- **Le emoji degli sticker si perdono.** Il contenitore `.wastickers` non ha un
  campo per contenerle. È un limite del formato, non del bot.
- **`/clear` arriva solo a 48 ore fa.** Telegram non permette a un bot di
  cancellare messaggi più vecchi, in nessun modo.
- **I job vivono in memoria**, con scadenza a un'ora, e non sopravvivono a un
  riavvio. Se un menù è scaduto, rimanda lo sticker.
- **`com.third-party-stickers error 1000` non è diagnostico.** WhatsApp lo solleva
  sia per errori di validazione sia per problemi transitori, e non nomina mai lo
  sticker colpevole. Riprova l'import prima di dare per scontato che il file sia
  sbagliato: durante i test un file identico ha fallito una volta ed è entrato
  senza problemi al secondo tentativo.

## Architettura

Vedi [`docs/ARCHITETTURA.md`](docs/ARCHITETTURA.md) — copre la mappa dei moduli, le
pipeline di conversione, il modello di concorrenza e una **descrizione completa del
formato `.wastickers`**, ricavata da un file reale e documentata lì perché altrove
è specificata male.

## Riconoscimenti

I limiti in byte di WhatsApp sono stati confermati confrontandoli con
[sticker-convert](https://github.com/laggykiller/sticker-convert) di laggykiller,
un'implementazione matura che vale la pena conoscere se ti servono conversioni che
questo bot non fa.

## Licenza

[MIT](LICENSE).
