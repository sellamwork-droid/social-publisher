"""Accesso ai file dei pacchetti: Google Drive (produzione) o cartella locale (test).

Struttura attesa:
    <root DA MANDARE>/<BRAND>/<AAAA-MM-GG>/...file...
    <root PUBBLICATI>/<BRAND>/<AAAA-MM-GG>/  (dove vengono spostati i pacchetti finiti)
"""
from __future__ import annotations

import io
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

STATE_FILE = "_stato.json"


@dataclass
class FileRef:
    rel: str          # percorso relativo nel pacchetto, es. "carosello_IT/01.png"
    ref: str          # id Drive o percorso locale assoluto
    size: int = 0


class LocalStorage:
    def __init__(self, inbox: str, published: str):
        self.inbox = Path(inbox)
        self.published = Path(published)

    def packages(self, brand: str) -> dict[str, str]:
        d = self.inbox / brand
        if not d.is_dir():
            return {}
        return {p.name: str(p) for p in d.iterdir() if p.is_dir()}

    def published_packages(self, brand: str) -> dict[str, str]:
        d = self.published / brand
        return {p.name: str(p) for p in d.iterdir() if p.is_dir()} if d.is_dir() else {}

    def list_files(self, pkg_ref: str) -> dict[str, FileRef]:
        root = Path(pkg_ref)
        out = {}
        for p in root.rglob("*"):
            if p.is_file():
                rel = p.relative_to(root).as_posix()
                out[rel] = FileRef(rel, str(p), p.stat().st_size)
        return out

    def download(self, f: FileRef, dest: Path) -> Path:
        shutil.copyfile(f.ref, dest)
        return dest

    def read_state(self, pkg_ref: str) -> dict:
        p = Path(pkg_ref) / STATE_FILE
        return json.loads(p.read_text()) if p.exists() else {}

    def write_state(self, pkg_ref: str, state: dict) -> None:
        (Path(pkg_ref) / STATE_FILE).write_text(json.dumps(state, indent=2, ensure_ascii=False))

    def move_to_published(self, brand: str, date: str, pkg_ref: str) -> None:
        dest = self.published / brand
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(pkg_ref, dest / date)


class DriveStorage:
    """Google Drive tramite service account. La cartella DA MANDARE e PUBBLICATI
    devono essere condivise (Editor) con l'email del service account."""

    FOLDER = "application/vnd.google-apps.folder"

    def __init__(self, service_account_info: dict, inbox_id: str, published_id: str):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=["https://www.googleapis.com/auth/drive"]
        )
        self.svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.inbox_id = inbox_id
        self.published_id = published_id

    # --- helpers
    def _children(self, folder_id: str) -> list[dict]:
        items, token = [], None
        while True:
            r = self.svc.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageSize=1000, pageToken=token,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            items += r.get("files", [])
            token = r.get("nextPageToken")
            if not token:
                return items

    def _child_folder(self, parent: str, name: str, create: bool = False) -> str | None:
        for f in self._children(parent):
            if f["name"] == name and f["mimeType"] == self.FOLDER:
                return f["id"]
        if not create:
            return None
        f = self.svc.files().create(
            body={"name": name, "mimeType": self.FOLDER, "parents": [parent]},
            fields="id", supportsAllDrives=True,
        ).execute()
        return f["id"]

    # --- API usata dallo script
    def packages(self, brand: str) -> dict[str, str]:
        bid = self._child_folder(self.inbox_id, brand)
        if not bid:
            return {}
        pk = {f["name"]: f["id"] for f in self._children(bid) if f["mimeType"] == self.FOLDER}
        self._parent = getattr(self, "_parent", {})
        self._parent.update({ref: bid for ref in pk.values()})
        return pk

    def published_packages(self, brand: str) -> dict[str, str]:
        bid = self._child_folder(self.published_id, brand)
        if not bid:
            return {}
        return {f["name"]: f["id"] for f in self._children(bid) if f["mimeType"] == self.FOLDER}

    def list_files(self, pkg_ref: str) -> dict[str, FileRef]:
        out: dict[str, FileRef] = {}

        def walk(fid: str, prefix: str):
            for f in self._children(fid):
                rel = f"{prefix}{f['name']}"
                if f["mimeType"] == self.FOLDER:
                    walk(f["id"], rel + "/")
                elif not f["mimeType"].startswith("application/vnd.google-apps"):
                    out[rel] = FileRef(rel, f["id"], int(f.get("size", 0)))

        walk(pkg_ref, "")
        return out

    def download(self, f: FileRef, dest: Path) -> Path:
        from googleapiclient.http import MediaIoBaseDownload

        req = self.svc.files().get_media(fileId=f.ref, supportsAllDrives=True)
        with open(dest, "wb") as fh:
            dl = MediaIoBaseDownload(fh, req, chunksize=32 * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk()
        return dest

    # Lo stato si salva nelle appProperties della cartella del pacchetto: un service account
    # non ha spazio su Drive e non può creare file nel Drive di Power, ma può modificare i metadati.
    # Ogni proprietà è "chiave post" -> "stato|id|nota" (max 124 byte chiave+valore).
    def read_state(self, pkg_ref: str) -> dict:
        meta = self.svc.files().get(fileId=pkg_ref, fields="appProperties", supportsAllDrives=True).execute()
        out = {}
        for k, v in (meta.get("appProperties") or {}).items():
            parts = v.split("|", 3) + ["", "", ""]
            out[k.replace(".", ":", 1)] = {"stato": parts[0], "postSubmissionId": parts[1],
                                           "quando": parts[2], "motivo": parts[3]}
        return out

    def write_state(self, pkg_ref: str, state: dict) -> None:
        props = {}
        for k, rec in state.items():
            k = k.replace(":", ".")  # Drive non accetta ':' nelle chiavi
            val = (f"{rec.get('stato', '')}|{rec.get('postSubmissionId') or ''}|{rec.get('quando') or ''}|"
                   f"{rec.get('motivo') or rec.get('nota') or ''}")
            budget = 120 - len(k.encode()) - 2
            props[k] = val.encode()[:budget].decode("utf-8", "ignore")
        self.svc.files().update(fileId=pkg_ref, body={"appProperties": props}, supportsAllDrives=True).execute()

    def move_to_published(self, brand: str, date: str, pkg_ref: str) -> None:
        dest = self._child_folder(self.published_id, brand)
        src = getattr(self, "_parent", {}).get(pkg_ref)
        if not dest or not src:
            raise RuntimeError(f"cartella PUBBLICATI/{brand} o cartella di origine non trovata")
        self.svc.files().update(
            fileId=pkg_ref, addParents=dest, removeParents=src,
            fields="id", supportsAllDrives=True,
        ).execute()
