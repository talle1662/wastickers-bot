# WhatsApp Sticker Converter Bot — Piano di progetto

> Rev. 3 — formato `.wastickers` **confermato** su file reale. Mini App rinviata a dopo la v1.

## 0. Scope della v1

**Dentro**: bot Telegram, download pack, conversione statici + animati (`.webm` / `.tgs`),
split automatico, inline keyboard con **una button per batch**, invio dei `.wastickers`.

**Fuori (rinviato)**: Mini App "Choose stickers" con griglia di selezione. Vedi §10 —
resta progettata ma non implementata, e la v1 è costruita in modo da poterla innestare
senza rifattorizzare (job store e batch già astratti su "lista di indici").

Conseguenza pratica: **niente web server, niente tunnel HTTPS, niente FastAPI**. La v1 è
un singolo processo Python che parla solo con l'API di Telegram.

---

## 1. Stack (verificato sulla macchina)

| Componente | Versione | Ruolo |
|---|---|---|
| Python | 3.14.5 | runtime |
| python-telegram-bot | 22.8 (async) | Bot API |
| Pillow | 12.2 | WebP statici, resize, tray icon |
| rlottie-python | 1.3.8 (`cp37-abi3-win_amd64`) | rendering `.tgs` |
| ffmpeg | 8.1.2 (`libwebp_anim`, `vp9`) | `.webm` → WebP animato |

Tutto già presente o installabile senza attriti. Nessun blocco.

---

## 2. Struttura del repo

```
bot_telegram/
├─ .env                     # BOT_TOKEN
├─ requirements.txt
├─ PLAN.md
└─ src/
   ├─ main.py               # entrypoint
   ├─ config.py             # costanti, limiti, .env
   ├─ jobs.py               # job store in memoria (token -> pack), TTL 1h
   ├─ handlers.py           # /start, sticker handler, callback dei batch
   ├─ keyboard.py           # costruzione dinamica della inline keyboard
   ├─ telegram_fetch.py     # getStickerSet + download concorrente
   ├─ convert/
   │  ├─ static.py          # statico -> WebP 512x512 <100KB
   │  ├─ video.py           # .webm (VP9+alpha) -> WebP animato <500KB
   │  ├─ lottie.py          # .tgs -> WebP animato <500KB
   │  └─ fit.py             # loop di compressione a target di byte
   ├─ packer.py             # splitting + scrittura .wastickers
   └─ util.py               # tempdir, logging, sanitize nomi
```

---

## 3. Formato `.wastickers` — CONFERMATO

Analisi di `Er_budello_de_yamchan1_fStikBot.wastickers` (9 sticker, 312 KB), prodotto dal
bot di riferimento e importato con successo in Sticker Maker.

**Container**: ZIP piatto (nessuna sottocartella), DEFLATE, 12 entry in quest'ordine:

```
title.txt
author.txt
tray.png
1787931681_01.webp
1787931681_02.webp
...
1787931681_09.webp
```

**`title.txt`** — 36 byte, UTF-8 puro, **nessun newline finale, nessun BOM**:
```
Er budello de @yamchan1 :: @fStikBot
```

**`author.txt`** — 28 byte, stesse regole:
```
@WhatsappStickerConverterBot
```
> Risolve la domanda aperta: il bot di riferimento ci mette **il proprio username**, non
> l'autore del pack Telegram. Adottiamo la stessa convenzione.

**`tray.png`** — PNG **96x96 RGBA**, 11.7 KB (limite 50 KB). Nome letterale `tray.png`.

