"""Collegamento con il portale Studio Hub (Supabase).

- PortalStorage: le consegne CONFERMATE nel portale diventano pacchetti come quelli di Drive
  (stesse regole, stessi orari, stesso controllo). Lo stato dei post sta nella colonna stato_post.
- Portale: scrive nel portale uscite (pub_post), numeri, chat esterne e il battito del sistema.
Serve SUPABASE_URL e SUPABASE_SERVICE_KEY (Secrets di GitHub). Senza, il portale è semplicemente spento.
Niente qui blocca la pubblicazione: gli errori finiscono nel log.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from storage import FileRef


class Supa:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})

    def get(self, table: str, **params) -> list[dict]:
        r = self.s.get(f"{self.url}/rest/v1/{table}", params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def patch(self, table: str, match: dict, body: dict) -> None:
        r = self.s.patch(f"{self.url}/rest/v1/{table}", params={k: f"eq.{v}" for k, v in match.items()},
                         json=body, timeout=60)
        r.raise_for_status()

    def upsert(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        r = self.s.post(f"{self.url}/rest/v1/{table}", json=rows, timeout=60,
                        headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        r.raise_for_status()

    def download(self, path: str, dest: Path) -> Path:
        with self.s.get(f"{self.url}/storage/v1/object/consegne/{path}", stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(4 * 1024 * 1024):
                    fh.write(chunk)
        return dest


def connect() -> Supa | None:
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_KEY", "")
    return Supa(url, key) if url and key else None


class PortalStorage:
    """Pacchetti = consegne confermate del portale. Nome: EN/REEL/2026-11-23~ab12cd34 (ref = id della consegna)."""

    def __init__(self, supa: Supa):
        self.db = supa
        self._rows: dict[str, dict] = {}

    def _list(self, brand: str, stati: str) -> dict[str, str]:
        rows = self.db.get("pub_consegne", select="*", brand=f"eq.{brand}", stato=f"in.({stati})")
        out = {}
        for r in rows:
            self._rows[r["id"]] = r
            out[f"{r['lingua']}/{r['tipo']}/{r['uscita']}~{r['id'][:8]}"] = r["id"]
        return out

    def packages(self, brand: str) -> dict[str, str]:
        return self._list(brand, "confermato")

    def published_packages(self, brand: str) -> dict[str, str]:
        return self._list(brand, "programmato,pubblicato,errore")

    def orario(self, ref: str) -> datetime | None:
        """giorno e ora scelti da Power nel portale (colonna «ora», 26/11 17:15); None = ancora da collocare"""
        r = self._rows.get(ref) or (self.db.get("pub_consegne", select="ora", id=f"eq.{ref}") or [{}])[0]
        v = r.get("ora")
        return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None

    def list_files(self, ref: str) -> dict[str, FileRef]:
        r = self._rows.get(ref) or self.db.get("pub_consegne", select="*", id=f"eq.{ref}")[0]
        out = {f["nome"]: FileRef(f["nome"], f["path"], int(f.get("bytes") or 0)) for f in r.get("files", [])}
        out["CONFERMATO.txt"] = FileRef("CONFERMATO.txt", "", 0)  # confermato da Power nel portale
        return out

    def download(self, f: FileRef, dest: Path) -> Path:
        if not f.ref:
            dest.write_text("")
            return dest
        return self.db.download(f.ref, dest)

    def read_state(self, ref: str) -> dict:
        r = self.db.get("pub_consegne", select="stato_post", id=f"eq.{ref}")
        return (r[0].get("stato_post") or {}) if r else {}

    def write_state(self, ref: str, state: dict) -> None:
        body: dict = {"stato_post": state, "aggiornato": datetime.now(timezone.utc).isoformat()}
        stati = [v.get("stato") for v in state.values()]
        attivi = [s for s in stati if s != "saltato"]
        if any(s in ("errore", "fallito") for s in stati):
            body["stato"] = "errore"
            body["nota_sistema"] = "; ".join(f"{k}: {v.get('motivo', '')}" for k, v in state.items()
                                             if v.get("stato") in ("errore", "fallito"))[:500]
        elif attivi and all(s == "pubblicato" for s in attivi):
            body["stato"] = "pubblicato"
        self.db.patch("pub_consegne", {"id": ref}, body)

    def move_to_published(self, brand: str, name: str, ref: str) -> None:
        cur = self.db.get("pub_consegne", select="stato", id=f"eq.{ref}")
        if cur and cur[0]["stato"] == "confermato":
            self.db.patch("pub_consegne", {"id": ref}, {"stato": "programmato", "nota_sistema": ""})


def annulla_uscite(supa: Supa, api, cfg: dict, portale, log, solo: str = "") -> int:
    """Consegne da annullare (bottone "Annulla uscita" nel portale, oppure --annulla <ID>):
    cancella su Blotato i post già programmati e segna la consegna come annullata."""
    # uscite rimaste "programmate" di consegne già annullate: si allineano
    try:
        vive = supa.get("pub_post", select="chiave,consegna_id", stato="eq.programmato", consegna_id="not.is.null")
        if vive:
            ann = {r["id"] for r in supa.get("pub_consegne", select="id", stato="eq.annullato",
                                               id=f"in.({','.join(sorted({v['consegna_id'] for v in vive}))})")}
            for v in vive:
                if v["consegna_id"] in ann:
                    supa.patch("pub_post", {"chiave": v["chiave"]}, {"stato": "annullato", "motivo": "uscita annullata da Power"})
    except Exception as e:
        log(f"(allineamento uscite annullate non riuscito: {str(e)[:200]})")
    righe = supa.get("pub_consegne", select="*", stato="eq.da_annullare")
    if solo:
        # anche le consegne «errore» (un post fallito, gli altri ancora programmati su Blotato): Power, 26/11 03:13, «annullali»
        # (pubblicazioni ferme); C0003 inglese non si annullava. Le altre si dicono nel log, così si vede perché non si toccano.
        mie = [r for r in supa.get("pub_consegne", select="id,contenuto_id,stato,brand,lingua,tipo,uscita,stato_post")
               if solo in (r.get("contenuto_id"), r["id"], r["id"][:8])]
        # e quelle già «annullato» (26/11 13:40): C0003 inglese risultava annullato ma senza nessun «cancellati su Blotato» nel
        # log; si ricontrolla Blotato e, se il post è ancora lì, si cancella (se no il log dice «non trovati»)
        buoni = ("confermato", "programmato", "errore", "annullato")
        for r in mie:
            if r["stato"] not in buoni:
                log(f"[{r['brand']} {r.get('contenuto_id') or r['id'][:8]} {r['lingua']}] non la annullo: è «{r['stato']}»")
        righe += [r for r in mie if r["stato"] in buoni]
    if not righe:
        return 0
    programmati = None
    n = 0
    for r in righe:
        brand = r["brand"]
        accounts = cfg["brands"][brand]["accounts"]
        stato = r.get("stato_post") or {}
        cancellati, falliti = [], []
        for key, rec in stato.items():
            if rec.get("stato") != "programmato":
                continue
            acc = accounts.get(rec.get("account") or key.split(":")[0], {})
            quando = rec.get("quando", "")
            if programmati is None:
                programmati = api.schedules()
            trovati = [x for x in programmati
                       if str((x.get("account") or {}).get("id") or (x.get("draft") or {}).get("accountId")) == str(acc.get("blotato_id"))
                       and (x.get("scheduledAt") or "").replace("-", "").replace("T", "").replace(":", "")[:12] == quando]
            for x in trovati:
                api.delete_schedule(x["id"])
            (cancellati if trovati else falliti).append(key)
            rec["stato"] = "annullato" if trovati else rec["stato"]
            nome_pkg = f"{r['lingua']}/{r['tipo']}/{r['uscita']}~{r['id'][:8]}"
            if trovati:  # la riga dell'uscita esiste già: si aggiorna solo lo stato
                supa.patch("pub_post", {"chiave": f"{brand}|{nome_pkg}|{key}"},
                           {"stato": "annullato", "motivo": "uscita annullata da Power",
                            "aggiornato": datetime.now(timezone.utc).isoformat()})
        nota = "Uscita annullata" + (f": cancellati su Blotato {', '.join(cancellati)}" if cancellati else "")
        if falliti:
            nota += f". Non trovati su Blotato (forse già usciti): {', '.join(falliti)}"
        supa.patch("pub_consegne", {"id": r["id"]}, {"stato": "annullato", "stato_post": stato, "nota_sistema": nota[:500],
                                                      "aggiornato": datetime.now(timezone.utc).isoformat()})
        log(f"[{brand} {r.get('contenuto_id') or r['id'][:8]} {r['lingua']}] {nota}")
        n += 1
    return n


class MultiStorage:
    """Drive (chat su claude.ai) + portale insieme. I riferimenti portano il prefisso della fonte."""

    def __init__(self, **sources):
        self.src = {k: v for k, v in sources.items() if v is not None}

    def _merge(self, meth: str, brand: str) -> dict[str, str]:
        out = {}
        for tag, s in self.src.items():
            for name, ref in getattr(s, meth)(brand).items():
                out[name] = f"{tag}::{ref}"
        return out

    def packages(self, brand):
        return self._merge("packages", brand)

    def published_packages(self, brand):
        return self._merge("published_packages", brand)

    def _split(self, ref):
        tag, _, raw = ref.partition("::")
        return self.src[tag], raw

    def list_files(self, ref):
        tag, _, raw = ref.partition("::")
        files = self.src[tag].list_files(raw)
        return {k: FileRef(f.rel, f"{tag}::{f.ref}", f.size) for k, f in files.items()}

    def download(self, f, dest):
        tag, _, raw = f.ref.partition("::")
        return self.src[tag].download(FileRef(f.rel, raw, f.size), dest)

    def read_state(self, ref):
        s, raw = self._split(ref)
        return s.read_state(raw)

    def write_state(self, ref, state):
        s, raw = self._split(ref)
        return s.write_state(raw, state)

    def move_to_published(self, brand, name, ref):
        s, raw = self._split(ref)
        return s.move_to_published(brand, name, raw)

    def orario(self, ref):
        s, raw = self._split(ref)
        return s.orario(raw) if hasattr(s, "orario") else None


class Portale:
    """Quello che il portale mostra: uscite, numeri, chat esterne, battito."""

    def __init__(self, supa: Supa | None, log=print):
        self.db, self.log = supa, log
        self.post_rows: dict[str, dict] = {}
        self.extra: dict[str, list[dict]] = {"pub_esterne": []}

    def post(self, chiave: str, **campi) -> None:
        if self.db:
            self.post_rows.setdefault(chiave, {"chiave": chiave}).update({k: v for k, v in campi.items() if v is not None})

    def esterne(self, rows: list[dict]) -> None:
        self.extra["pub_esterne"] = rows

    def flush(self, ok: bool, dettaglio: dict) -> None:
        if not self.db:
            return
        try:
            now = datetime.now(timezone.utc).isoformat()
            rows = [{**r, "aggiornato": now} for r in self.post_rows.values()]
            # PostgREST vuole le stesse colonne in ogni riga di un upsert: si manda riga per gruppo di colonne
            groups: dict[tuple, list] = {}
            for r in rows:
                groups.setdefault(tuple(sorted(r)), []).append(r)
            for g in groups.values():
                self.db.upsert("pub_post", g)
            if self.extra["pub_esterne"]:
                self.db.upsert("pub_esterne", self.extra["pub_esterne"])
            self.db.upsert("pub_sistema", [{"chiave": "publisher", "stato": "ok" if ok else "problemi",
                                            "ultimo": now, "dettaglio": dettaglio}])
            self.log(f"Portale aggiornato ({len(rows)} uscite).")
        except Exception as e:
            self.log(f"(portale non aggiornato: {str(e)[:300]})")
