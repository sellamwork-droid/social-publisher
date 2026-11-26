"""Imposta quante chat lavorano insieme nel Piano del portale (pub_sistema «piano», campo «parallele»).

Power, 26/11 16:08: «cambia te il piano a 4». Tocca solo quel campo; il resto del Piano resta com'è.
Il motore lo legge da solo al giro successivo (resta il tetto del computer, config.json «max_macchina»).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from portale import connect


def main() -> None:
    n = int(os.environ["PARALLELE"])
    if not 1 <= n <= 8:
        raise SystemExit(f"valore non valido: {n} (da 1 a 8)")
    supa = connect()
    if not supa:
        raise SystemExit("Portale non collegato: mancano SUPABASE_URL e SUPABASE_SERVICE_KEY.")
    riga = supa.get("pub_sistema", select="dettaglio", chiave="eq.piano")
    dettaglio = (riga[0].get("dettaglio") if riga else None) or {}
    prima = dettaglio.get("parallele")
    dettaglio["parallele"] = n
    supa.patch("pub_sistema", {"chiave": "piano"}, {"dettaglio": dettaglio, "ultimo": datetime.now(timezone.utc).isoformat()})
    dopo = supa.get("pub_sistema", select="dettaglio", chiave="eq.piano")[0]["dettaglio"]
    print(f"Piano: chat insieme {prima} → {dopo.get('parallele')} (resto invariato: {dict((k, v) for k, v in dopo.items() if k != 'parallele')})")


if __name__ == "__main__":
    main()
