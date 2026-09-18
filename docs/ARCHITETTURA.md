# Architettura

*[🇬🇧 English version](ARCHITECTURE.md)*

## 1. Cosa fa davvero il bot

Un pacchetto di sticker Telegram e uno WhatsApp non sono lo stesso oggetto. Un
pacchetto Telegram diventa *n* pacchetti WhatsApp, e la corrispondenza è vincolata
da regole facili da violare che, quando vengono violate, producono un unico errore
poco utile.

Tutto il progetto discende da tre vincoli:

| Vincolo | Origine | Conseguenza |
|---|---|---|
| 3–30 sticker per pacchetto | WhatsApp | un pacchetto da 108 va diviso |
| Niente mix animati/statici | WhatsApp | va diviso *prima* per natura |
| 100 000 / 500 000 byte per sticker | WhatsApp | ogni sticker va ricodificato |

## 2. Flusso dei dati

```
messaggio con sticker
    │
    ├─ sticker.set_name ──► getStickerSet()       solo metadati, nessun download
    │                          │
    │                          └─ is_animated / is_video per ogni sticker
    │                               │
    │                               ├─ divisione per famiglia: statici | animati
    │                               └─ gruppi da ≤30 dentro ogni famiglia
    │                                    │
    │                                    └─ tastiera inline, un bottone per gruppo
    │
    └─[bottone]─► scarica solo la fetta richiesta   asyncio, semaforo a 6
                     │
                     └─ conversione                 ProcessPoolExecutor
                          │  ├─ .webp  → Pillow
                          │  ├─ .webm  → ffmpeg (libvpx-vp9 → libwebp_anim)
                          │  └─ .tgs   → rlottie → frame PNG → ffmpeg
                          │
                          └─ impacchetta in .wastickers   zip
                               │
                               └─ send_document
```

La proprietà importante: **`getStickerSet` dice già se ogni sticker è animato**,
quindi la classificazione non costa nulla e avviene prima di scaricare qualsiasi
cosa. Il menù dei gruppi compare istantaneamente anche su un pacchetto da 300, e
ogni bottone scarica poi soltanto i suoi 30 file.

## 3. Mappa dei moduli

```
bot.bat / bot.sh        lanciatori che aprono la console di controllo
console.py              supervisore: log dal vivo più /start, /stop, /status
run.py                  entry point; la guardia __main__ conta su Windows
src/
├─ main.py              wiring degli handler, timeout, process pool
├─ config.py            credenziali, limiti WhatsApp, parametri
├─ texts.py             tutte le stringhe mostrate all'utente
├─ jobs.py              StickerRef / Family / Job, algoritmo di divisione, job store
├─ keyboard.py          costruzione della tastiera, numerazione per famiglia
├─ telegram_fetch.py    getStickerSet + download concorrenti con retry
├─ handlers.py          /start, /clear, ricezione sticker, run di conversione
├─ packer.py            il contenitore .wastickers — l'unico modulo che ne sa il formato
├─ util.py              logging, sanitizzazione dei nomi file
└─ convert/
   ├─ __init__.py       convert_one(): punto d'ingresso del process pool
   ├─ canvas.py         adattamento di un'immagine alla tela 512×512
   ├─ static.py         statico → WebP sotto 100 000 byte
   ├─ video.py          .webm → WebP animato
   ├─ lottie.py         .tgs → WebP animato
   └─ fit.py            encoder animato condiviso e la sua scala di compressione
```

Due confini voluti:

- **`packer.py` è l'unico modulo che conosce il formato del contenitore.** Se il
  formato cambia, cambia un file solo.
- **`texts.py` contiene ogni stringa rivolta all'utente.** Tradurre il bot non
  tocca nient'altro.

## 4. L'algoritmo di divisione

In [`src/jobs.py`](../src/jobs.py).

**Passo A — divisione per natura.** WhatsApp rifiuta un pacchetto che mischia
animati e statici, quindi le due famiglie vengono separate prima di tutto e
numerate in modo indipendente. È per questo che i bottoni dicono `🖼 1–30` e
`🎬 1–30` invece di una numerazione unica: un gruppo a cavallo del confine
costruirebbe un file che fallisce l'import.

