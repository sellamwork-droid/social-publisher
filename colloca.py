"""Colloca (o sposta) uscite del portale a un giorno e un'ora precisi, come «Colloca» in Uscite (pub_colloca).

Power, 26/11 17:38: «ogni giorno dobbiamo pubblicare 3 contenuti minimo. Se siamo in ritardo li pubblichiamo lo stesso,
troviamo altri orari, ma entro oggi». Serve quando le uscite le colloca Claude su richiesta di Power.
COLLOCA="C0008=2026-11-26 19:00, A0003=2026-11-26 21:00" (ora italiana; per ID si prende la consegna confermata o
programmata più recente nella LINGUA scelta, default IT). Poi il giro di pubblicazione sposta i post su Blotato.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from portale import connect

ROMA = ZoneInfo("Europe/Rome")


def main() -> None:
    supa = connect()
    if not supa:
        raise SystemExit("Portale non collegato")
    lingua = os.environ.get("LINGUA", "IT") or "IT"
    ora_adesso = datetime.now(timezone.utc)
    for voce in [v.strip() for v in os.environ.get("COLLOCA", "").split(",") if v.strip()]:
        cid, quando_txt = [x.strip() for x in voce.split("=", 1)]
        quando = datetime.strptime(quando_txt, "%Y-%m-%d %H:%M").replace(tzinfo=ROMA)
        if quando.astimezone(timezone.utc) < ora_adesso + timedelta(minutes=10):
            print(f"{cid}: {quando_txt} è troppo vicino o passato, salto"); continue
        righe = [r for r in supa.get("pub_consegne", select="id,chat_id,contenuto_id,lingua,stato,uscita,stato_post,created_at",
                                     contenuto_id=f"eq.{cid}", lingua=f"eq.{lingua}")
                 if r["stato"] in ("confermato", "programmato", "errore")]
        if not righe:
            print(f"{cid}: nessuna consegna {lingua} confermata o programmata, salto"); continue
        c = sorted(righe, key=lambda r: r["created_at"])[-1]
        # Power, 26/11 17:47: «non due caroselli in un giorno» (per brand)
        cc = supa.get("pub_consegne", select="id,brand,tipo", id=f"eq.{c['id']}")[0]
        if cc["tipo"] == "CAROSELLI":
            altri = [r for r in supa.get("pub_consegne", select="id,contenuto_id", brand=f"eq.{cc['brand']}", lingua=f"eq.{lingua}",
                                         tipo="eq.CAROSELLI", uscita=f"eq.{quando.date().isoformat()}", stato="in.(confermato,programmato,pubblicato)")
                     if r["id"] != c["id"]]
            if altri:
                print(f"{cid}: il {quando.date()} c'è già il carosello {altri[0]['contenuto_id']}: mai due caroselli in un giorno, salto"); continue
        if any(v.get("stato") == "pubblicato" for v in (c.get("stato_post") or {}).values()):
            print(f"{cid}: già uscito, salto"); continue
        adesso = datetime.now(timezone.utc).isoformat()
        etichetta = quando.strftime("%d/%m %H:%M")
        supa.patch("pub_consegne", {"id": c["id"]}, {
            "ora": quando.astimezone(timezone.utc).isoformat(), "uscita": quando.date().isoformat(), "stato": "confermato",
            "aggiornato": adesso, "nota_sistema": f"Collocato su richiesta di Power: {etichetta} (ora italiana)."})
        vive = supa.get("pub_post", select="chiave", consegna_id=f"eq.{c['id']}", stato="eq.programmato")
        for p in vive:
            supa.patch("pub_post", {"chiave": p["chiave"]}, {"stato": "annullato", "motivo": f"ricollocata: {etichetta}", "aggiornato": adesso})
        if c.get("chat_id"):
            supa.s.post(f"{supa.url}/rest/v1/pub_messages", timeout=60, headers={"Prefer": "return=minimal"},
                        json={"chat_id": c["chat_id"], "autore": "sistema", "consegna_id": c["id"], "stato": "fatto",
                              "testo": f"Uscita di {cid} {lingua} collocata da Power: {etichetta}."}).raise_for_status()
        print(f"{cid} {lingua}: dal {c['uscita']} a {etichetta} ({len(vive)} uscite vecchie chiuse)")


if __name__ == "__main__":
    main()
