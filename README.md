# social-publisher — pubblicazione automatica AXUX + VOLWICK

Un solo motore per i due brand. Regole per chi produce (cartelle, nomi, conferma, orari): **`REGOLE.md`**.
Qui sotto il funzionamento tecnico.

## Come gira

`.github/workflows/publisher.yml` avvia `publish.py` ogni ora (minuto 7). Lo script:

1. legge `DA MANDARE/<BRAND>/<AAAA-MM-GG>/` su Drive (oggi e i prossimi `lookahead_days`)
2. per ogni file decide account e slot (`plan.py`)
3. prepara i media (`media.py`):
   - copertine in JPEG 1080×1920 sotto i 2 MB
   - per TikTok, copertina messa come primo frame del video
4. carica tutto su Blotato e programma il post all'orario dello slot (`blotato.py`)
5. scrive lo stato in `_stato.json` dentro il pacchetto (niente doppioni) e una riga nel foglio "Log"
6. a pacchetto completo lo sposta in `PUBBLICATI/<BRAND>/`

Un errore (descrizione mancante, account non collegato, problema di rete) non blocca gli altri post. Viene scritto nello stato e nel foglio, e i post in errore vengono riprovati all'ora successiva.

## File

| File | Cosa fa |
|---|---|
| `config.yaml` | account Blotato, fusi, orari degli slot, impostazioni TikTok/YouTube |
| `publish.py` | programma principale |
| `plan.py` | dai nomi dei file ai post da fare |
| `media.py` | copertine e primo frame TikTok (ffmpeg) |
| `blotato.py` | API Blotato |
| `storage.py` | Drive (produzione) o cartella locale (test) |

## Secrets da impostare (GitHub → Settings → Secrets and variables → Actions)

| Nome | Valore |
|---|---|
| `BLOTATO_API_KEY` | Blotato → Settings → API |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | contenuto del file JSON del service account Google (Drive API + Sheets API attive) |
| `DRIVE_INBOX_FOLDER_ID` | ID della cartella `DA MANDARE` (la parte finale del link della cartella) |
| `DRIVE_PUBLISHED_FOLDER_ID` | ID della cartella `PUBBLICATI` |
| `SHEET_ID` | (facoltativo) ID del foglio cruscotto con una scheda chiamata `Log` |

Le cartelle `DA MANDARE` e `PUBBLICATI` e il foglio vanno condivisi come **Editor** con l'email del service account.

## Prove

```bash
pip install -r requirements.txt
python publish.py --accounts                      # ID degli account collegati su Blotato
python publish.py --dry-run                       # cosa farebbe su Drive, senza toccare nulla
python publish.py --local ./in ./out --dry-run    # prova su cartelle locali
```

Da GitHub: Actions → "Pubblicazione social" → Run workflow. La casella "Solo prova" è attiva di default.

## Quando si collegano gli Instagram USA

1. `python publish.py --accounts` per leggere i loro ID.
2. Mettere gli ID in `config.yaml` (campo `blotato_id` di `ig_us` per AXUX e VOLWICK).
3. Commit.

Finché l'ID è `null`, i post per quell'account risultano "saltato".