**Passo B — gruppi da 30**, più una correzione:

```python
batches = [items[i:i + 30] for i in range(0, len(items), 30)]

if len(batches) >= 2 and len(batches[-1]) < 3:
    merged = batches[-2] + batches[-1]
    half = (len(merged) + 1) // 2
    batches[-2:] = [merged[:half], merged[half:]]
```

La divisione ingenua è quella che si vuole — 100 sticker devono fare
`30+30+30+10`, non quattro pacchetti da 25 — ma può produrre una coda di uno o
due elementi, sotto il minimo di tre di WhatsApp, che viene rifiutata all'import.
La correzione ribilancia soltanto gli ultimi due gruppi, lasciando intatto ogni
altro caso:

| ingresso | risultato |
|---|---|
| 100 | `[30, 30, 30, 10]` |
| 45 | `[30, 15]` |
| 31 | `[16, 15]` |
| 32 | `[16, 16]` |
| 61 | `[30, 16, 15]` |
| 241 | `[30 × 7, 16, 15]` |

Una famiglia con meno di tre sticker in totale non è sanabile dividendo. Il file
viene costruito comunque e la didascalia avvisa che WhatsApp potrebbe rifiutarlo.

## 5. Il contenitore `.wastickers`

Ricavato da un file prodotto dall'app Sticker Maker stessa e verificato
importabile. È un normale ZIP (DEFLATE, nessuna sottocartella):

```
title.txt              UTF-8, nessun newline finale, nessun BOM, max 128 caratteri
author.txt             idem
tray.png               PNG, esattamente 96×96, max 50 000 byte
<prefisso>_01.webp     il prefisso è un timestamp Unix; indice a 2 cifre
<prefisso>_02.webp
...
```

Dettagli facili da sbagliare:

- **`author.txt` contiene lo username del bot convertitore**, non l'autore del
  pacchetto originale. È ciò che contengono gli export di Sticker Maker.
- **Il prefisso degli sticker è il timestamp di creazione.** Quando un pacchetto
  Telegram viene diviso in più file generati nello stesso secondo, ogni file
  richiede un prefisso *distinto*, altrimenti due pacchetti finiscono per avere
  sticker con nomi identici.
- **Il payload WebP è lossy con alpha** — RIFF `VP8X` + `ALPH` + `VP8`, non `VP8L`
  lossless. Si salva con `lossless=False` e un valore di qualità.
- **L'alpha è facoltativo.** In un export reale gli sticker fotografici senza
  trasparenza sono RGB puro e vengono importati senza problemi. Forzare RGBA è
  innocuo ma inutile.
- **Non esiste alcun metadato sulle emoji nell'archivio.** Le emoji per sticker di
  Telegram non possono sopravvivere alla conversione. È una proprietà del formato.

### I limiti in byte sono decimali, non binari

```
statico    100 000 byte      non 100 × 1024 = 102 400
animato    500 000 byte      non 500 × 1024 = 512 000
tray        50 000 byte      non  50 × 1024 =  51 200
durata      10 000 ms max, 8 ms min
```

