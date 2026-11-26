"""Elenco delle consegne del portale, solo lettura (Power, 26/11 13:50: «prima dimmi quali sono», «prima fammeli vedere»).

- Stampa le consegne con uscita da ieri in poi: giorno, posto, brand, lingua, ID, stato, titolo.
- Con MOSTRA="C0003,C0005" scarica in da_guardare/ i file dell'ultima consegna italiana di ogni ID (video o immagini,
  copertina, descrizione), che il workflow carica come artifact da guardare.
Non scrive niente: né nel portale, né su Blotato.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

from portale import connect

ORDINE_POSTO = {"reel1": 0, "carosello": 1, "reel2": 2, "reel3": 3}


def main() -> None:
    supa = connect()
    if not supa:
        print("Portale non collegato: mancano SUPABASE_URL e SUPABASE_SERVICE_KEY.")
        return
    dal = (date.today() - timedelta(days=1)).isoformat()
    righe = supa.get("pub_consegne", select="*", uscita=f"gte.{dal}")
    righe = [r for r in righe if r.get("stato") != "superato"]
    righe.sort(key=lambda r: (r.get("uscita") or "", r.get("brand") or "", ORDINE_POSTO.get(r.get("slot") or "", 9),
                              r.get("lingua") or "", r.get("created_at") or ""))
    print(f"CONSEGNE con uscita dal {dal} (tranne le superate): {len(righe)}")
    for r in righe:
        print(" | ".join([
            r.get("uscita") or "?", (r.get("slot") or "?").ljust(9), (r.get("brand") or "?").ljust(7), r.get("lingua") or "?",
            (r.get("contenuto_id") or r["id"][:8]).ljust(6), (r.get("stato") or "?").ljust(12),
            "data fissa" if r.get("data_fissa") else "", (r.get("titolo") or "")[:70],
            f"confermata {str(r.get('confermato_at') or r.get('aggiornato') or '')[:16]}",
        ]))

    if os.environ.get("CHAT") == "true":
        # il portale ha la funzione «sposta uscita»? (si chiama con un id inesistente: risponde «non autorizzato» o «non trovata»
        # se c'è, «Could not find the function» se il database non è ancora aggiornato; non cambia niente)
        r = supa.s.post(f"{supa.url}/rest/v1/rpc/pub_colloca", timeout=60,
                        json={"consegna": "00000000-0000-0000-0000-000000000000", "quando": "2030-01-01T10:00:00Z"})
        print(f"\nFUNZIONE pub_colloca: {r.status_code} {r.text[:160]}")
        oggi = date.today().isoformat()
        print(f"\nUSCITE DA OGGI ({oggi})")
        for p in sorted(supa.get("pub_post", select="uscita,ora_uscita,account,contenuto_id,lingua,stato,motivo", uscita=f"gte.{oggi}"),
                        key=lambda x: x.get("ora_uscita") or ""):
            print(f"  {p['uscita']} {str(p.get('ora_uscita') or '')[11:16]}Z {p['account']:<26} {p['contenuto_id']:<6} {p['lingua']} {p['stato']:<11} {p.get('motivo','')[:80]}")
        for c in supa.get("pub_consegne", select="contenuto_id,lingua,stato,uscita,ora", stato="eq.confermato"):
            print(f"  CONFERMATO {c['contenuto_id']} {c['lingua']} uscita {c['uscita']} ora {c.get('ora')}")
        stampa_chat(supa)

    mostra = [x.strip() for x in os.environ.get("MOSTRA", "").split(",") if x.strip()]
    if not mostra:
        return
    out = Path("da_guardare")
    out.mkdir(exist_ok=True)
    for cid in mostra:
        tutte = [r for r in supa.get("pub_consegne", select="*", contenuto_id=f"eq.{cid}") if r.get("lingua") == "IT"]
        tutte.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        if not tutte:
            print(f"{cid}: nessuna consegna italiana")
            continue
        r = tutte[0]
        d = out / f"{cid}_IT_{r.get('uscita')}_{r.get('slot')}_{r.get('stato')}"
        d.mkdir(exist_ok=True)
        for f in r.get("files") or []:
            try:
                supa.download(f["path"], d / f["nome"])
            except Exception as e:  # un file che non c'è più non ferma gli altri
                print(f"{cid}: {f.get('nome')} non scaricato ({str(e)[:120]})")
        print(f"{cid}: {len(list(d.iterdir()))} file in {d.name} (titolo: {r.get('titolo')})")


def stampa_chat(supa) -> None:
    """Power, 26/11 15:21: «perché non va nulla?». Stato di ogni chat e gli ultimi messaggi di sistema e di Claude."""
    print("\nCHAT")
    chats = supa.get("pub_chats", select="*")
    chats.sort(key=lambda c: (c.get("brand") or "", c.get("id") or ""))
    msgs = supa.get("pub_messages", select="chat_id,autore,stato,created_at,testo", order="created_at.desc", limit="400")
    for c in chats:
        print(f"- {c.get('id')} | {c.get('stato')} | {(c.get('attivita') or '')[:160]} | lavoro su: {(c.get('lavoro_su') or '')[:80]}")
        suoi = [m for m in msgs if m.get("chat_id") == c.get("id")][:6]
        for m in suoi:
            testo = " ".join(str(m.get("testo") or "").split())
            print(f"      {str(m.get('created_at'))[:16]} {m.get('autore')}/{m.get('stato')}: {testo[:260]}")
    print("\nSISTEMA")
    for r in supa.get("pub_sistema", select="*"):
        print(" ", str(r)[:400])


if __name__ == "__main__":
    main()
