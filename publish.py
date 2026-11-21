"""Sistema di pubblicazione AXUX + VOLWICK.

Legge i pacchetti in DA MANDARE/<BRAND>/<AAAA-MM-GG>/, prepara ogni post e lo programma su Blotato
all'orario dello slot dell'account. Registra lo stato in _stato.json dentro il pacchetto (così non
programma mai due volte lo stesso post) e, quando il pacchetto è finito, lo sposta in PUBBLICATI.

Uso:
  python publish.py                         # produzione (Drive + Blotato, variabili d'ambiente)
  python publish.py --dry-run               # mostra cosa farebbe, senza caricare né programmare nulla
  python publish.py --local IN OUT --dry-run  # test su cartelle locali
  python publish.py --accounts              # elenca gli account collegati su Blotato con i loro ID

Variabili d'ambiente (Secrets di GitHub):
  BLOTATO_API_KEY, GOOGLE_SERVICE_ACCOUNT_JSON, DRIVE_INBOX_FOLDER_ID, DRIVE_PUBLISHED_FOLDER_ID,
  SHEET_ID (facoltativo: foglio del cruscotto, scheda "Log")
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from blotato import Blotato  # noqa: E402
from media import cover_jpeg, prepend_cover_frame  # noqa: E402
from plan import Job, build_jobs, parse_caption  # noqa: E402
from storage import DriveStorage, LocalStorage  # noqa: E402

UTC = timezone.utc
DONE = {"programmato", "saltato"}


def log(msg: str) -> None:
    print(msg, flush=True)


class SheetLog:
    def __init__(self, sa_info: dict | None, sheet_id: str | None):
        self.svc = None
        self.sheet_id = sheet_id
        if sa_info and sheet_id:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            creds = service_account.Credentials.from_service_account_info(
                sa_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
            self.svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

    def add(self, row: list) -> None:
        if not self.svc:
            return
        try:
            self.svc.spreadsheets().values().append(
                spreadsheetId=self.sheet_id, range="Log!A:J", valueInputOption="USER_ENTERED",
                body={"values": [row]}).execute()
        except Exception as e:  # il log non deve mai bloccare la pubblicazione
            log(f"   (log foglio non riuscito: {e})")


class Publisher:
    def __init__(self, cfg: dict, storage, api: Blotato, sheet: SheetLog, now: datetime):
        self.cfg, self.storage, self.api, self.sheet, self.now = cfg, storage, api, sheet, now
        self.tmp = Path(tempfile.mkdtemp(prefix="pub_"))
        self._uploads: dict[tuple, str] = {}
        self._local: dict[str, Path] = {}

    # ---------- file
    def _local_file(self, f) -> Path:
        if f.ref not in self._local:
            dest = self.tmp / f"{len(self._local):04d}_{Path(f.rel).name}"
            self._local[f.ref] = self.storage.download(f, dest)
        return self._local[f.ref]

    def _upload(self, key: tuple, path: Path) -> str:
        if key not in self._uploads:
            self._uploads[key] = self.api.upload(path)
        return self._uploads[key]

    def _cover_url(self, job: Job) -> str | None:
        if not job.cover:
            return None
        src = self._local_file(job.cover)
        jpg = cover_jpeg(src, self.tmp / (Path(job.cover.rel).stem + "_1080.jpg"))
        return self._upload(("cover", job.cover.ref), jpg)

    # ---------- orari
    def slot_time(self, pkg_date: date, acc: dict, slot: str) -> tuple[datetime, bool]:
        hhmm = acc["slots"].get(slot)
        if not hhmm:
            raise ValueError(f"nessun orario configurato per lo slot '{slot}'")
        h, m = map(int, hhmm.split(":"))
        local = datetime(pkg_date.year, pkg_date.month, pkg_date.day, h, m, tzinfo=ZoneInfo(acc["timezone"]))
        when = local.astimezone(UTC)
        if when < self.now + timedelta(minutes=5):
            return self.now + timedelta(minutes=self.cfg.get("late_publish_minutes", 10)), True
        return when, False

    # ---------- corpo della richiesta Blotato
    def build_post(self, job: Job, acc: dict, caption_text: str) -> dict:
        platform = acc["platform"]
        d = self.cfg["defaults"]
        title, text = parse_caption(caption_text)
        target: dict = {"targetType": platform}
        media_urls: list[str] = []

        if job.kind == "carousel":
            for img in job.media:
                media_urls.append(self._upload(("img", img.ref), self._local_file(img)))
        else:
            video = self._local_file(job.media[0])
            if platform == "tiktok" and job.cover:
                tt = self.tmp / (Path(job.media[0].rel).stem + "_tiktok.mp4")
                if not tt.exists():
                    prepend_cover_frame(video, self._local_file(job.cover), tt)
                media_urls.append(self._upload(("tiktok", job.media[0].ref), tt))
            else:
                media_urls.append(self._upload(("video", job.media[0].ref), video))

        if platform == "instagram":
            if job.kind == "reel":
                target["mediaType"] = "reel"
                target["shareToFeed"] = d["instagram"].get("shareToFeed", True)
                cover = self._cover_url(job)
                if cover:
                    target["coverImageUrl"] = cover
        elif platform == "tiktok":
            target.update({k: v for k, v in d["tiktok"].items()
                           if k != "autoAddMusic" or job.kind == "carousel"})
            if job.kind == "carousel":
                target["imageCoverIndex"] = 0
                if title:
                    target["title"] = title[:90]
            else:
                target["videoCoverTimestamp"] = 0
        elif platform == "youtube":
            if not title:
                raise ValueError("manca il titolo YouTube (riga 'TITLE: ...' o riga hook nel .txt)")
            target.update({"title": title, **d["youtube"]})
            if self.cfg.get("youtube_thumbnails", True):
                cover = self._cover_url(job)
                if cover:
                    target["thumbnailUrl"] = cover

        return {"post": {"accountId": str(acc["blotato_id"]),
                         "content": {"platform": platform, "text": text, "mediaUrls": media_urls},
                         "target": target}}

    # ---------- pacchetto
    def run_package(self, brand: str, bcfg: dict, pkg_name: str, pkg_ref: str) -> None:
        pkg_date = date.fromisoformat(pkg_name)
        files = self.storage.list_files(pkg_ref)
        if self.cfg.get("require_confirmation", True) and not any(
                Path(r).stem.lower() == "confermato" for r in files):
            log(f"[{brand} {pkg_name}] in attesa: manca il file CONFERMATO (non pubblico nulla)")
            return
        jobs = build_jobs(files)
        state = self.storage.read_state(pkg_ref)
        if not jobs:
            log(f"[{brand} {pkg_name}] nessun file riconosciuto (controlla i nomi)")
            return
        log(f"[{brand} {pkg_name}] {len(jobs)} post nel pacchetto")

        for job in jobs:
            prev = state.get(job.key, {})
            if prev.get("stato") in DONE:
                continue
            acc = bcfg["accounts"].get(job.account)
            rec = {"file": job.source, "account": job.account, "aggiornato": self.now.isoformat()}
            try:
                if acc and acc.get("paused"):
                    rec.update(stato="saltato", motivo="account in pausa (config.yaml)")
                elif not acc or not acc.get("blotato_id"):
                    rec.update(stato="saltato", motivo="account non collegato su Blotato")
                elif job.problems:
                    rec.update(stato="errore", motivo="; ".join(job.problems))
                else:
                    when, late = self.slot_time(pkg_date, acc, job.slot)
                    caption = self._local_file(job.caption).read_text(encoding="utf-8")
                    body = self.build_post(job, acc, caption)
                    body["scheduledTime"] = when.strftime("%Y-%m-%dT%H:%M:%SZ")
                    res = self.api.create_post(body)
                    local_when = when.astimezone(ZoneInfo(acc["timezone"])).strftime("%Y-%m-%d %H:%M")
                    rec.update(stato="programmato", orario=f"{local_when} ({acc['timezone']})",
                               postSubmissionId=res.get("postSubmissionId"),
                               **({"nota": "slot già passato: pubblicato appena possibile"} if late else {}))
            except Exception as e:
                rec.update(stato="errore", motivo=str(e)[:400])
                traceback.print_exc()
            if self.api.dry_run:  # in prova non si salva nulla, così la corsa vera riparte da zero
                rec["stato"] = "prova:" + rec["stato"]
            else:
                state[job.key] = rec
                self.storage.write_state(pkg_ref, state)
            log(f"   {job.key:<20} {rec['stato']:<12} {rec.get('orario', '')} {rec.get('motivo', '')}")
            self.sheet.add([self.now.strftime("%Y-%m-%d %H:%M"), brand, pkg_name, job.account, job.kind,
                            job.source, rec.get("orario", ""), rec["stato"], rec.get("postSubmissionId", ""),
                            rec.get("motivo", rec.get("nota", ""))])

        if all(state.get(j.key, {}).get("stato") in DONE for j in jobs) and not self.api.dry_run:
            self.storage.move_to_published(brand, pkg_name, pkg_ref)
            log(f"[{brand} {pkg_name}] completo: spostato in PUBBLICATI")

    def run(self) -> None:
        tz = ZoneInfo(self.cfg.get("package_timezone", "Europe/Rome"))
        today = self.now.astimezone(tz).date()
        last = today + timedelta(days=self.cfg.get("lookahead_days", 2))
        for brand, bcfg in self.cfg["brands"].items():
            for name, ref in sorted(self.storage.packages(brand).items()):
                try:
                    d = date.fromisoformat(name)
                except ValueError:
                    log(f"[{brand}] cartella '{name}' ignorata: il nome deve essere AAAA-MM-GG")
                    continue
                if d > last:
                    log(f"[{brand} {name}] fuori finestra (esce il {name}): lo prendo dal {d - timedelta(days=self.cfg.get('lookahead_days', 2))}")
                    continue
                try:
                    self.run_package(brand, bcfg, name, ref)
                except Exception:
                    log(f"[{brand} {name}] errore nel pacchetto:")
                    traceback.print_exc()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--local", nargs=2, metavar=("DA_MANDARE", "PUBBLICATI"))
    ap.add_argument("--accounts", action="store_true")
    ap.add_argument("--now", help="per i test: data/ora ISO in UTC")
    ap.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    api = Blotato(os.environ.get("BLOTATO_API_KEY", ""), dry_run=args.dry_run)

    if args.accounts:
        for a in api.accounts():
            print(json.dumps(a, ensure_ascii=False))
        return

    drv = cfg.get("drive", {})
    for var, key in (("DRIVE_INBOX_FOLDER_ID", "inbox_folder_id"), ("DRIVE_PUBLISHED_FOLDER_ID", "published_folder_id")):
        if not os.environ.get(var):  # un secret vuoto arriva come stringa vuota: si usa config.yaml
            os.environ[var] = drv.get(key) or ""
    needed = ["BLOTATO_API_KEY", "GOOGLE_SERVICE_ACCOUNT_JSON", "DRIVE_INBOX_FOLDER_ID", "DRIVE_PUBLISHED_FOLDER_ID"]
    missing = [n for n in needed if not os.environ.get(n)]
    if not args.local and missing:
        log("Sistema non ancora configurato, mancano i Secrets: " + ", ".join(missing) + ". Nessuna azione.")
        return
    sa = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]) if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") else None
    if args.local:
        storage = LocalStorage(*args.local)
    else:
        storage = DriveStorage(sa, os.environ["DRIVE_INBOX_FOLDER_ID"], os.environ["DRIVE_PUBLISHED_FOLDER_ID"])
    now = datetime.fromisoformat(args.now).replace(tzinfo=UTC) if args.now else datetime.now(UTC)
    Publisher(cfg, storage, api, SheetLog(sa, os.environ.get("SHEET_ID")), now).run()


if __name__ == "__main__":
    main()