Usare i valori binari lascia passare file fino a 12 000 byte oltre il limite reale.
WhatsApp rifiuta allora l'intero pacchetto con un errore generico che non nomina
nessuno sticker, il che rende il bug intermittente e molto difficile da tracciare.
Valori confermati confrontandoli con
[sticker-convert](https://github.com/laggykiller/sticker-convert).

## 6. Conversione

### Statici (`.webp`)

Pillow: apertura → ridimensionamento dentro 512×512 preservando le proporzioni →
centratura su una tela 512×512 trasparente → salvataggio WebP, scendendo con
`quality` da 95 finché il risultato non sta entro 100 000 byte. Non viene aggiunto
padding: la grafica degli sticker Telegram ha già i suoi margini.

### Video (`.webm`, VP9 con alpha)

```
ffmpeg -c:v libvpx-vp9 -i in.webm
       -vf "fps=F,scale=512:512:force_original_aspect_ratio=decrease,
            format=rgba,pad=512:512:-1:-1:color=#00000000"
       -t 9.8 -an -c:v libwebp_anim -pix_fmt yuva420p
       -lossless 0 -q:v Q -loop 0 out.webp
```

Indicare esplicitamente `libvpx-vp9` come decoder è ciò che preserva il canale
alpha.

### Lottie (`.tgs`)

`.tgs` è JSON Lottie compresso con gzip: non c'è alcun flusso video da decodificare
per ffmpeg. `rlottie` rasterizza l'animazione vettoriale frame per frame a 512×512,
e la sequenza PNG va allo stesso encoder del percorso video. I frame vengono
generati una volta sola al frame rate nativo; il filtro `fps` dell'encoder ne scarta
quando serve rimpicciolire il file.

### La scala di compressione

Entrambi i percorsi animati condividono [`convert/fit.py`](../src/convert/fit.py),
che riprova con impostazioni via via peggiori finché l'output non rientra:

```
(80, nativo) (70, nativo) (60, nativo)
(65, 24) (55, 24) (50, 20) (45, 15) (40, 12) (30, 10)
(25, 10) (20, 8) (15, 8)          ← raggiungibili solo con un target abbassato
```

Si sacrifica prima la qualità, poi la fluidità, poi entrambe. Il taglio a 9,8
secondi e il pad a 512×512 vengono applicati a ogni tentativo. Se nemmeno l'ultimo
gradino basta, lo sticker viene segnalato come scartato invece di essere spedito
fuori misura: uno sticker sovradimensionato farebbe fallire l'intero pacchetto
all'import, quindi perderne uno costa meno.

## 7. Concorrenza

- **I download** sono `asyncio` con semaforo a 6 e backoff su `RetryAfter`.
- **La conversione è CPU-bound** (Pillow, rlottie, ffmpeg) e gira in un
  `ProcessPoolExecutor` dimensionato a `cpu_count - 1`, pilotato da
  `loop.run_in_executor`. L'event loop resta reattivo, quindi il bot continua a
  rispondere mentre codifica un gruppo da 30.
- **Una conversione alla volta per utente**, imposta da `JobStore.claim`. Gli altri
  tocchi ricevono un `answerCallbackQuery` invece di far partire un secondo run.
- **L'avanzamento** è un solo messaggio modificato da un task in background al
  massimo ogni due secondi. Gli handler si limitano a impostare una stringa.

Su Windows il process pool genera interpreti nuovi che reimportano il modulo di
avvio: per questo `run.py` ha la guardia su `__main__`.

## 8. Gestione dei fallimenti

La regola è che una cosa andata male deve costare esattamente quella cosa:

- **Uno sticker che non rientra** viene scartato; il gruppo parte lo stesso e la
  didascalia elenca cosa è stato tolto, con posizione ed emoji.
- **Un gruppo fallito** viene segnalato e il run prosegue con i gruppi rimanenti.
  Questo è stato un bug reale: un timeout su un upload da 9,2 MB abortiva l'intero
  run, quindi il gruppo *successivo* non veniva nemmeno tentato.
- **I timeout di upload** sono dimensionati per i media, non per le chiamate API
  brevi (`MEDIA_WRITE_TIMEOUT`, 15 minuti). Quelli di default troncavano upload che
  lato server stavano riuscendo.
- **Le modifiche di avanzamento non sollevano mai eccezioni.** Una modifica
  cosmetica fallita non deve interrompere un run.

## 9. Stato

Volutamente minimo. Un `Job` contiene i metadati del pacchetto, i gruppi calcolati e
quali sono già stati convertiti; vive in un dizionario in memoria con scadenza a
un'ora e si perde al riavvio. Ricostruirlo costa all'utente un messaggio, quindi la
persistenza porterebbe poco.

`/clear` segue lo stesso ragionamento: invece di tenere un registro degli id dei
messaggi — che un riavvio perderebbe, e che mancherebbe tutto ciò che è passato
mentre il bot era spento — scorre gli id a ritroso partendo da sé stesso. In una
chat privata sono sequenziali, e `deleteMessages` ne prende 100 alla volta saltando
quelli che non può toccare. Il limite di 48 ore di Telegram delimita comunque tutto.

## 10. Come estenderlo

`convert_indices(job, indices)` è già la forma del percorso di conversione: un
gruppo non è altro che un intervallo contiguo di posizioni. Un'interfaccia di
selezione — una Mini App Telegram che mostra il pacchetto a griglia per scegliere 30
sticker qualsiasi — fornirebbe una lista non contigua e non richiederebbe altro dal
lato conversione.

Richiederebbe invece l'infrastruttura che il bot attuale evita di proposito:

- Un endpoint **HTTPS** pubblico. Telegram rifiuta `http://` e `localhost`, quindi
  un bot locale ha bisogno di un tunnel.
- Un web server che condivide l'event loop del bot, così il job store resta in un
  solo processo.
- **Thumbnail servite tramite proxy.** Gli URL dei file Telegram contengono il token
  del bot (`api.telegram.org/file/bot<TOKEN>/…`): metterli in una pagina
  consegnerebbe il token a chiunque la apra.
- **Validazione HMAC di `initData`** sull'endpoint che avvia una conversione,
  altrimenti è un'API aperta.

Da sapere inoltre: da una tastiera inline `WebApp.sendData()` non funziona, è
riservata alle reply keyboard. La selezione deve tornare indietro con una POST
autenticata verso il proprio backend.

---

## 11. La console di controllo

`console.py` esegue il bot come processo figlio, riversa il suo output nella
finestra e in `logs/bot.log`, e accetta `/start`, `/stop`, `/restart`, `/status`,
`/logs`.

Esiste perché fermare il bot non è semplicemente uccidere un processo: la
conversione avviene in un pool di worker, e uccidere solo il padre può lasciarli
orfani, con la memoria occupata e — peggio — una seconda istanza che poi entra in
conflitto con la prima sullo stesso token. Quindi il figlio parte in un gruppo di
processi suo (`CREATE_NEW_PROCESS_GROUP` su Windows, `start_new_session` altrove),
gli si chiede di fermarsi con `CTRL_BREAK`/`SIGINT` così python-telegram-bot chiude
in modo pulito, e infine si passa `taskkill /T` (o `SIGKILL` al gruppo) perché non
sopravviva nulla.

### Il figlio non deve ereditare lo stdin della console

```python
subprocess.Popen(..., stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
```

Questa riga regge tutto. Senza, l'output del bot supervisionato smette di arrivare
nell'istante in cui il padre si blocca in lettura di un comando dal proprio stdin —
e smette *del tutto*, prima ancora della prima riga di log, mentre il processo
resta vivo e funzionante. Nessun errore, nessun codice di uscita: il pannello dei
log resta semplicemente vuoto e il bot funziona benissimo, il che rende la causa
difficilissima da indovinare partendo dal sintomo.

È stata isolata per bisezione: un padre che dorme cattura l'output del figlio, un
padre che legge stdin non cattura nulla, a parità di tutto il resto. Un processo in
background supervisionato non ha comunque alcun motivo di leggere lo stdin della
console, quindi reindirizzarlo sul dispositivo nullo è la forma giusta a
prescindere dal meccanismo Windows sottostante.

Nella stessa funzione c'è una seconda lezione, più piccola: il pump scrive ogni
riga sul file di log *prima* di stamparla. La prima versione stampava per prima, e
quando la stampa si bloccava restava vuoto anche il log su disco — l'unico
artefatto che avrebbe potuto spiegare il guasto era proprio quello che il guasto
distruggeva.

---

## Appendice: storico di sviluppo

[`PLAN.md`](PLAN.md) è il documento di progetto originale, più il resoconto di cosa
hanno cambiato i primi test dal vivo e perché — incluso il timeout di upload che
abortiva interi run e il bug dei limiti decimali contro binari. È conservato perché
il ragionamento dietro una correzione di solito è più difficile da recuperare della
correzione stessa.