**Sticker** — `<unix_ts>_<NN>.webp`:
- prefisso = timestamp Unix di creazione del pack (`1787931681` = 2026-08-28 15:41:21 UTC,
  coincide con l'ora di generazione del file)
- `NN` = indice **zero-padded a 2 cifre, da `01`** (sufficiente: max 30 per pack)

**Proprietà dei WebP** (tutti e 9):

| Proprietà | Valore osservato |
|---|---|
| Dimensioni | 512x512, tutti |
| Peso | 7.8 – 50.8 KB (limite 100 KB, largo margine) |
| Codifica | RIFF `VP8X` + `ALPH` + `VP8` → **lossy con alpha**, non VP8L lossless |
| Mode | **misto RGBA e RGB** — 02 e 04 non hanno canale alpha |

Due conseguenze per il converter:
1. Si salva con `lossless=False` + `quality`, non lossless. Coerente con il loop di fit (§6.1).
2. L'alpha **non è obbligatorio**: i meme fotografici senza trasparenza restano RGB e
   vengono accettati. Non serve forzare RGBA, anche se farlo è innocuo.

**Non esiste nessun file di metadati emoji** nello ZIP: le emoji degli sticker Telegram
sono definitivamente perse. Limite del formato, non del bot.

**Prefisso per i file multipli**: uno split produce più `.wastickers` nello stesso istante.
Per evitare collisioni di identità tra pack, ogni file riceve un prefisso distinto
(`<ts><batch_idx>`), non lo stesso timestamp ripetuto.

---

## 4. Flusso end-to-end

```
sticker in arrivo
   └─ getStickerSet(set_name)        <- SOLO metadati, nessun download
        └─ classificazione istantanea: is_animated / is_video / statico
             └─ calcolo dei batch (§5) -> inline keyboard (§7)
                  │
                  ├─[batch button]─► download del SOLO sottoinsieme richiesto
                  └─[convert all]──► download completo
                       │
                       └─ conversione (process pool)
                            └─ zip .wastickers (§3)
                                 └─ send_document
```

`getStickerSet` restituisce già `is_animated` e `is_video` per ogni sticker, quindi la
classificazione statico/animato è **gratuita** e disponibile prima di scaricare qualsiasi
cosa. Il menu compare istantaneamente anche su un pack da 120.

---

## 5. Algoritmo di splitting

**Passo A — separazione per tipo** (WhatsApp non permette il mix):

```
statici = [s for s in pack if not (s.is_animated or s.is_video)]
animati = [s for s in pack if     s.is_animated or s.is_video]
```

Le due famiglie sono indipendenti, ognuna con la propria numerazione dei batch. È il motivo
per cui i bottoni non possono essere un "primi 30" sul pack grezzo: un batch a cavallo tra
le due famiglie produrrebbe un file rifiutato all'import.

**Passo B — chunking greedy da 30** dentro ogni famiglia:

```
100 -> [30, 30, 30, 10]      4 file
 60 -> [30, 30]              2 file
 45 -> [30, 15]              2 file
```

**Correzione min-3** (✅ confermata): se l'ultimo chunk ha `< 3` elementi si ribilanciano
**solo gli ultimi due**:

```
31 -> [16, 15]      invece di [30, 1], che verrebbe rifiutato
32 -> [17, 15]
```

Tutti gli altri casi restano invariati: 100 -> `30+30+30+10` è preservato.

**Caso degenere**: famiglia con meno di 3 sticker in totale. Il file viene comunque generato,
con avviso esplicito che WhatsApp potrebbe rifiutarlo.

**Naming**: file `<PackName>_static_1of4.wastickers`, `title.txt` = `<PackName> (1/4)`.

---

## 6. Conversione

### 6.1 Statici (`.webp`)

Pillow: apri -> `thumbnail()` preservando l'aspect ratio -> incolla centrato su canvas
512x512 trasparente (~8 px di padding) -> `save(format="WEBP", lossless=False, quality=q)`.
Fit: `q` da 95 a scendere finché `size <= 100 KB`. Sul pack di riferimento il massimo era
50.8 KB, quindi il loop scatterà raramente.

### 6.2 Video (`.webm`, VP9 con alpha)

```
ffmpeg -c:v libvpx-vp9 -i in.webm \
  -vf "fps=<F>,scale=512:512:force_original_aspect_ratio=decrease,
       pad=512:512:-1:-1:color=#00000000" \
  -t 9.8 -loop 0 -c:v libwebp_anim -lossless 0 -q:v <Q> -an out.webp
```

Il decoder `libvpx-vp9` esplicito serve a preservare il canale alpha.

### 6.3 Lottie (`.tgs`)

`.tgs` = JSON Lottie gzippato. `rlottie-python` -> `LottieAnimation.from_tgs()` -> render
frame per frame a 512x512 RGBA -> assemblaggio in WebP animato. FPS nativo, cappato a 30.

### 6.4 Fit del peso (`convert/fit.py`) — condiviso da 6.2 e 6.3

Gradini successivi finché `size <= 500 KB`:

```
1. quality: 80 -> 65 -> 50 -> 40
2. fps:     nativo -> 24 -> 20 -> 15 -> 12
3. durata:  taglio a 10 s (hard cap)
4. fallback: 10 fps + quality 30
```

**Scarto** (✅ confermato): se resta sopra soglia lo sticker è escluso e il bot riporta
**quanti e quali**, con posizione + emoji:

```
2 stickers skipped (couldn't fit under 500 KB):
  #17 😂   #44 🔥
```

### 6.5 Tray icon

Generata dal **primo sticker del batch**: primo frame se animato, resize a 96x96, PNG RGBA.
Se supera 50 KB si riduce la palette. Sul riferimento pesava 11.7 KB.

---

## 7. UX del bot

### 7.1 `/start`

Messaggio esatto richiesto, con `disable_web_page_preview=True`:

```
👨‍💻 WhatsApp Sticker Converter

Send me any Telegram sticker and I will convert its whole pack into a .wastickers
file you can import with the Sticker Maker (https://getstickerpack.com/) app.

✨ Animated stickers are supported — both video (.webm) and Lottie (.tgs) packs
are converted to animated WebP.
```

### 7.2 Sticker ricevuto — menu dei batch

Risposta **immediata**, nessun download ancora fatto:

```
📦 Er budello de @yamchan1 :: @fStikBot — 120 stickers
🖼 110 static · 🎬 10 animated

A WhatsApp pack holds at most 30 stickers, and can't mix static with animated.

[ ⚡ Convert everything — 5 files ]
[ 🖼 1–30 ]   [ 🖼 31–60 ]
[ 🖼 61–90 ]  [ 🖼 91–110 ]
[ 🎬 1–10 ]
```

- **Una button per batch**, non solo "first 30". Due per riga.
- Numerazione **per famiglia**: se il pack è tutto statico la riga 🎬 non compare.
- Ogni batch scarica **solo il proprio sottoinsieme** → molto più rapido del bot di
  riferimento, che scarica sempre tutto.
- Il bottone premuto si marca ✅ nella keyboard (edit in place): si vede a colpo d'occhio
  cosa è già stato convertito.
- I bottoni restano attivi: si può riconvertire un batch.

**`callback_data`** (limite Bot API: 64 byte) — formato compatto:
```
c:<job8>:<s|a>:<idx>      es. "c:a3f91b2e:s:2"
```

**Pagination**: se una famiglia supera 8 batch (>240 sticker), gli eccedenti finiscono
dietro un bottone `▸ More batches`.

### 7.3 Progresso

Messaggio di stato editato in place, throttling 1 update ogni ~2 s (flood limit):

```
Downloading... 18/30
Converting...  18/30
Building file...
```

### 7.4 Riepilogo finale

```
Done — Er budello de @yamchan1 (1/4), 30 stickers
2 stickers skipped (couldn't fit under 500 KB): #17 😂  #44 🔥
Note: emoji tags aren't carried by the .wastickers format.
```

### 7.5 Errori gestiti

- sticker senza `set_name` (sticker singolo / custom emoji) → messaggio esplicativo
- `getStickerSet` fallisce o pack rimosso
- job scaduto (TTL 1 h) → "This pack expired, send the sticker again."
- secondo job dello stesso utente in parallelo → lock per `user_id`,
  `answerCallbackQuery` "Already working, please wait."

---

## 8. Robustezza e limiti operativi

- **Download**: `asyncio.Semaphore(6)`, retry con backoff su `RetryAfter` ed errori di rete.
- **Conversione**: CPU-bound → `ProcessPoolExecutor(max_workers=cpu_count-1)` via
  `loop.run_in_executor`, così il loop asyncio resta reattivo.
- **Upload**: limite 50 MB per documento. 30 animati x 500 KB ≈ 15 MB, ampio margine.
  Il riferimento con 9 statici pesava 312 KB.
- **Job store**: dict in memoria, TTL 1 h, pulizia periodica. Si perde al riavvio:
  accettabile per uso personale.
- **Disco**: `tempfile.TemporaryDirectory()` per job, rimosso in `finally`.
- **Timing stimato**: 30 statici ≈ 10-20 s; 30 animati ≈ 40-90 s.

---

## 9. Decisioni

| # | Punto | Stato |
|---|---|---|
| 1 | Layout ZIP `.wastickers` | ✅ **confermato su file reale** (§3) |
| 2 | Contenuto di `author.txt` | ✅ risolto: username del bot |
| 3 | Ribilanciamento min-3 (31 → 16+15) | ✅ confermato |
| 4 | Sticker fuori peso: scartare + elencare | ✅ confermato |
| 5 | Bottone `⚡ Convert everything` | 🔸 **da confermare** |
| 6 | Mini App | ⏸️ rinviata a v2 |

---

## 10. Rinviato a v2 — Mini App "Choose stickers"

Progettazione conservata per non riscoprirla da zero. Requisiti emersi:

- Serve **HTTPS pubblico**: Telegram rifiuta `http://` e `localhost`. Su questa macchina
  significa `cloudflared tunnel --url http://localhost:8080` (URL variabile a ogni riavvio,
  quindi da leggere da `.env` e keyboard costruita a runtime).
- Backend FastAPI + uvicorn nello **stesso event loop** di PTB, per condividere il job store
  senza Redis.
- **Il BOT_TOKEN non deve mai raggiungere il browser**: l'URL dei file Telegram è
  `api.telegram.org/file/bot<TOKEN>/...`, quindi le thumbnail vanno servite da un proxy
  lato server, mai linkate direttamente.
- Il `POST /convert` va autenticato validando l'HMAC di `initData`
  (`secret = HMAC_SHA256("WebAppData", BOT_TOKEN)`), altrimenti è un endpoint pubblico.
- Da inline keyboard `WebApp.sendData()` **non funziona** (è solo per reply keyboard):
  il ritorno passa da POST diretto + `WebApp.close()`.

**Aggancio previsto**: la v1 espone già `convert_indices(job, indices) -> [file]`. La Mini
App si limiterà a fornire una lista di indici arbitraria invece di un range contiguo.

---

## 11. Milestone v1

| # | Fase | Deliverable | Verifica |
|---|---|---|---|
| ~~0~~ | ~~Analisi formato~~ | ~~layout ZIP~~ | ✅ **fatto** (§3) |
| 1 | Scheletro bot | `/start` col messaggio esatto | test su Telegram |
| 2 | Fetch + classificazione | menu batch corretto su pack da 120 | conteggio 🖼/🎬 |
| 3 | Conversione statica | WebP 512x512 ≤100 KB, lossy+alpha | confronto byte-level col riferimento |
| 4 | Packer | `.wastickers` importabile | **import reale su telefono** |
| 5 | Batch button + split | ogni bottone produce il suo file | test 1–30 / 31–60 / 91–110 |
| 6 | `.webm` animati | WebP animato ≤500 KB con alpha | import reale |
| 7 | `.tgs` Lottie | idem | import reale |
| 8 | Edge case | 31 / 32 / famiglia da 1 / pack misto | test mirati |
| 9 | Rifinitura | progresso, lock, cleanup, logging | pack da 120 |

**Gate — Fase 4**: finché un `.wastickers` generato da noi non entra davvero in WhatsApp dal
telefono, tutto il resto resta non verificato. Vantaggio ora: abbiamo un file di riferimento
funzionante, quindi la Fase 3-4 si può validare per confronto diretto prima ancora di
passare dal telefono.

---

## 12. Rev. 4 — correzioni dopo il primo test dal vivo

Pacchetto reale da 108 sticker (57 statici, 51 animati), 18 settembre 2026.

**Cosa ha funzionato**: classificazione statici/animati, split per famiglia
(57 -> 30+27, 51 -> 30+21), conversione (0 sticker scartati su 108), import in
Sticker Maker del pacchetto statico.

### 12.1 Timeout sull'upload, che uccideva i batch successivi

`httpx.ReadTimeout` su un documento da 9.2 MB: il file era gia arrivato a
Telegram, ma il client smetteva di aspettare la risposta e l'eccezione abortiva
l'intero run, impedendo la creazione del batch successivo.

Due correzioni:
1. timeout dei media portati a 15 minuti (`MEDIA_WRITE_TIMEOUT`, piu timeout
   espliciti sulla singola `send_document`);
2. ogni batch e ora isolato in un `try/except`: un fallimento viene riportato e
   il run prosegue con i batch rimanenti.

### 12.2 Limiti di peso decimali, non binari

`MAX_ANIMATED_BYTES` era `500 * 1024 = 512000`. Il limite vero e **500 000**.
Idem per gli statici (100 000, non 102 400) e per la tray (50 000, non 51 200).
Un file tra 500 000 e 512 000 byte passava i nostri controlli e veniva rifiutato
da WhatsApp con un errore generico che non nomina lo sticker colpevole.
Valori confermati leggendo `sticker-convert`, implementazione funzionante.

Bug latente e intermittente: non e la causa del fallimento osservato (vedi 12.3),
ma lo sarebbe diventato.

### 12.3 L'errore `com.third-party-stickers 1000` era transitorio

Lo stesso file, reimportato senza essere rigenerato, e entrato senza problemi.
Verificato dal log che nessuna riconversione fosse avvenuta nel frattempo, quindi
i byte erano identici. Causa piu probabile: condivisione verso Sticker Maker
prima che il download da Telegram fosse completo.

**Da ricordare**: questo errore non e diagnostico. Prima di inseguire il formato,
riprovare l'import.

### 12.4 Lingua e presentazione

Tutte le stringhe rivolte all'utente sono in italiano e vivono in `src/texts.py`.
L'immagine profilo e in `assets/profile.png` e va caricata a mano da @BotFather
(`/setuserpic`): l'API dei bot non permette di impostarla.

### 12.5 stdout in UTF-8

La console Windows usa cp1252 e solleva `UnicodeEncodeError` su qualunque emoji
finita in un log. Gli sticker pack ne sono pieni, quindi `setup_logging`
riconfigura ora stdout in UTF-8 con `errors="replace"`.

---

## 13. Rev. 5 — console di controllo

Aggiunta `console.py` con i lanciatori `bot.bat` / `bot.sh`: una finestra che
mostra i log dal vivo e accetta `/start`, `/stop`, `/restart`, `/status`, `/logs`,
`/cls`, `/quit`.

### 13.1 Perche un supervisore e non un semplice avvio

La conversione gira in un pool di worker. Uccidere solo il processo padre li lascia
orfani: memoria occupata e, soprattutto, il rischio che una seconda istanza entri
in conflitto con la prima sullo stesso token. Il figlio parte quindi in un gruppo
di processi dedicato, riceve CTRL_BREAK per chiudere in modo pulito, e viene poi
spazzato con `taskkill /T`.

### 13.2 Il bug che e costato piu tempo

Il figlio ereditava lo stdin della console. Conseguenza: nell'istante in cui il
thread principale si bloccava su `input()` per leggere un comando, l'output del bot
smetteva di arrivare **del tutto** — nemmeno la prima riga, stampata prima di
qualsiasi chiamata di rete — mentre il processo restava vivo e perfettamente
funzionante. Nessuna eccezione, nessun codice di uscita.

Isolato per bisezione, con un A/B a parita di tutto il resto:

| padre | righe catturate |
|---|---|
| dorme, non legge stdin | 4 |
| legge stdin | 0 |

Correzione: `stdin=subprocess.DEVNULL` sul figlio.

Due errori miei hanno reso la diagnosi piu lenta del necessario:

1. il pump aveva un `except Exception: pass` che avrebbe nascosto qualunque errore
   reale. Ora l'errore viene mostrato;
2. il pump stampava la riga **prima** di scriverla su file, quindi quando la stampa
   si bloccava restava vuoto anche il log su disco — l'unico artefatto che avrebbe
   potuto spiegare il guasto. Ora si scrive prima su file.

**Da ricordare**: un processo supervisionato non deve ereditare lo stdin di chi lo
supervisiona, e un handler che ingoia le eccezioni in un percorso diagnostico e un
bug travestito da robustezza.
