# Regole di pubblicazione — AXUX + VOLWICK

Unico sistema, uguali regole per i due brand. Ogni chat che produce contenuti per AXUX o VOLWICK segue questo file.
(Copia anche nel Project AXUX: `sistema-pubblicazione-axux-volwick.md`. In caso di differenze vale questo file.)

## Almeno 3 uscite al giorno, anche in ritardo (Power, 26 novembre 2026, 17:38)
- «Ogni giorno dobbiamo pubblicare 3 contenuti minimo. Se siamo in ritardo li pubblichiamo lo stesso, troviamo altri orari,
  ma entro oggi. Lo dico io, sono io il capo.» Un giorno non si salta: i confermati si collocano in orari nuovi dello stesso
  giorno. Mai due caroselli nello stesso giorno per brand (Power, 17:47: «non due caroselli in un giorno»). Su richiesta di Power li colloca anche Claude con il workflow «Colloca uscite» (`colloca.py`).

## Collocazione a mano (Power, 26 novembre 2026, 17:15)
- «Rendimi tutto manuale per ora. Quando schiaccio Confermato mi deve buttare su Uscite e mi fa collocare dove voglio io il
  video. E fammi collocare anche quelli già messi, fammi modificare. L'importante è che si modifica Blotato.»
- `collocazione_manuale: true` in `config.yaml`: una consegna confermata nel portale **non esce** finché Power non sceglie
  giorno e ora in Uscite (colonna `ora` di `pub_consegne`, funzione `pub_colloca`). Gli orari dei posti (reel1, reel2…)
  non decidono più l'ora delle consegne del portale.
- Ricollocare un'uscita già programmata: torna «confermato» con l'ora nuova; al giro dopo (entro 15 minuti) il sistema
  cancella su Blotato il post all'orario vecchio e lo riprogramma. Per questo l'ora scelta deve essere almeno 15 minuti dopo.
- Le chat su claude.ai (cartelle di Drive) restano con gli orari dei posti.

## Uscite automatiche: Instagram italiano e YouTube inglese (Power, 26 novembre 2026, 16:47)
- «Metti le uscite automatiche quando scrivo confermato per Instagram italiano, per YouTube inglese e permettimi di scaricare i video.»
- **In automatico** dopo il Confermato di Power: **Instagram italiano** (@axux.ita, @volwick.ita) per l'italiano, **YouTube**
  (Media axux, Volwick Official) per l'inglese.
- **A mano, li pubblica Power**: TikTok (@axux.official, @volwick.official) e Instagram USA (@axux.officiall, @volwick.officiall)
  restano `paused: true`. Power scarica dal portale video, copertina e descrizione alla massima qualità (gli stessi file che
  escono in automatico) e li pubblica lui. Si riaccendono solo quando lo dice Power, togliendo quelle righe.
