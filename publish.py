"""Sistema di pubblicazione AXUX + VOLWICK.

Legge i pacchetti in DA MANDARE/<BRAND>/<AAAA-MM-GG>/, prepara ogni post e lo programma su Blotato
all'orario dello slot dell'account. Registra lo stato nelle proprietà nascoste della cartella del pacchetto (così non
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
from media import cover_jpeg, prepend_cover_frame, video_instagram  # noqa: E402
from plan import adapt_caption, parse_ids, Job, build_jobs, parse_caption, TARGETS  # noqa: E402
from storage import DriveStorage, LocalStorage  # noqa: E402
from sheet import Dashboard  # noqa: E402

UTC = timezone.utc
ROME = ZoneInfo("Europe/Rome")


def it_time(dt: datetime) -> str:
    return dt.astimezone(ROME).strftime("%d/%m/%Y %H:%M")
DONE = {"programmato", "saltato", "pubblicato", "fallito"}


def log(msg: str) -> None:
    print(msg, flush=True)


class Publisher:
    def __init__(self, cfg: dict, storage, api: Blotato, sheet: Dashboard, now: datetime):
        self.cfg, self.storage, self.api, self.sheet, self.now = cfg, storage, api, sheet, now
        self.tmp = Path(tempfile.mkdtemp(prefix="pub_"))
        self._uploads: dict[tuple, str] = {}
        self.problemi = 0  # errori e post falliti: se > 0 la corsa finisce in rosso (GitHub manda una email)
        self.troppo_tardi = 0  # post non pubblicati perché il loro orario è passato da troppo (il portale li sposta)
        self._local: dict[str, Path] = {}
        from portale import Portale
        self.portale = Portale(None, log)  # sostituito in main() se il portale è collegato

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
    @staticmethod
    def motivo_fermo(acc: dict | None, pkg_date: date) -> str:
        """perché un account non pubblica un pacchetto di quel giorno ("" = pubblica)"""
        if acc and acc.get("paused"):
            return "account in pausa (config.yaml)"
        if not acc or not acc.get("blotato_id"):
            return "account non collegato su Blotato"
        if acc.get("dal") and pkg_date < date.fromisoformat(str(acc["dal"])):
            return f"account attivo dal {acc['dal']} (config.yaml)"
        return ""

    @staticmethod
    def riprendibile(prev: dict) -> bool:
        """saltato solo perché l'account era fermo: si rifà quando l'account parte (Power, 25/11: IG USA e TikTok dal 26/11)"""
        return prev.get("stato") == "saltato" and str(prev.get("motivo", "")).startswith(("account in pausa", "account attivo dal"))

    def ritardo_minuti(self, pkg_date: date, acc: dict, slot: str) -> int | None:
        """minuti passati dall'orario del posto (nel fuso dell'account); None se il posto non ha un orario"""
        hhmm = acc.get("slots", {}).get(slot)
        if not hhmm:
            return None
        h, m = map(int, hhmm.split(":"))
        quando = datetime(pkg_date.year, pkg_date.month, pkg_date.day, h, m, tzinfo=ZoneInfo(acc["timezone"])).astimezone(UTC)
        return int((self.now - quando).total_seconds() // 60)

    def quando(self, pkg_date: date, acc: dict, slot: str, ora: datetime | None) -> tuple[datetime, bool]:
        """l'ora scelta da Power nel portale se c'è (26/11 17:15, collocazione a mano), se no l'orario del posto"""
        if ora is None:
            return self.slot_time(pkg_date, acc, slot)
        when = ora.astimezone(UTC)
        if when < self.now + timedelta(minutes=5):
            return self.now + timedelta(minutes=self.cfg.get("late_publish_minutes", 10)), True
        return when, False

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
        text = adapt_caption(text, platform)
        target: dict = {"targetType": platform}
        media_urls: list[str] = []

        if job.kind == "story":
            media_urls.append(self._upload(("story", job.media[0].ref), self._local_file(job.media[0])))
        elif job.kind == "carousel":
            for img in job.media:
                media_urls.append(self._upload(("img", img.ref), self._local_file(img)))
        else:
            video = self._local_file(job.media[0])
            if platform == "tiktok" and job.cover:
                tt = self.tmp / (Path(job.media[0].rel).stem + "_tiktok.mp4")
                if not tt.exists():
                    prepend_cover_frame(video, self._local_file(job.cover), tt)
                media_urls.append(self._upload(("tiktok", job.media[0].ref), tt))
            elif platform == "instagram":
                ig = self.tmp / (Path(job.media[0].rel).stem + "_instagram.mp4")
                if not ig.exists():
                    try:
                        video_instagram(video, ig)
                    except Exception as e:  # se la versione per Instagram non riesce, esce l'originale
                        log(f"versione per Instagram non riuscita ({e}): uso l'originale")
                        ig = video
                media_urls.append(self._upload(("instagram", job.media[0].ref), ig))
            else:
                media_urls.append(self._upload(("video", job.media[0].ref), video))

        if platform == "instagram":
            if job.kind == "story":
                target["mediaType"] = "story"
            elif job.kind == "reel":
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

    def _programmati(self) -> list[dict]:
        """i post programmati su Blotato, letti una volta per giro (servono per spostare un'uscita)"""
        if getattr(self, "_cache_programmati", None) is None:
            self._cache_programmati = self.api.schedules()
        return self._cache_programmati

    # ---------- pacchetto
    def run_package(self, brand: str, bcfg: dict, pkg_name: str, pkg_ref: str, solo_nuovi: bool = False) -> None:
        """solo_nuovi: pacchetto già programmato o pubblicato, si fanno solo i post nuovi (un account partito dopo)"""
        lang, tipo, day = pkg_name.split("/")
        day = day.split("~")[0]  # pacchetti del portale: EN/REEL/2026-11-23~ab12cd34
        pkg_date = date.fromisoformat(day)
        files = self.storage.list_files(pkg_ref)
        if self.cfg.get("require_confirmation", True) and not any(
                Path(r).stem.lower() == "confermato" for r in files):
            log(f"[{brand} {pkg_name}] in attesa: manca il file CONFERMATO (non pubblico nulla)")
            return
        jobs = build_jobs(files, lang, tipo)
        if "ID.txt" in files:
            parse_ids(self._local_file(files["ID.txt"]).read_text(encoding="utf-8", errors="replace"), jobs)
        state = self.storage.read_state(pkg_ref)
        ora = self.storage.orario(pkg_ref) if hasattr(self.storage, "orario") else None
        # Power, 26/11 17:15: «rendimi tutto manuale per ora»: una consegna del portale esce solo quando Power le ha dato
        # giorno e ora in Uscite. Senza, aspetta (niente stato, niente Blotato).
        if (self.cfg.get("collocazione_manuale") and not solo_nuovi and ora is None and pkg_ref.startswith("portale::")):
            # messa «In attesa» da Power (26/11 17:55): i post già programmati su Blotato si tolgono, poi aspetta
            vivi = {k: v for k, v in state.items() if v.get("stato") == "programmato" and v.get("quando")}
            if vivi and not self.api.dry_run:
                for key, rec in vivi.items():
                    acc = bcfg["accounts"].get(rec.get("account") or key.split(":")[0], {})
                    trovati = [x for x in self._programmati()
                               if str((x.get("account") or {}).get("id") or (x.get("draft") or {}).get("accountId")) == str(acc.get("blotato_id"))
                               and (x.get("scheduledAt") or "").replace("-", "").replace("T", "").replace(":", "")[:12] == rec["quando"]]
                    for x in trovati:
                        self.api.delete_schedule(x["id"])
                    log(f"   {key:<20} in attesa: {'tolto da Blotato il post' if trovati else 'non trovato su Blotato il post'} delle {rec.get('orario', rec['quando'])}")
                    del state[key]
                self.storage.write_state(pkg_ref, state)
            log(f"[{brand} {pkg_name}] in attesa: aspetta che Power scelga giorno e ora in Uscite")
            return
        if not jobs:
            log(f"[{brand} {pkg_name}] nessun file riconosciuto (controlla i nomi)")
            return
        if solo_nuovi:
            jobs = [j for j in jobs if (not state.get(j.key) or self.riprendibile(state[j.key]))
                    and not self.motivo_fermo(bcfg["accounts"].get(j.account), pkg_date)]
            if not jobs:
                return
            log(f"[{brand} {pkg_name}] già programmato: {len(jobs)} post nuovi ({', '.join(j.key for j in jobs)})")
        else:
            log(f"[{brand} {pkg_name}] {len(jobs)} post nel pacchetto")

        for job in jobs:
            prev = state.get(job.key, {})
            acc = bcfg["accounts"].get(job.account)
            fermo = self.motivo_fermo(acc, pkg_date)
            # Power, 26/11 17:00: un'uscita spostata nel portale (pub_sposta_uscita) torna «confermato» con il giorno nuovo. Il post
            # già programmato su Blotato all'orario vecchio si cancella e si riprogramma qui all'orario nuovo.
            if prev.get("stato") == "programmato" and acc and not fermo and not job.problems and prev.get("quando"):
                try:
                    nuovo = self.quando(pkg_date, acc, job.slot, ora)[0].strftime("%Y%m%d%H%M")
                except Exception:
                    nuovo = prev["quando"]
                if nuovo != prev["quando"]:
                    if self.api.dry_run:
                        log(f"   {job.key:<20} prova: spostato dal {prev['quando']} al {nuovo}")
                        continue
                    vecchi = [x for x in self._programmati()
                              if str((x.get("account") or {}).get("id") or (x.get("draft") or {}).get("accountId")) == str(acc.get("blotato_id"))
                              and (x.get("scheduledAt") or "").replace("-", "").replace("T", "").replace(":", "")[:12] == prev["quando"]]
                    for x in vecchi:
                        self.api.delete_schedule(x["id"])
                    log(f"   {job.key:<20} spostato: {'cancellato su Blotato il post' if vecchi else 'non trovato su Blotato il post'} "
                        f"delle {prev.get('orario', prev['quando'])}, lo riprogrammo")
                    prev = {}
            if prev.get("stato") in DONE and not (self.riprendibile(prev) and not fermo):
                continue
            # Power, 25/11 03:07: «avevo accettato un contenuto di volwick e me lo sono ritrovato pubblicato ora». Era la
            # versione nuova di un reel del giorno prima (il 24, posto delle 22:00): confermato alle 02:43, il sistema lo
            # ha pubblicato subito come «in ritardo». Un posto passato da poco esce appena possibile (una conferma arrivata
            # pochi minuti dopo l'orario); passato da più di late_max_minutes non esce: niente stato, il pacchetto resta
            # confermato e il portale lo rimette nel primo posto libero, poi esce lì.
            if acc and not fermo and not job.problems:
                ritardo = (int((self.now - ora).total_seconds() // 60) if ora is not None
                           else self.ritardo_minuti(pkg_date, acc, job.slot))
                limite = int(self.cfg.get("late_max_minutes", 120))
                if ritardo is not None and ritardo > limite:
                    log(f"[{brand} {pkg_name}] {job.key}: il suo orario è passato da {ritardo // 60} h {ritardo % 60:02d} min "
                        f"(oltre {limite} min): non lo pubblico adesso, il portale lo rimette nel primo posto libero")
                    self.troppo_tardi += 1
                    continue
            rec = {"file": job.source, "account": job.account, "aggiornato": self.now.isoformat(), "cid": job.cid}
            try:
                if fermo:
                    rec.update(stato="saltato", motivo=fermo)
                elif job.problems:
                    rec.update(stato="errore", motivo="; ".join(job.problems))
                else:
                    when, late = self.quando(pkg_date, acc, job.slot, ora)
                    src = job.alt.get(acc["platform"]) or job.caption
                    caption = self._local_file(src).read_text(encoding="utf-8") if src else ""
                    if not caption.strip():
                        raise ValueError(f"la descrizione {src.rel if src else ''} è vuota: ogni video deve avere la sua descrizione")
                    body = self.build_post(job, acc, caption)
                    body["scheduledTime"] = when.strftime("%Y-%m-%dT%H:%M:%SZ")
                    try:
                        res = self.api.create_post(body)
                    except Exception as e:
                        if "thumbnail" in str(e).lower() and body["post"]["target"].pop("thumbnailUrl", None):
                            res = self.api.create_post(body)  # canale non verificato: senza miniatura
                            rec["nota"] = "miniatura non messa: canale YouTube non verificato"
                        else:
                            raise
                    local_when = when.astimezone(ZoneInfo(acc["timezone"])).strftime("%Y-%m-%d %H:%M")
                    rec.update(stato="programmato", orario=f"{local_when} ({acc['timezone']})",
                               quando=when.strftime("%Y%m%d%H%M"),
                               postSubmissionId=res.get("postSubmissionId"),
                               **({"nota": "slot già passato: pubblicato appena possibile"} if late else {}))
            except Exception as e:
                rec.update(stato="errore", motivo=str(e)[:400])
                traceback.print_exc()
            if rec["stato"] == "errore":
                self.problemi += 1
            if self.api.dry_run:  # in prova non si salva nulla, così la corsa vera riparte da zero
                rec["stato"] = "prova:" + rec["stato"]
            else:
                state[job.key] = rec
                try:
                    self.storage.write_state(pkg_ref, state)
                except Exception as e:
                    log(f"   ATTENZIONE: stato non salvato per {job.key} ({e}). Controllare doppioni su Blotato.")
            log(f"   {job.key:<20} {rec['stato']:<12} {rec.get('orario', '')} {rec.get('motivo', '')}")
            nome = (acc or {}).get("nome", job.account)
            uscita_it = (it_time(datetime.strptime(rec["quando"], "%Y%m%d%H%M").replace(tzinfo=UTC))
                         if rec.get("quando") else "")
            if not self.api.dry_run:
                self.portale.post(f"{brand}|{pkg_name}|{job.key}", brand=brand, uscita=day, account=nome,
                                  piattaforma=(acc or {}).get("platform", job.account), tipo=job.kind, lingua=lang,
                                  contenuto_id=job.cid, stato=rec["stato"], blotato_id=rec.get("postSubmissionId") or "",
                                  ora_uscita=(datetime.strptime(rec["quando"], "%Y%m%d%H%M").replace(tzinfo=UTC).isoformat()
                                              if rec.get("quando") else None),
                                  consegna_id=(pkg_ref.split("::", 1)[1] if pkg_ref.startswith("portale::") else None),
                                  motivo=rec.get("motivo", rec.get("nota", "")) or "")
                self.sheet.upsert("Stato", f"{brand}|{pkg_name}|{job.key}", Brand=brand, **{
                    "Giorno uscita": day, "Account": nome, "Tipo": f"{job.kind} {lang}", "File": f"{lang}/{tipo}/{job.source}",
                    "Uscita (ora account)": rec.get("orario", ""), "Uscita (ora Italia)": uscita_it,
                    "Stato": rec["stato"], "Aggiornato (ora Italia)": it_time(self.now),
                    "ID Blotato": rec.get("postSubmissionId", ""),
                    "Link / motivo": rec.get("motivo", rec.get("nota", "")), "ID contenuto": job.cid})
                self.sheet.event([it_time(self.now), brand, day, nome, f"{job.kind} {lang}", f"{lang}/{tipo}/{job.source}", uscita_it,
                                  rec["stato"], rec.get("postSubmissionId", ""), rec.get("motivo", rec.get("nota", ""))])

        if not solo_nuovi and all(state.get(j.key, {}).get("stato") in DONE for j in jobs) and not self.api.dry_run:
            try:
                self.storage.move_to_published(brand, pkg_name, pkg_ref)
                log(f"[{brand} {pkg_name}] completo: spostato in PUBBLICATI")
            except Exception as e:
                log(f"[{brand} {pkg_name}] completo (tutto programmato), ma non spostato in PUBBLICATI: {str(e)[:200]}")

    def check_accounts(self) -> None:
        """Avvisa se un account usato dal sistema non risulta più collegato o sano su Blotato."""
        items = self.api.accounts()
        by_id = {str(a.get("id")): a for a in items}
        bad_words = ("reauth", "reconnect", "expired", "disconnected", "error", "unhealthy", "invalid")
        for brand, bcfg in self.cfg["brands"].items():
            for name, acc in bcfg["accounts"].items():
                aid = acc.get("blotato_id")
                if not aid or acc.get("paused"):
                    continue
                a = by_id.get(str(aid))
                if not a:
                    motivo = f"account {aid} non trovato su Blotato (scollegato o rimosso)"
                else:
                    flags = {k: v for k, v in a.items() if isinstance(v, (str, bool)) and (
                        (isinstance(v, bool) and v and any(w in k.lower() for w in bad_words)) or
                        (isinstance(v, str) and k.lower() in ("status", "health", "state") and
                         v.lower() not in ("healthy", "active", "connected", "ok")))}
                    motivo = f"account {aid} da ricollegare su Blotato ({flags})" if flags else ""
                if motivo:
                    log(f"[{brand}] {name}: ATTENZIONE {motivo}")
                if not self.api.dry_run:
                    if motivo:
                        self.problemi += 1
                        self.sheet.event([it_time(self.now), brand, "", acc.get("nome", name), "account", "", "",
                                          "DA RICOLLEGARE", str(aid), motivo])
                    self.sheet.upsert("Account", f"{brand}|{name}", Brand=brand, Account=acc.get("nome", name),
                                      Piattaforma=acc["platform"], **{"ID Blotato": str(aid),
                                      "Stato": "DA RICOLLEGARE" if motivo else "collegato",
                                      "Ultimo controllo (ora Italia)": it_time(self.now), "Note": motivo})
            for name, acc in bcfg["accounts"].items():
                if not self.api.dry_run and (not acc.get("blotato_id") or acc.get("paused")):
                    self.sheet.upsert("Account", f"{brand}|{name}", Brand=brand, Account=acc.get("nome", name),
                                      Piattaforma=acc["platform"], **{"ID Blotato": str(acc.get("blotato_id") or ""),
                                      "Stato": "in pausa" if acc.get("paused") else "non collegato",
                                      "Ultimo controllo (ora Italia)": it_time(self.now), "Note": ""})
        log(f"Account Blotato controllati: {len(items)} collegati.")
        if self.api.dry_run:
            for a in items:
                log(f"   account Blotato {a.get('id')}: {a.get('platform')} @{a.get('username')} ({a.get('fullname')})")

    def verify(self) -> None:
        """Controlla su Blotato i post già passati di orario: pubblicato o fallito."""
        if self.api.dry_run:
            return
        tz = ZoneInfo(self.cfg.get("package_timezone", "Europe/Rome"))
        today = self.now.astimezone(tz).date()
        soglia = (self.now - timedelta(minutes=20)).strftime("%Y%m%d%H%M")
        for brand in self.cfg["brands"]:
            pk = {**self.storage.published_packages(brand), **self.storage.packages(brand)}
            for name, ref in pk.items():
                try:
                    d = date.fromisoformat(name.rsplit("/", 1)[-1].split("~")[0])
                except ValueError:
                    continue
                if not (today - timedelta(days=3) <= d <= today):
                    continue
                state = self.storage.read_state(ref)
                changed = False
                for key, rec in state.items():
                    if rec.get("stato") != "programmato" or not rec.get("postSubmissionId") or not rec.get("quando"):
                        continue
                    if rec["quando"] > soglia:
                        continue
                    try:
                        st = self.api.post_status(rec["postSubmissionId"])
                    except Exception as e:
                        log(f"[{brand} {name}] {key}: stato non leggibile ({str(e)[:120]})")
                        continue
                    stato = (st.get("status") or st.get("post", {}).get("status") or "").lower()
                    if stato == "published":
                        rec["stato"], changed = "pubblicato", True
                        log(f"[{brand} {name}] {key}: PUBBLICATO {st.get('publicUrl', '')}")
                        self.portale.post(f"{brand}|{name}|{key}", stato="pubblicato", link=st.get("publicUrl", "") or "")
                        self.sheet.upsert("Stato", f"{brand}|{name}|{key}", Stato="pubblicato", **{
                            "Aggiornato (ora Italia)": it_time(self.now), "Link / motivo": st.get("publicUrl", "")})
                        self.sheet.event([it_time(self.now), brand, name, key.split(":")[0], "", "", "",
                                          "pubblicato", rec["postSubmissionId"], st.get("publicUrl", "")])
                    elif stato == "failed":
                        rec["stato"], rec["motivo"], changed = "fallito", (st.get("errorMessage") or "")[:300], True
                        self.problemi += 1
                        log(f"[{brand} {name}] {key}: FALLITO su Blotato: {rec['motivo']}")
                        self.portale.post(f"{brand}|{name}|{key}", stato="fallito", motivo=rec["motivo"])
                        self.sheet.upsert("Stato", f"{brand}|{name}|{key}", Stato="FALLITO", **{
                            "Aggiornato (ora Italia)": it_time(self.now), "Link / motivo": rec["motivo"]})
                        self.sheet.event([it_time(self.now), brand, name, key.split(":")[0], "", "", "",
                                          "FALLITO", rec["postSubmissionId"], rec["motivo"]])
                if changed:
                    try:
                        self.storage.write_state(ref, state)
                    except Exception as e:
                        log(f"[{brand} {name}] stato verifiche non salvato: {e}")

    def run(self) -> None:
        tz = ZoneInfo(self.cfg.get("package_timezone", "Europe/Rome"))
        today = self.now.astimezone(tz).date()
        last = today + timedelta(days=self.cfg.get("lookahead_days", 2))
        for brand, bcfg in self.cfg["brands"].items():
            for name, ref in sorted(self.storage.packages(brand).items()):
                try:
                    d = date.fromisoformat(name.rsplit("/", 1)[-1].split("~")[0])
                except ValueError:
                    log(f"[{brand}] cartella '{name}' ignorata: il nome deve essere AAAA-MM-GG")
                    continue
                # fuori finestra, ma con post già su Blotato (spostato più avanti o messo in attesa da Power): si sistema subito
                if d > last and not any(v.get("stato") == "programmato" for v in self.storage.read_state(ref).values()):
                    log(f"[{brand} {name}] fuori finestra: lo prendo dal {d - timedelta(days=self.cfg.get('lookahead_days', 2))}")
                    continue
                try:
                    self.run_package(brand, bcfg, name, ref)
                except Exception:
                    log(f"[{brand} {name}] errore nel pacchetto:")
                    traceback.print_exc()
            # pacchetti già programmati o pubblicati di oggi e dei prossimi giorni: i post per un account partito dopo
            # (Power, 25/11: Instagram USA e TikTok italiano dal 26/11) si aggiungono senza rifare gli altri
            for name, ref in sorted(self.storage.published_packages(brand).items()):
                try:
                    d = date.fromisoformat(name.rsplit("/", 1)[-1].split("~")[0])
                except ValueError:
                    continue
                if not (today <= d <= last):
                    continue
                lang, tipo = name.split("/")[:2]
                da_fare = [a for a in TARGETS.get((lang.upper(), tipo.upper()), []) if not self.motivo_fermo(bcfg["accounts"].get(a), d)]
                if not da_fare:
                    continue
                try:
                    self.run_package(brand, bcfg, name, ref, solo_nuovi=True)
                except Exception:
                    log(f"[{brand} {name}] errore nel pacchetto già programmato:")
                    traceback.print_exc()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--local", nargs=2, metavar=("DA_MANDARE", "PUBBLICATI"))
    ap.add_argument("--accounts", action="store_true")
    ap.add_argument("--annulla", default="", help="ID contenuto (A0002) o consegna da togliere dai programmati")
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
    from portale import MultiStorage, PortalStorage, Portale, connect
    supa = connect()
    storage = MultiStorage(drive=storage, portale=PortalStorage(supa) if supa else None)
    log("Portale Studio Hub: " + ("collegato" if supa else "non collegato (mancano SUPABASE_URL e SUPABASE_SERVICE_KEY)"))
    now = datetime.fromisoformat(args.now).replace(tzinfo=UTC) if args.now else datetime.now(UTC)
    sheet_id = os.environ.get("SHEET_ID") or cfg.get("drive", {}).get("sheet_id")
    pub = Publisher(cfg, storage, api, Dashboard(None if args.dry_run else sa, sheet_id, log), now)
    if supa and not args.dry_run:
        pub.portale = Portale(supa, log)
    if supa and not args.dry_run:
        try:
            from portale import annulla_uscite
            annulla_uscite(supa, api, cfg, pub.portale, log, args.annulla.strip())
        except Exception:
            log("annullamento non riuscito:")
            traceback.print_exc()
    try:
        pub.check_accounts()
    except Exception:
        log("controllo account non riuscito:")
        traceback.print_exc()
    pub.run()
    try:
        pub.verify()
    except Exception:
        log("verifica dei post pubblicati non riuscita:")
        traceback.print_exc()
    from brain import Brain
    Brain(pub, log).run()  # calendario, numeri, chi lavora (non blocca mai la pubblicazione)
    pub.sheet.flush()
    pub.portale.flush(pub.problemi == 0, {"problemi": pub.problemi, "ora": now.isoformat()})
    if pub.problemi and not args.dry_run:
        log(f"{pub.problemi} problemi: controlla i messaggi qui sopra.")
        sys.exit(1)


if __name__ == "__main__":
    main()
