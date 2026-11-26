"""Reel inglesi accettati da Power, esportati come li chiede Instagram (Power, 26/11 20:21: «mi riesci a rimandare qui
tutti i reel accettati in inglese», «se lo scarico dammelo per ig direttamente, deve essere perfetto per ig»).

Per ogni reel EN confermato, programmato o pubblicato (l'ultima versione di ogni ID): scarica il video dal portale, lo
porta al formato di Instagram con esporta_ig.py se non lo è già, e con AGGIORNA=true rimette nel portale il file per
Instagram al posto di quello vecchio (così anche il bottone «Video» dà quello). I file finiscono in fuori/ con la
copertina e un DESCRIZIONI.txt, che il workflow allega a una release in bozza (non pubblica) da scaricare.
Con LINGUA=IT|EN|tutte sceglie la lingua; con DAL=AAAA-MM-GG solo le uscite da quel giorno. Con RIPROGRAMMA=true
(Power, 26/11 22:32: «seguiamo la ricerca», 30 fps) un contenuto già programmato e non ancora uscito torna «confermato»
con modificato_at nuovo: social-publisher cancella il post vecchio su Blotato e lo rifà con il file nuovo.
Con ALLEGA=false niente file in fuori/ (solo il portale)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from esporta_ig import controlla, esporta
from portale import connect

STATI = ("confermato", "programmato", "pubblicato")


def slug(t: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", t or "").strip("-")[:50]


def main() -> None:
    supa = connect()
    out = Path("fuori"); out.mkdir(exist_ok=True)
    tmp = Path("tmp_in"); tmp.mkdir(exist_ok=True)
    solo = {x.strip().upper() for x in os.environ.get("IDS", "").split(",") if x.strip()}
    aggiorna = os.environ.get("AGGIORNA") == "true"
    riprogramma = os.environ.get("RIPROGRAMMA") == "true"
    allega = os.environ.get("ALLEGA", "true") != "false"
    lingua = (os.environ.get("LINGUA") or "EN").upper()
    dal = os.environ.get("DAL", "").strip()
    filtri = {"stato": f"in.({','.join(STATI)})"}
    if lingua in ("IT", "EN"):
        filtri["lingua"] = f"eq.{lingua}"
    if dal:
        filtri["uscita"] = f"gte.{dal}"
    righe = supa.get("pub_consegne", select="*", **filtri)
    ultime: dict[str, dict] = {}
    for r in sorted(righe, key=lambda r: r.get("created_at") or ""):
        if not any(f.get("tipo") == "video" for f in r.get("files") or []):
            continue
        cid = (r.get("contenuto_id") or r["id"][:8]) + ("" if lingua in ("IT", "EN") else f"_{r['lingua']}")
        if solo and cid.upper() not in solo:
            continue
        ultime[cid] = r
    descr = []
    for cid, r in sorted(ultime.items(), key=lambda kv: (kv[1].get("uscita") or "", kv[0])):
        nome = f"{r.get('brand', '')}_{cid.split('_')[0]}_{r['lingua']}_{slug(r.get('titolo'))}"
        files = list(r.get("files") or [])
        for i, f in enumerate(files):
            low = f["nome"].lower()
            if f.get("tipo") == "video":
                src = tmp / f"{cid}_{f['nome']}"
                supa.download(f["path"], src)
                dest = out / f"{nome}.mp4"
                if controlla(src):
                    esporta(src, dest)
                    stato_file = "esportato ora per Instagram"
                    if aggiorna:
                        dati = dest.read_bytes()
                        rr = supa.s.post(f"{supa.url}/storage/v1/object/consegne/{f['path']}", data=dati, timeout=900,
                                         headers={"Content-Type": "video/mp4", "x-upsert": "true"})
                        rr.raise_for_status()
                        files[i] = {**f, "bytes": len(dati)}
                        corpo = {"files": files}
                        gia_uscito = any(v.get("stato") == "pubblicato" for v in (r.get("stato_post") or {}).values())
                        if riprogramma and r.get("ora") and not gia_uscito and r.get("stato") in ("programmato", "confermato", "errore"):
                            from datetime import datetime, timezone
                            corpo.update(modificato_at=datetime.now(timezone.utc).isoformat(), stato="confermato",
                                         nota_sistema="File rifatto a 30 fps per Instagram: Blotato si aggiorna entro 15 minuti.")
                            stato_file += ", riprogrammato su Blotato"
                        supa.patch("pub_consegne", {"id": r["id"]}, corpo)
                        stato_file += ", e rimesso nel portale"
                else:
                    src.rename(dest)
                    stato_file = "già come lo chiede Instagram"
                e = controlla(dest)
                if not allega:
                    dest.unlink(missing_ok=True)
                print(f"REEL {cid} EN {r.get('stato')} uscita {r.get('uscita')}: {dest.name} {dest.stat().st_size / 1e6:.1f} MB · "
                      f"{stato_file} · {'OK Instagram' if not e else 'NON VA: ' + ' · '.join(e)}")
            elif "_cover." in low and allega:
                supa.download(f["path"], out / f"{nome}_copertina{Path(f['nome']).suffix}")
            elif low.endswith(".txt") and not low.startswith("id") and allega:
                p = tmp / f"{cid}.txt"
                supa.download(f["path"], p)
                descr.append(f"===== {cid} · {r.get('titolo') or ''} =====\n{p.read_text(encoding='utf-8', errors='replace').strip()}\n")
    (out / "DESCRIZIONI.txt").write_text("\n".join(descr), encoding="utf-8")
    print(f"PRONTI {len(ultime)} reel ({lingua}) {'in fuori/' if allega else 'solo nel portale'}")


if __name__ == "__main__":
    main()