- (Dal 26/11 03:03 alle 16:47 tutti gli account erano in pausa; i post di quei giorni con l'orario già passato non escono.)

## Portale Studio Hub (dal 22 novembre 2026)
Il posto unico di Power è il portale **Studio Hub**: piano dei 7 giorni, chat per brand e tipologia (Claude Code sul Mac), consegne con anteprima, bottone **Confermato**, uscite e numeri. Una consegna confermata nel portale esce da sola entro 15 minuti, con le stesse regole di questo file (nomi, copertina, orari, account). Le chat su claude.ai continuano a usare le cartelle di Drive qui sotto.

## Dal 26 novembre: Instagram USA riparte, TikTok in italiano (Power, 25 novembre 2026, 00:15)
- «Pubblichiamo anche sugli ig in inglese quando approvo le cose inglesi, ma partendo dal 26 novembre, e anche i tik tok italiani vanno usati per lingua ita per ora.»
- **Instagram USA** (@axux.officiall, @volwick.officiall) riparte con le uscite **dal 26 novembre**: l'inglese che Power conferma va su Instagram USA e YouTube. Prima del 26 resta fermo (`dal: "2026-11-26"` in `config.yaml`).
- **TikTok** (@axux.official, @volwick.official) per ora pubblica **l'italiano**, dalle uscite del 26 novembre, agli stessi orari di Instagram Italia. L'inglese non va più su TikTok.
- **L'inglese non esce mai da solo** (23/11): dopo il Confermato dell'italiano la chat fa la versione inglese (rivista da un revisore madrelingua separato) e la consegna; Power la trova in Approva, sezione Inglese, e la conferma lui. Su claude.ai: la cartella EN prende `CONFERMATO.txt` solo dopo il «confermato» di Power sulla versione inglese.
- I pacchetti del 26 e dopo già programmati prima del cambio ricevono da soli i post nuovi (Instagram USA, TikTok): non serve rifare nulla.
- (Prima: dal 23/11 17:26 Instagram USA e TikTok in pausa, YouTube inglese attivo.)

## 0. Regola n.1 — si pubblica solo ciò che Power conferma
- La chat mostra a Power video, copertine, descrizioni e caroselli, poi aspetta.
- Solo quando Power scrive **"confermato"** la chat salva il contenuto su Drive nella sua cartella (vedi sotto) e ci aggiunge il file vuoto **`CONFERMATO.txt`**.
- Senza `CONFERMATO.txt` il sistema non pubblica niente di quella cartella. La lascia in attesa.
- Se Power chiede modifiche, la chat corregge e aspetta di nuovo "confermato".

## 1. Come funziona
Chat (producono, Power conferma) → Drive `DA MANDARE/<BRAND>/<LINGUA>/<TIPO>/<data>/` → questo repository (GitHub Actions, ogni 3 ore) → Blotato → Instagram / YouTube / TikTok.

**Regola di Power del 25 novembre 2026 (00:15):** «pubblichiamo anche sugli ig in inglese quando approvo le cose inglesi, ma partendo dal 26 novembre, e anche i tik tok italiani vanno usati per lingua ita per ora». Dalle uscite del **26 novembre**: l'inglese confermato da Power va su **Instagram USA** (.officiall) e YouTube; l'italiano va su **Instagram italiano e TikTok** (@axux.official, @volwick.official), allo stesso orario. Prima del 26 TikTok e Instagram USA non pubblicano; i pacchetti del 26 e dopo già programmati ricevono da soli i post nuovi.
Il sistema non manda comandi alle chat. Pubblica solo cartelle confermate.

## 2. Cartelle su Drive (uguali per i due brand)
Tutto sta in **Il mio Drive → `SOCIAL PUBLISHER`** (https://drive.google.com/drive/folders/16_d9APVUEW4C42TUUd1kcff20L9kOvWy). Non è la vecchia cartella DA MANDARE di AXUX.
**Prima l'italiano, poi l'inglese** (regola di Power, 22 novembre 2026, 16:20): ogni contenuto nasce in italiano (IT = Instagram italiano), Power lo approva per primo; dopo il suo Confermato la stessa chat fa la versione inglese dello stesso ID (EN = Instagram USA e YouTube; TikTok per ora è in italiano), adattata al pubblico USA, stesso slot e giorno.
```
SOCIAL PUBLISHER/
  DA MANDARE/
    AXUX/
      EN/  REEL/<AAAA-MM-GG>/   CAROSELLI/<AAAA-MM-GG>/
      IT/  REEL/<AAAA-MM-GG>/   CAROSELLI/<AAAA-MM-GG>/
    VOLWICK/   (uguale)
  PUBBLICATI/  (stessa struttura: il sistema ci sposta le cartelle finite)
```
La data è il **giorno di uscita**. Reel e caroselli si confermano separatamente: ogni cartella-data ha il suo `CONFERMATO.txt`.

**REEL/<data>/**
```
reel1.mp4   reel1.txt   reel1_cover.png
reel2.mp4   reel2.txt   reel2_cover.png
reel3.mp4   reel3.txt   reel3_cover.png
ID.txt                                     ← reel1=A0012 (una riga per reel): lega i post ai numeri
short1.mp4  short1.txt  short1_cover.png   ← solo EN, facoltativo: altrimenti su YouTube va reel1
CONFERMATO.txt
```
**CAROSELLI/<data>/**
```
01.png 02.png 03.png …   (massimo 10)
descrizione.txt          (un solo .txt)
ID.txt                   (l'ID del carosello, es. C0003)
CONFERMATO.txt
```
Il sistema prende le cartelle di oggi e dei 2 giorni dopo. Le altre cartelle su Drive non vengono toccate. (I vecchi nomi `reel1_EN.mp4` funzionano ancora: la lingua la decide la cartella.)

## 3. Dove va ogni cartella
| Cartella | Va su |
|---|---|
| `EN/REEL` | Instagram USA (.officiall, dalle uscite del 26/11) + YouTube Shorts |
| `IT/REEL` | Instagram italiano + TikTok (dalle uscite del 26/11) |
| `EN/CAROSELLI` | Instagram USA (dal 26/11) |
| `IT/CAROSELLI` | Instagram italiano + TikTok (carosello foto, dal 26/11) |
| `EN/STORIE`, `IT/STORIE` (facoltative, `storia1.png/.mp4`…) | storia Instagram USA / italiano |

Storie: per ora le fa Power a mano. Se si usano le cartelle STORIE escono **senza link sticker** (Meta non lo permette via API).

## 4. Volume per brand al giorno
Regola di Power del 24 novembre 2026 (02:51): **3 reel + 1 carosello al giorno per brand**. Dal 25/11 00:50 il piano automatico del portale è spento (Power: «per ora teniamo tutto manuale»): i giorni vuoti si chiedono dalla Regia.
**Il giorno giusto e nessun giorno scoperto** (Power, 25/11 02:04: «noi dobbiamo pubblicare ogni giorno»; «quando il video dice oggi venerdì 27, oppure domani ci sarà questo, deve già andarsi a posizionare sulla data giusta»): un contenuto che parla di un giorno (oggi, domani, «venerdì 27», un dato con la sua data, anche in descrizione o a schermo) va nella cartella del giorno in cui quelle parole sono vere; nel portale lo fa da solo (`"data_fissa": true` in consegna.json, giorno e data scritti per esteso). Gli altri il portale li mette nel primo posto libero da oggi, prima i giorni vuoti più vicini; su Drive la chat sceglie la prima cartella-data con il posto libero.
Instagram IT: 3 reel + 1 carosello · TikTok (italiano, dal 26/11): 3 reel + 1 carosello · Instagram USA (dal 26/11): 3 reel + 1 carosello · YouTube Shorts: 3.

## 5. File
- **Video:** verticale 9:16, MP4 H.264 + AAC, 3 s – 3 min. Su TikTok il sistema mette da solo la copertina come primo frame.
- **Copertina e descrizione obbligatorie per ogni video** (regola di Power, 22 novembre 2026): `reelN_cover.png/.jpg` verticale 1080×1920 o 4K e `reelN.txt` non vuoto. Senza una delle due il video non esce su nessuna piattaforma (errore nel cruscotto e nel portale). YouTube usa la copertina solo se il canale è verificato; su TikTok diventa il primo frame.
- **Carosello:** `01.png`, `02.png` … massimo 10 su Instagram, stesso formato (4:5 1080×1350 consigliato). Escono **nell'ordine dei numeri** (anche 1, 2, 10 sono in ordine giusto).
- **Descrizione** `reelN.txt` / `descrizione.txt` (obbligatoria, lingua della cartella):
  - AXUX: `→ axux.com | AXUX5 · 5% OFF` / hook / hashtag
  - VOLWICK: la caption con l'offerta e gli hashtag, come nelle regole di Volwick
  - Riga facoltativa `TITLE: …` = titolo dello Short YouTube (tolta dagli altri social). Senza, il titolo è l'hook.
  - **Hashtag: massimo 5** (limite di Instagram e TikTok dal dicembre 2025). Se sono di più il sistema tiene i primi 5 su IG e TikTok, fino a 15 su YouTube, e su YouTube aggiunge `#Shorts`. Metti quindi per primi i 5 più importanti.
  - Facoltativo, per un testo diverso su una piattaforma: `reel1.youtube.txt`, `reel1.tiktok.txt`, `reel1.instagram.txt` (per i caroselli `descrizione.tiktok.txt`…). Senza, vale il `.txt` normale.

## 6. Account (ID Blotato in `config.yaml`)
| Brand | Instagram IT | TikTok (per ora IT) | Instagram USA | YouTube (EN) |
|---|---|---|---|---|
| AXUX | @axux.ita | @axux.official (dal 26/11) | @axux.officiall (dal 26/11) | Media axux (non verificato: niente copertina) |
| VOLWICK | @volwick.ita | @volwick.official (dal 26/11) | @volwick.officiall (dal 26/11) | Volwick Official |

In `config.yaml`, `dal: "AAAA-MM-GG"` su un account = pubblica solo i pacchetti da quel giorno; `paused: true` = fermo. Dove va ogni lingua: `plan.py`, `TARGETS`.

Gli Instagram USA si aprono e si ricollegano SOLO dal loro profilo AdsPower con proxy USA.

## 7. Orari (fuso dell'account, si cambiano in `config.yaml`)
| Account | AXUX | VOLWICK |
|---|---|---|
| IG IT (Roma) | reel1 14:00 · carosello 17:00 · reel2 19:00 · reel3 21:00 | 15:00 · 18:00 · 20:00 · 22:00 |
| IG USA (New York) | carosello 09:00 · reel1 12:00 · reel2 18:00 · reel3 21:00 | 09:30 · 12:30 · 18:30 · 21:30 |
| TikTok (Roma, come IG IT) | reel1 14:00 · carosello 17:00 · reel2 19:00 · reel3 21:00 | 15:00 · 18:00 · 20:00 · 22:00 |
| Shorts (New York) | short1 14:00 · short2 19:00 · short3 21:00 | 14:30 · 19:30 · 21:30 |

**Posto già passato** (Power, 25/11 03:07: «avevo accettato un contenuto di volwick e me lo sono ritrovato pubblicato ora»): se l'orario è passato da poco (meno di 2 ore, `late_max_minutes`) il post esce tra 10 minuti; se è passato da più di 2 ore **non esce**: il pacchetto resta confermato e il portale lo rimette nel primo posto libero da oggi, poi esce lì. Mai più un contenuto del giorno prima pubblicato di notte.

## 8. Controllo e centro di controllo
- **Prima del "confermato"** la chat lancia il controllo automatico del cervello del brand (`cervello.py pacchetto …`): con un errore il contenuto non si mostra a Power.
- **Ogni ora** il sistema programma le cartelle nuove, verifica su Blotato i post già passati di orario (pubblicato o fallito) e aggiorna il foglio **SOCIAL PUBLISHER · Cruscotto**:
  - **Calendario**: prossimi 7 giorni per brand, EN/IT reel e carosello: manca, aspetta il tuo confermato, in coda, programmato, pubblicato, errore;
  - **Stato**: una riga per post, con ID del contenuto e link;
  - **Numeri**: views, like, commenti, reach per post (statistiche di Blotato), scritti anche nella memoria dei cervelli AXUX e VOLWICK (`MEMORIA/numeri.json`) per imparare cosa funziona;
  - **Chi lavora**: le chat attive di AXUX e VOLWICK;
  - **Account** e **Storico**.
- Se qualcosa va storto la corsa su GitHub diventa **rossa** e GitHub manda una email.

## 9. Sicurezza
Chiavi solo nei Secrets di GitHub, mai in chat o nei file. Storie con link sticker: solo a mano (limite di Meta). Contenuti dichiarati "fatti con AI" su TikTok e YouTube.

## Qualità su Instagram (Power, 26/11 20:08: «alzare la qualità al massimo»)
Prima dell'invio a Instagram il sistema fa una versione apposta del reel, come la chiede Instagram: 1080x1920, H.264 High, 2 B-frame, GOP chiuso di mezzo secondo, stessa frequenza (23-60 fps), quasi senza perdita (CRF 10) con tetto 22 Mbps e file sotto i 95 MB, colori BT.709, audio AAC 48 kHz stereo 256 kb/s. YouTube riceve l'originale. Instagram ricomprime comunque: così parte dal file migliore che accetta. Su Telegram un video si manda come **file** (Allega › File), non come video, altrimenti Telegram lo comprime.
