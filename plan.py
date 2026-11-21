"""Dal contenuto di un pacchetto ai singoli post da programmare.

Regole (vedi documento del sistema):
  reelN_IT.mp4        -> Instagram IT (reel)
  reelN_EN.mp4        -> Instagram USA (reel) + TikTok + YouTube Shorts (se non c'è shortN_EN.mp4)
  shortN_EN.mp4       -> YouTube Shorts
  carosello_IT/       -> Instagram IT (carosello)
  carosello_EN/       -> Instagram USA (carosello) + TikTok (carosello foto)
  storiaN_IT/EN.(png|jpg|mp4) -> storia Instagram IT / USA (senza link sticker: limite di Meta)
Ogni media ha una descrizione <nome>.txt e, facoltativa, una copertina <nome>_cover.png/.jpg.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from storage import FileRef

VIDEO_RE = re.compile(r"^(reel|short)(\d+)_(IT|EN)\.(mp4|mov)$", re.I)
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
STORY_RE = re.compile(r"^storia(\d+)_(IT|EN)\.(png|jpg|jpeg|mp4|mov)$", re.I)


@dataclass
class Job:
    key: str                 # identificativo stabile, es. "tiktok:reel1"
    account: str             # chiave account in config (ig_it, ig_us, tiktok, youtube)
    kind: str                # reel | carousel | short
    slot: str                # nome slot in config (reel1, carosello, short2)
    media: list[FileRef]
    caption: FileRef | None
    cover: FileRef | None = None
    source: str = ""         # nome file/cartella sorgente, per il log
    problems: list[str] = field(default_factory=list)


def _cover(files: dict[str, FileRef], base: str) -> FileRef | None:
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if f"{base}_cover{ext}" in files:
            return files[f"{base}_cover{ext}"]
    return None


def _caption(files: dict[str, FileRef], *candidates: str) -> FileRef | None:
    for c in candidates:
        if c in files:
            return files[c]
    return None


def _carousel_images(files: dict[str, FileRef], folder: str) -> list[FileRef]:
    imgs = [f for rel, f in files.items()
            if rel.startswith(folder + "/") and rel.lower().endswith(IMG_EXT)
            and "/" not in rel[len(folder) + 1:]]
    def natural(f):  # 2.png prima di 10.png
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", f.rel)]
    return sorted(imgs, key=natural)


def build_jobs(files: dict[str, FileRef]) -> list[Job]:
    jobs: list[Job] = []
    videos = {}  # (tipo, n, lingua) -> FileRef
    for rel, f in files.items():
        m = VIDEO_RE.match(rel)
        if m:
            videos[(m.group(1).lower(), int(m.group(2)), m.group(3).upper())] = f

    def vjob(key, account, kind, slot, f: FileRef, txt_bases: list[str]):
        base = f.rel.rsplit(".", 1)[0]
        cap = _caption(files, *[b + ".txt" for b in txt_bases])
        j = Job(key, account, kind, slot, [f], cap, _cover(files, base), source=f.rel)
        if not cap:
            j.problems.append(f"manca la descrizione {base}.txt")
        if account.startswith("ig_") and not j.cover:
            j.problems.append(f"manca la copertina {base}_cover.png (obbligatoria su Instagram)")
        jobs.append(j)

    for (typ, n, lang), f in sorted(videos.items()):
        if typ == "reel" and lang == "IT":
            vjob(f"ig_it:reel{n}", "ig_it", "reel", f"reel{n}", f, [f"reel{n}_IT"])
        elif typ == "reel" and lang == "EN":
            vjob(f"ig_us:reel{n}", "ig_us", "reel", f"reel{n}", f, [f"reel{n}_EN"])
            vjob(f"tiktok:reel{n}", "tiktok", "reel", f"reel{n}", f, [f"reel{n}_EN"])
            if ("short", n, "EN") not in videos:
                vjob(f"youtube:short{n}", "youtube", "short", f"short{n}", f, [f"reel{n}_EN"])
        elif typ == "short" and lang == "EN":
            vjob(f"youtube:short{n}", "youtube", "short", f"short{n}", f, [f"short{n}_EN", f"reel{n}_EN"])

    for rel, f in sorted(files.items()):
        m = STORY_RE.match(rel)
        if m:
            n, lang = int(m.group(1)), m.group(2).upper()
            acc = "ig_it" if lang == "IT" else "ig_us"
            cap = _caption(files, f"storia{n}_{lang}.txt")
            jobs.append(Job(f"{acc}:storia{n}", acc, "story", f"storia{n}", [f], cap, source=rel))

    for lang, targets in (("IT", ["ig_it"]), ("EN", ["ig_us", "tiktok"])):
        folder = f"carosello_{lang}"
        imgs = _carousel_images(files, folder)
        if not imgs:
            continue
        cap = _caption(files, f"{folder}/{folder}.txt", f"{folder}.txt")
        for acc in targets:
            j = Job(f"{acc}:carosello", acc, "carousel", "carosello", imgs[:10 if acc != "tiktok" else 35], cap,
                    source=folder + "/")
            if not cap:
                j.problems.append(f"manca la descrizione {folder}/{folder}.txt")
            if len(imgs) < 2:
                j.problems.append("il carosello ha meno di 2 immagini")
            if len(imgs) > 10 and acc != "tiktok":
                j.problems.append(f"il carosello ha {len(imgs)} immagini: su Instagram ne vanno massimo 10")
            jobs.append(j)
    return jobs


def parse_caption(text: str) -> tuple[str, str]:
    """Ritorna (titolo, testo). Una riga 'TITLE: ...' (o 'TITOLO: ...') diventa il titolo YouTube
    e viene tolta dal testo. Senza, il titolo è la riga dell'hook (prima riga che non è link né hashtag)."""
    lines = text.replace("\r\n", "\n").strip().split("\n")
    title = ""
    body = []
    for ln in lines:
        m = re.match(r"^\s*(TITLE|TITOLO)\s*:\s*(.+)$", ln, re.I)
        if m and not title:
            title = m.group(2).strip()
        else:
            body.append(ln)
    body_text = "\n".join(body).strip()
    if not title:
        for ln in body:
            s = ln.strip()
            if s and not s.startswith(("→", "#", "http")) and "axux.com" not in s and "volwick.com" not in s:
                title = s
                break
    title = re.sub(r"\s+", " ", title)[:100].strip()
    return title, body_text
