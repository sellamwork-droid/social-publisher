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
