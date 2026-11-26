"""Fa rifare alle chat i reel già confermati, per Instagram (Power, 26/11 23:25: «aggiorniamo tutti sti video come ha fatto
questa chat e rimettiamoli qui: l'importante che siano centrati e non escano sgranati»).

IDS = "A0012,A0016,…": per ogni ID trova l'ultima consegna non annullata di ogni lingua (reel), la chat che l'ha fatta, e le
scrive una richiesta come Power (una per ID, italiano e inglese insieme). Le versioni nuove tornano in Approva e, confermate,
prendono il posto di quelle già collocate (stesso giorno e ora). Con PROVA=true stampa e basta."""
from __future__ import annotations

import os

from portale import connect

TESTO = """RIFAI PER INSTAGRAM {cid} ({lingue}): stesso contenuto, stesso copy, stessa voce e stessa durata; cambia solo la resa grafica, perché su Instagram esce sgranato.
1) Centrato: titoli, scritte, sottotitoli, grafici, card e logo sull'asse del video (x 540 su 1080), margini uguali a sinistra e a destra (140 px). Prima del render, fotogrammi di prova con una linea a 540.{volwick}
2) Scritte pulite e nitide, come A0010 di stasera nella chat Reazione al dato: niente grana sopra i testi, niente ombra 3D a strati né riflesso che passa, bagliore leggero, bordi netti, testi grandi e spessi.
3) Sfondo pulito: niente stelline, particelle, polvere o fasci di luce in movimento; poche sfumature scure; se una sfumatura fa strisce, un velo di grana fermo e leggerissimo solo sullo sfondo. Movimenti di camera calmi.
4) Ultimo passo: esportazione per Instagram a 30 fps ({esporta}) e controlla un fotogramma del file esportato prima di consegnare.
Consegna prima l'italiano, poi l'inglese (se c'è). Le versioni nuove mi arrivano in Approva: se le confermo prendono il posto di quelle già in uscita, allo stesso giorno e ora. Non toccare altro."""


def main() -> None:
    supa = connect()
    ids = [x.strip().upper() for x in os.environ.get("IDS", "").split(",") if x.strip()]
    prova = os.environ.get("PROVA") == "true"
    chats = {c["id"]: c for c in supa.get("pub_chats", select="id,titolo,attiva,brand")}
    for cid in ids:
        righe = [r for r in supa.get("pub_consegne", select="id,chat_id,lingua,tipo,stato,versione,created_at,brand", contenuto_id=f"eq.{cid}")
                 if r["stato"] not in ("annullato", "superato") and r["tipo"] == "REEL"]
        if not righe:
            print(f"{cid}: nessun reel in gioco, salto")
            continue
        righe.sort(key=lambda r: r["created_at"])
        chat = next((r["chat_id"] for r in reversed(righe) if r.get("chat_id") and chats.get(r["chat_id"], {}).get("attiva", True)), None)
        if not chat:
            print(f"{cid}: la chat che l'ha fatto non è attiva, salto")
            continue
        # una lingua già uscita non si rifà (resta il post pubblicato)
        uscite = {r["lingua"] for r in righe if r["stato"] == "pubblicato"}
        lingue = sorted({r["lingua"] for r in righe} - uscite, key=lambda l: 0 if l == "IT" else 1)
        if not lingue:
            print(f"{cid}: già uscito in tutte le lingue, salto")
            continue
        brand = chats[chat]["brand"]
        testo = TESTO.format(cid=cid, lingue=" e ".join("italiano" if l == "IT" else "inglese" for l in lingue),
                             volwick=(" Se il motore non è ancora centrato (pull request #401 non ancora dentro), centra dentro la tua scena." if brand == "VOLWICK" else ""),
                             esporta=("python3 00_MOTORE/tools/esporta_ig.py <video finito> reel1.mp4; se nella tua copia non c'è ancora, lo converte il portale" if brand == "VOLWICK" else "python3 tools/esporta_ig.py <video finito> reel1.mp4"))
        stati = ", ".join(f"{r['lingua']} v{r['versione']} {r['stato']}" for r in righe)
        print(f"{cid} → {chat} ({chats[chat]['titolo']}) · {stati}")
        if not prova:
            supa.s.post(f"{supa.url}/rest/v1/pub_messages", timeout=60, headers={"Prefer": "return=minimal"},
                        json={"chat_id": chat, "autore": "power", "testo": testo, "stato": "nuovo"}).raise_for_status()


if __name__ == "__main__":
    main()
