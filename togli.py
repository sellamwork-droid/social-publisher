"""Toglie una consegna dal portale (stato «annullato»), solo se non è ancora uscita su nessun account.

Power, 26/11 19:51: «togliamo quello (A0010 inglese ricompresso) e di' alla chat di rifarlo». Per ID + lingua: prende le
consegne confermate, programmate o da approvare di quell'ID; se ha post programmati su Blotato non la tocca (per quelle c'è
«Annulla uscita»). TOGLI="A0010:EN", MOTIVO="...".
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from portale import connect


def main() -> None:
    supa = connect()
    if not supa:
        raise SystemExit("Portale non collegato")
    cid, _, lin = os.environ["TOGLI"].strip().partition(":")
    motivo = os.environ.get("MOTIVO", "").strip() or "tolta da Power"
    for r in supa.get("pub_consegne", select="id,stato,stato_post,versione", contenuto_id=f"eq.{cid}", lingua=f"eq.{lin or 'IT'}"):
        if r["stato"] not in ("confermato", "da_approvare"):
            continue
        if any(v.get("stato") in ("programmato", "pubblicato") for v in (r.get("stato_post") or {}).values()):
            print(f"{cid} {lin} v{r.get('versione')}: ha post su Blotato, non la tocco (usa Annulla uscita)"); continue
        supa.patch("pub_consegne", {"id": r["id"]}, {"stato": "annullato", "nota_sistema": motivo[:400],
                                                      "aggiornato": datetime.now(timezone.utc).isoformat()})
        print(f"{cid} {lin} v{r.get('versione')}: tolta ({r['stato']} → annullato)")


if __name__ == "__main__":
    main()
