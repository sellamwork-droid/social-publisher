# Regole di pubblicazione — AXUX + VOLWICK

Unico sistema, uguali regole per i due brand. Ogni chat che produce contenuti per AXUX o VOLWICK segue questo file.
(Copia anche nel Project AXUX: `sistema-pubblicazione-axux-volwick.md`. In caso di differenze vale questo file.)

## 0. Regola n.1 — si pubblica solo ciò che Power conferma
- La chat mostra a Power video, copertine, descrizioni e caroselli, poi aspetta.
- Solo quando Power scrive **"confermato"** la chat salva il pacchetto su Drive in `DA MANDARE/<BRAND>/<AAAA-MM-GG>/` e ci aggiunge il file vuoto **`CONFERMATO.txt`**.
- Senza `CONFERMATO.txt` il sistema non pubblica niente di quel pacchetto. Lo lascia in attesa.
- Se Power chiede modifiche, la chat corregge e aspetta di nuovo "confermato".

## 1. Come funziona
Chat (producono, Power conferma) → Drive `DA MANDARE/AXUX` e `DA MANDARE/VOLWICK` → questo repository (GitHub Actions, ogni ora) → Blotato → Instagram / YouTube (TikTok in pausa).
Il sistema non manda comandi alle chat. Pubblica solo pacchetti confermati.

## 2. Cartelle su Drive (uguali per i due brand)
```
DA MANDARE/
  AXUX/<AAAA-MM-GG>/
  VOLWICK/<AAAA-MM-GG>/
PUBBLICATI/            ← il sistema ci sposta i pacchetti finiti
```
Dentro ogni pacchetto (la data è il giorno di uscita):
```
CONFERMATO.txt         ← obbligatorio, solo dopo il "confermato" di Power
reel1_IT.mp4  reel1_IT.txt  reel1_IT_cover.png
reel1_EN.mp4  reel1_EN.txt  reel1_EN_cover.png
reel2_IT.mp4 … reel2_EN.mp4 …
carosello_IT/01.png 02.png … carosello_IT.txt
carosello_EN/01.png 02.png … carosello_EN.txt
short1_EN.mp4 short1_EN.txt short1_EN_cover.png   ← facoltativo, altrimenti su YouTube va reel1_EN
_stato.json            ← lo scrive il sistema, non toccarlo
```
Il sistema prende i pacchetti di oggi e dei 2 giorni dopo. Le altre cartelle già presenti su Drive non vengono toccate.

## 3. Dove va ogni file
| File | Va su |
|---|---|
| `reelN_IT.mp4` | Instagram italiano |
| `reelN_EN.mp4` | Instagram USA (.official) + TikTok + YouTube Shorts |
| `shortN_EN.mp4` | YouTube Shorts al posto di `reelN_EN` |
| `carosello_IT/` | Instagram italiano |
| `carosello_EN/` | Instagram USA + TikTok (carosello foto) |

## 4. Volume per brand al giorno
Instagram IT: 2 reel + 1 carosello · Instagram USA: 2 reel + 1 carosello (traduzione esatta dell'IT) · TikTok: 2 reel + 1 carosello (in pausa) · YouTube Shorts: 2.

## 5. File
- **Video:** verticale 9:16, MP4 H.264 + AAC, 3 s – 3 min. Su TikTok il sistema mette da solo la copertina come primo frame.
- **Copertina** `<nome>_cover.png/.jpg`: verticale 1080×1920 o 4K. Se manca, si usa il primo frame. Miniatura YouTube solo con canale verificato.
- **Carosello:** `01.png` … massimo 10, stesso formato (4:5 1080×1350 consigliato).
- **Descrizione** `<nome>.txt` (obbligatoria, lingua dell'account):
  - AXUX: `→ axux.com | AXUX5 · 5% OFF` / hook / hashtag
  - VOLWICK: la caption con l'offerta e gli hashtag, come nelle regole di Volwick
  - Riga facoltativa `TITLE: …` = titolo dello Short YouTube (tolta dagli altri social). Senza, il titolo è l'hook.

## 6. Account (ID Blotato in `config.yaml`)
| Brand | Instagram IT | Instagram USA | TikTok (EN) | YouTube (EN) |
|---|---|---|---|---|
| AXUX | @axux.ita | @axux.official (da collegare da AdsPower) | @axux.official (in pausa) | Media axux |
| VOLWICK | da collegare | @volwick.official | @volwick.official (in pausa) | Volwick Official |

Gli Instagram USA si aprono e si ricollegano SOLO dal loro profilo AdsPower con proxy USA.

## 7. Orari (fuso dell'account, si cambiano in `config.yaml`)
| Account | AXUX | VOLWICK |
|---|---|---|
| IG IT (Roma) | reel1 12:45 · carosello 18:00 · reel2 20:30 | 13:00 · 18:30 · 21:00 |
| IG USA (New York) | carosello 09:00 · reel1 12:00 · reel2 18:00 | 09:30 · 12:30 · 18:30 |
| TikTok (New York) | carosello 11:00 · reel1 14:00 · reel2 19:00 | 11:30 · 14:30 · 19:30 |
| Shorts (New York) | short1 14:00 · short2 19:00 | 14:30 · 19:30 |

## 8. Sicurezza
Chiavi solo nei Secrets di GitHub, mai in chat o nei file. Storie con link sticker: solo a mano (limite di Meta). Contenuti dichiarati "fatti con AI" su TikTok e YouTube.
