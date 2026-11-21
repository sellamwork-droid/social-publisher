"""Client minimo per l'API REST di Blotato (https://help.blotato.com/api)."""
from __future__ import annotations

import mimetypes
import time
from pathlib import Path

import requests

BASE = "https://backend.blotato.com/v2"


class BlotatoError(RuntimeError):
    pass


class Blotato:
    def __init__(self, api_key: str, dry_run: bool = False):
        self.dry_run = dry_run
        self.s = requests.Session()
        self.s.headers.update({"blotato-api-key": api_key, "Content-Type": "application/json"})

    def _req(self, method: str, path: str, **kw):
        for attempt in range(4):
            r = self.s.request(method, BASE + path, timeout=120, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise BlotatoError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
            return r.json() if r.content else {}
        raise BlotatoError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")

    def accounts(self) -> list[dict]:
        return self._req("GET", "/users/me/accounts").get("items", [])

    def upload(self, path: Path) -> str:
        """Carica un file locale e restituisce l'URL pubblico da usare in mediaUrls."""
        if self.dry_run:
            return f"https://dry-run.local/{path.name}"
        r = self._req("POST", "/media/uploads", json={"filename": path.name})
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            put = requests.put(r["presignedUrl"], data=fh, headers={"Content-Type": ctype}, timeout=900)
        if put.status_code >= 400:
            raise BlotatoError(f"upload {path.name} -> {put.status_code}: {put.text[:300]}")
        return r["publicUrl"]

    def create_post(self, body: dict) -> dict:
        if self.dry_run:
            return {"postSubmissionId": "dry-run"}
        return self._req("POST", "/posts", json=body)

    def post_status(self, submission_id: str) -> dict:
        return self._req("GET", f"/posts/{submission_id}")
