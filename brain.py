"""Centro di controllo e collegamento con i cervelli di AXUX e VOLWICK.

A ogni corsa:
- Calendario : prossimi 7 giorni, per brand e per EN/IT reel/carosello: cosa manca, cosa aspetta il
               "confermato" di Power, cosa è programmato, pubblicato o in errore.
- Numeri     : risultati di ogni post (GET /v2/analytics di Blotato) legati all'ID del contenuto (ID.txt);
               scritti nel cruscotto e, con il secret BRAIN_TOKEN, in MEMORIA/numeri.json di ogni brand,
               così le chat sanno cosa funziona.
- Chi lavora : le chat attive di AXUX e VOLWICK (MEMORIA/sessioni dei due repository, serve BRAIN_TOKEN).
Niente qui può bloccare la pubblicazione: ogni errore va solo nel log.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

ROME = ZoneInfo("Europe/Rome")
REPOS = {"AXUX": "sellamwork-droid/Axux", "VOLWICK": "sellamwork-droid/volwick-reel-studio"}
GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
METRICHE = {  # nome nel cruscotto -> possibili nomi nella risposta di Blotato
    "views": ("views_count", "views", "viewCount", "video_views", "plays"),
    "likes": ("likes_count", "likes", "likeCount"),
    "comments": ("comments_count", "comments", "commentCount"),
    "reach": ("reach_count", "reach"),
    "shares": ("shares_count", "shares", "shareCount"),
    "saves": ("saves_count", "saves", "saved", "bookmarks"),
}


def _it(dt: datetime) -> str:
    return dt.astimezone(ROME).strftime("%Y-%m-%d %H:%M")


def _num(item: dict, names) -> float | None:
    stack = [item]
    while stack:
        d = stack.pop()
        for n in names:
            v = d.get(n)
            if isinstance(v, (int, float)):
                return v
            if isinstance(v, str) and v.replace(".", "", 1).isdigit():
                return float(v)
        stack += [v for v in d.values() if isinstance(v, dict)]
    return None


def _strings(item) -> set[str]:
    out, stack = set(), [item]
    while stack:
        d = stack.pop()
        if isinstance(d, dict):
            stack += list(d.values())
        elif isinstance(d, list):
            stack += d
        elif isinstance(d, (str, int)):
            out.add(str(d).rstrip("/"))
    return out


class GitHub:
    def __init__(self, token: str):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})

    def get(self, repo: str, path: str):
        r = self.s.get(f"https://api.github.com/repos/{repo}/contents/{path}", timeout=60)
        return r.json() if r.status_code == 200 else None

    def read(self, repo: str, path: str) -> tuple[str | None, str | None]:
        j = self.get(repo, path)
        if not j or "content" not in j:
            return None, None
        return base64.b64decode(j["content"]).decode("utf-8", "replace"), j["sha"]

    def write(self, repo: str, path: str, text: str, msg: str) -> bool:
        old, sha = self.read(repo, path)
        if old == text:
            return True
        body = {"message": msg, "content": base64.b64encode(text.encode()).decode(),
                "committer": {"name": "Social Publisher", "email": "noreply@anthropic.com"}}
        if sha:
            body["sha"] = sha
        r = self.s.put(f"https://api.github.com/repos/{repo}/contents/{path}", json=body, timeout=60)
        return r.status_code in (200, 201)


class Brain:
    def __init__(self, pub, log):
        self.pub, self.log = pub, log
        tok = os.environ.get("BRAIN_TOKEN", "")
        self.gh = GitHub(tok) if tok else None
        self.tz = ZoneInfo(pub.cfg.get("package_timezone", "Europe/Rome"))

    # ------------------------------------------------------------ pacchetti
    def _packages(self, brand: str) -> dict[str, tuple[str, bool]]:
        st = self.pub.storage
        out = {n: (r, True) for n, r in st.published_packages(brand).items()}
        out.update({n: (r, False) for n, r in st.packages(brand).items()})
        return out

    def calendario(self) -> None:
        today = self.pub.now.astimezone(self.tz).date()
        rows = []
        for brand in self.pub.cfg["brands"]:
            pk = self._packages(brand)
            for i in range(7):
                d = today + timedelta(days=i)
                label = ("OGGI " if i == 0 else "domani " if i == 1 else "") + f"{GIORNI[d.weekday()]} {d:%d/%m}"
                row = [label, brand]
                for lang, tipo in (("EN", "REEL"), ("EN", "CAROSELLI"), ("IT", "REEL"), ("IT", "CAROSELLI")):
                    row.append(self._cella(pk.get(f"{lang}/{tipo}/{d.isoformat()}")))
                rows.append(row)
        rows.sort(key=lambda r: (r[0].split()[-1][3:] + r[0].split()[-1][:2], r[1]))
        self.pub.sheet.replace("Calendario", rows)

    def _cella(self, found) -> str:
        if not found:
            return "— manca"
        ref, pubblicato = found
        st = self.pub.storage
        try:
            files = st.list_files(ref)
            if not any(f.lower().startswith("confermato") for f in files):
                return "⏳ aspetta il tuo confermato"
            state = {k: v for k, v in st.read_state(ref).items() if v.get("stato") != "saltato"}
        except Exception as e:
            return f"? {str(e)[:60]}"
        if not state:
            return "✓ confermato, in coda"
        c = {}
        for v in state.values():
            c[v.get("stato", "")] = c.get(v.get("stato", ""), 0) + 1
        n = len(state)
        if c.get("errore") or c.get("fallito"):
            return f"✖ ERRORE {c.get('errore', 0) + c.get('fallito', 0)}/{n} (vedi Stato)"
        if c.get("pubblicato") == n:
            return f"● pubblicato {n}/{n}"
        parts = []
        if c.get("pubblicato"):
            parts.append(f"pubblicato {c['pubblicato']}")
        if c.get("programmato"):
            parts.append(f"programmato {c['programmato']}")
        return "◐ " + " · ".join(parts) + f" (su {n})"

    # ------------------------------------------------------------ numeri
    def numeri(self) -> None:
        api = self.pub.api
        if api.dry_run:
            return
        # indice dei post del sistema (ultimi 45 giorni): postSubmissionId -> dati
        today = self.pub.now.astimezone(self.tz).date()
        index = {}
        for brand, bcfg in self.pub.cfg["brands"].items():
            for name, (ref, _) in self._packages(brand).items():
                try:
                    d = date.fromisoformat(name.rsplit("/", 1)[-1])
                except ValueError:
                    continue
                if not (today - timedelta(days=45) <= d <= today):
                    continue
                for key, rec in self.pub.storage.read_state(ref).items():
                    if rec.get("postSubmissionId") and rec.get("stato") in ("programmato", "pubblicato"):
                        acc = bcfg["accounts"].get(key.split(":")[0], {})
                        index[rec["postSubmissionId"]] = {
                            "brand": brand, "giorno": d.isoformat(), "pkg": name, "key": key,
                            "cid": rec.get("cid", ""), "account": acc.get("nome", key.split(":")[0]),
                            "platform": acc.get("platform", ""), "tipo": name.split("/")[1]}
        links = self.pub.sheet.links()  # url pubblico -> chiave Stato (dalle verifiche)
        by_key = {f"{v['brand']}|{v['pkg']}|{v['key']}": v for v in index.values()}
        items = []
        for platform in ("instagram", "youtube", "tiktok"):
            try:
                got = api.analytics(platform, 100)
                if got and not getattr(self, "_logged", False):
                    self.log(f"   (analytics: esempio di campi {sorted(got[0].keys())[:25]})")
                    self._logged = True
                items += got
            except Exception as e:
                self.log(f"(numeri {platform} non letti: {str(e)[:160]})")
        trovati = 0
        per_brand: dict[str, dict] = {}
        for it in items:
            vals = _strings(it)
            info = next((index[v] for v in vals if v in index), None)
            if not info:
                k = next((links[v] for v in vals if v in links), None)
                info = by_key.get(k) if k else None
            if not info:
                continue
            trovati += 1
            m = {k: _num(it, names) for k, names in METRICHE.items()}
            link = next((v for v in vals if v.startswith("http") and "blotato" not in v), "")
            key = f"{info['brand']}|{info['pkg']}|{info['key']}"
            self.pub.portale.post(key, views=m["views"], likes=m["likes"], commenti=m["comments"], reach=m["reach"],
                                  condivisioni=m["shares"], salvataggi=m["saves"], numeri_at=datetime.now(timezone.utc).isoformat(),
                                  **({"link": link} if link else {}))
            self.pub.sheet.upsert("Numeri", key, Brand=info["brand"], **{
                "Giorno uscita": info["giorno"], "Account": info["account"], "Tipo": info["tipo"],
                "ID contenuto": info["cid"], "Views": m["views"], "Like": m["likes"], "Commenti": m["comments"],
                "Reach": m["reach"], "Condivisioni": m["shares"], "Salvataggi": m["saves"],
                "Aggiornato (ora Italia)": _it(self.pub.now), "Link": link})
            if info["cid"]:
                b = per_brand.setdefault(info["brand"], {})
                b.setdefault(info["cid"], {})[f"{info['account']} {info['tipo']}"] = {
                    **{k: v for k, v in m.items() if v is not None}, "giorno": info["giorno"]}
        self.log(f"Numeri: {len(items)} post letti da Blotato, {trovati} del sistema.")
        if self.gh:
            for brand, cont in per_brand.items():
                repo = REPOS.get(brand)
                old, _ = self.gh.read(repo, "MEMORIA/numeri.json")
                data = json.loads(old) if old else {"contenuti": {}}
                for cid, acc in cont.items():
                    data["contenuti"].setdefault(cid, {}).update(acc)
                data["aggiornato"] = _it(self.pub.now)
                ok = self.gh.write(repo, "MEMORIA/numeri.json", json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                                   "numeri dei post (social-publisher)")
                self.log(f"   numeri scritti nel cervello {brand}: {'ok' if ok else 'ERRORE'}")

    # ------------------------------------------------------------ chi lavora
    def chi_lavora(self) -> None:
        if not self.gh:
            self.pub.sheet.replace("Chi lavora", [["", "", "Serve il secret BRAIN_TOKEN su GitHub per vedere le chat", "", "", ""]])
            return
        rows = []
        now = datetime.now(timezone.utc)
        for brand, repo in REPOS.items():
            lista = self.gh.get(repo, "MEMORIA/sessioni") or []
            for f in lista if isinstance(lista, list) else []:
                if not f.get("name", "").endswith(".json"):
                    continue
                txt, _ = self.gh.read(repo, f["path"])
                try:
                    r = json.loads(txt or "{}")
                    t = datetime.fromisoformat(r.get("ultimo") or r.get("ultimo_utc") or "")
                    if t.tzinfo is None:
                        t = t.replace(tzinfo=ROME)
                except Exception:
                    continue
                age = (now - t).total_seconds() / 60
                if age > 24 * 60:
                    continue
                stato = "chiusa" if r.get("stato") == "chiusa" else "ATTIVA" if age < 45 else "ferma"
                rows.append([brand, r.get("chi", f["name"]), r.get("cosa", ""), r.get("video") or r.get("id", ""),
                             _it(t), stato])
        rows.sort(key=lambda r: ({"ATTIVA": 0, "ferma": 1, "chiusa": 2}[r[5]], r[4]), reverse=False)
        self.pub.portale.esterne([{"chiave": f"{r[0]}|{r[1]}", "brand": r[0], "chi": r[1], "cosa": r[2], "contenuto": r[3],
                                   "ultimo": datetime.strptime(r[4], "%Y-%m-%d %H:%M").replace(tzinfo=ROME).isoformat(), "stato": r[5]}
                                  for r in rows if not r[1].startswith("studio-hub")])
        self.pub.sheet.replace("Chi lavora", rows or [["", "", "nessuna chat nelle ultime 24 ore", "", "", ""]])

    def run(self) -> None:
        for step in (self.calendario, self.numeri, self.chi_lavora):
            try:
                step()
            except Exception as e:
                self.log(f"(centro di controllo, {step.__name__}: {str(e)[:200]})")
