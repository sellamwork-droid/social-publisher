# Regole di pubblicazione — AXUX + VOLWICK

Unico sistema, uguali regole per i due brand. Ogni chat che produce contenuti per AXUX o VOLWICK segue questo file.
(Copia anche nel Project AXUX: `sistema-pubblicazione-axux-volwick.md`. In caso di differenze vale questo file.)

## Portale Studio Hub (dal 22 novembre 2026)
Il posto unico di Power è il portale **Studio Hub**: piano dei 7 giorni, chat per brand e tipologia (Claude Code sul Mac), consegne con anteprima, bottone **Confermato**, uscite e numeri. Una consegna confermata nel portale esce da sola entro 15 minuti, con le stesse regole di questo file (nomi, copertina, orari, account). Le chat su claude.ai continuano a usare le cartelle di Drive qui sotto.

## 0. Regola n.1 — si pubblica solo ciò che Power conferma
- La chat mostra a Power video, copertine, descrizioni e caroselli, poi aspetta.
- Solo quando Power scrive **"confermato"** la chat salva il contenuto su Drive nella sua cartella (vedi sotto) e ci aggiunge il file vuoto **`CONFERMATO.txt`**.
- Senza `CONFERMATO.txt` il sistema non pubblica niente di quella cartella. La lascia in attesa.
- Se Power chiede modifiche, la chat corregge e aspetta di nuovo "confermato".

## 1. Come funziona
Chat (producono, Power conferma) → Drive `DA MANDARE/<BRAND>/<LINGUA>/<TIPO>/<data>/` → questo repository (GitHub Actions, ogni 3 ore) → Blotato → Instagram / YouTube (TikTok in pausa).
Il sistema non manda comandi alle chat. Pubblica solo cartelle confermate.

## 2. Cartelle su Drive (uguali per i due brand)
Tutto sta in **Il mio Drive → `SOCIAL PUBLISHER`** (https://drive.google.com/drive/folders/16_d9APVUEW4C42TUUd1kcff20L9kOvWy). Non è la vecchia cartella DA MANDARE di AXUX.
I contenuti nascono **in inglese** (EN = Instagram USA, YouTube, TikTok). L'italiano (IT) è la versione per l'Instagram italiano.
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
| `EN/REEL` | Instagram USA (.officiall) + YouTube Shorts + TikTok (in pausa) |
| `IT/REEL` | Instagram italiano |
| `EN/CAROSELLI` | Instagram USA + TikTok (carosello foto, in pausa) |
| `IT/CAROSELLI` | Instagram italiano |
| `EN/STORIE`, `IT/STORIE` (facoltative, `storia1.png/.mp4`…) | storia Instagram USA / italiano |

Storie: per ora le fa Power a mano. Se si usano le cartelle STORIE escono **senza link sticker** (Meta non lo permette via API).

## 4. Volume per brand al giorno
Instagram IT: 2 reel + 1 carosello · Instagram USA: 2 reel + 1 carosello (traduzione esatta dell'IT) · TikTok: 2 reel + 1 carosello (in pausa) · YouTube Shorts: 2.

## 5. File
- **Video:** verticale 9:16, MP4 H.264 + AAC, 3 s – 3 min. Su TikTok il sistema mette da solo la copertina come primo frame.
- **Copertina** `reelN_cover.png/.jpg`: verticale 1080×1920 o 4K. **Obbligatoria per i reel Instagram**: senza copertina il reel IG non esce (errore). Per YouTube e TikTok è facoltativa (YouTube la usa solo se il canale è verificato).
- **Carosello:** `01.png`, `02.png` … massimo 10 su Instagram, stesso formato (4:5 1080×1350 consigliato). Escono **nell'ordine dei numeri** (anche 1, 2, 10 sono in ordine giusto).
- **Descrizione** `reelN.txt` / `descrizione.txt` (obbligatoria, lingua della cartella):
  - AXUX: `→ axux.com | AXUX5 · 5% OFF` / hook / hashtag
  - VOLWICK: la caption con l'offerta e gli hashtag, come nelle regole di Volwick
  - Riga facoltativa `TITLE: …` = titolo dello Short YouTube (tolta dagli altri social). Senza, il titolo è l'hook.
  - **Hashtag: massimo 5** (limite di Instagram e TikTok dal dicembre 2025). Se sono di più il sistema tiene i primi 5 su IG e TikTok, fino a 15 su YouTube, e su YouTube aggiunge `#Shorts`. Metti quindi per primi i 5 più importanti.
  - Facoltativo, per un testo diverso su una piattaforma: `reel1.youtube.txt`, `reel1.tiktok.txt`, `reel1.instagram.txt` (per i caroselli `descrizione.tiktok.txt`…). Senza, vale il `.txt` normale.

## 6. Account (ID Blotato in `config.yaml`)
| Brand | Instagram IT | Instagram USA | TikTok (EN) | YouTube (EN) |
|---|---|---|---|---|
| AXUX | @axux.ita | @axux.officiall | @axux.official (in pausa) | Media axux (non verificato: niente copertina) |
| VOLWICK | @volwick.ita | @volwick.officiall | @volwick.official (in pausa) | Volwick Official |

Gli Instagram USA si aprono e si ricollegano SOLO dal loro profilo AdsPower con proxy USA.

## 7. Orari (fuso dell'account, si cambiano in `config.yaml`)
| Account | AXUX | VOLWICK |
|---|---|---|
| IG IT (Roma) | reel1 14:00 · carosello 17:00 · reel2 19:00 | 15:00 · 18:00 · 20:00 |
| IG USA (New York) | carosello 09:00 · reel1 12:00 · reel2 18:00 | 09:30 · 12:30 · 18:30 |
| TikTok (New York) | carosello 11:00 · reel1 14:00 · reel2 19:00 | 11:30 · 14:30 · 19:30 |
| Shorts (New York) | short1 14:00 · short2 19:00 | 14:30 · 19:30 |

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
