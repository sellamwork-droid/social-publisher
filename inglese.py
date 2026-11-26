"""Chiede alle chat la versione inglese dei contenuti italiani già confermati (come il bottone «Fai la versione inglese»).

Power, 26/11 13:33 e 16:59: dopo il Confermato dell'italiano deve partire da sola la versione inglese. Il motore lo fa da
solo dal commit 1a88b34; questo serve per i contenuti confermati prima che il motore sul PC si riavviasse.
Niente doppioni: salta un ID che ha già una consegna inglese o una richiesta in corso.
"""
from __future__ import annotations

import os

from portale import connect

BUONI = ("confermato", "programmato", "pubblicato")


def main() -> None:
    ids = [x.strip() for x in os.environ.get("IDS", "").split(",") if x.strip()]
    supa = connect()
    if not supa:
        raise SystemExit("Portale non collegato")
    for cid in ids:
        it = [r for r in supa.get("pub_consegne", select="id,chat_id,brand,contenuto_id,lingua,stato,slot,uscita,created_at",
                                  contenuto_id=f"eq.{cid}", lingua="eq.IT") if r["stato"] in BUONI]
        if not it:
            print(f"{cid}: nessun italiano confermato, salto"); continue
        c = sorted(it, key=lambda r: r["created_at"])[-1]
        en = [r for r in supa.get("pub_consegne", select="id,stato", contenuto_id=f"eq.{cid}", lingua="eq.EN", brand=f"eq.{c['brand']}")
              if r["stato"] != "annullato"]
        if en:
            print(f"{cid}: la versione inglese c'è già ({en[0]['stato']}), salto"); continue
        gia = supa.get("pub_messages", select="id", chat_id=f"eq.{c['chat_id']}", stato="in.(nuovo,preso)",
                       testo=f"like.VERSIONE INGLESE di {cid}*")
        if gia:
            print(f"{cid}: già chiesta, salto"); continue
        posto = "carosello" if c["slot"] == "carosello" else f"reel {str(c['slot']).replace('reel', '')}"
        a, m, g = c["uscita"].split("-")
        testo = (f"VERSIONE INGLESE di {cid} ({posto} del {int(g)}/{int(m)}/{a}): fai ora la versione inglese di questo contenuto, "
                 "che ho confermato in italiano.")
        r = supa.s.post(f"{supa.url}/rest/v1/pub_messages", timeout=60, headers={"Prefer": "return=minimal"},
                        json={"chat_id": c["chat_id"], "autore": "power", "testo": testo, "consegna_id": c["id"], "stato": "nuovo"})
        r.raise_for_status()
        print(f"{cid}: chiesta a {c['chat_id']}")


if __name__ == "__main__":
    main()
