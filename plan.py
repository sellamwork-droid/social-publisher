"""Dal contenuto di un pacchetto ai singoli post da programmare.

Struttura su Drive (DA MANDARE):  <BRAND>/<LINGUA>/<TIPO>/<AAAA-MM-GG>/
  LINGUA = EN | IT        TIPO = REEL | CAROSELLI | STORIE
  EN/REEL       reelN.mp4  -> Instagram USA + TikTok + YouTube Shorts   (shortN.mp4 = solo YouTube)
  IT/REEL       reelN.mp4  -> Instagram IT
  EN/CAROSELLI  01.png ... -> Instagram USA + TikTok (foto)
  IT/CAROSELLI  01.png ... -> Instagram IT
  EN|IT/STORIE  storiaN.png/.mp4 -> storia Instagram USA / IT (senza link sticker: limite di Meta)
Ogni reel ha reelN.txt (descrizione) e reelN_cover.png (copertina, obbligatoria su Instagram).
Un carosello ha le immagini numerate e un solo .txt con la descrizione.
I vecchi nomi con _EN/_IT (reel1_EN.mp4) sono accettati: la lingua la decide la cartella.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from pathlib import Path

from storage import FileRef

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


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
    alt: dict = field(default_factory=dict)
    cid: str = ""  # ID del contenuto (da ID.txt): lega il post ai numeri e alla memoria del brand  # piattaforma -> descrizione dedicata (reel1.youtube.txt)


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



LANGS = ("EN", "IT")
TIPI = ("REEL", "CAROSELLI", "STORIE")
PLATFORMS = ("instagram", "tiktok", "youtube")
MAX_HASHTAGS = {"instagram": 5, "tiktok": 5, "youtube": 15}  # IG e TikTok: limite di 5 dal dic. 2025
# (lingua, tipo) -> account. Power, 25/11/2026 00:15: «pubblichiamo anche sugli ig in inglese quando approvo le cose inglesi,
# ma partendo dal 26 novembre, e anche i tik tok italiani vanno usati per lingua ita per ora»: TikTok passa all'italiano.
# Da quando ogni account parte lo dice config.yaml («dal»).
TARGETS = {
    ("EN", "REEL"): ["ig_us", "youtube"], ("IT", "REEL"): ["ig_it", "tiktok"],
    ("EN", "CAROSELLI"): ["ig_us"], ("IT", "CAROSELLI"): ["ig_it", "tiktok"],
    ("EN", "STORIE"): ["ig_us"], ("IT", "STORIE"): ["ig_it"],
}
_SUFFIX = re.compile(r"_(IT|EN)(?=(_cover)?\.[A-Za-z0-9]+$)", re.I)
REEL_RE = re.compile(r"^(reel|short)(\d+)\.(mp4|mov)$", re.I)
STORIA_RE = re.compile(r"^storia(\d+)\.(png|jpg|jpeg|mp4|mov)$", re.I)


def build_jobs(raw: dict[str, FileRef], lang: str, tipo: str) -> list[Job]:
    lang, tipo = lang.upper(), tipo.upper()
    files = {_SUFFIX.sub("", rel): f for rel, f in raw.items()}  # reel1_EN.mp4 -> reel1.mp4
    accounts = TARGETS.get((lang, tipo), [])
    jobs: list[Job] = []

    def add(key_acc, kind, slot, media, cap, cover=None, source="", needs_cover=False, cap_name=""):
        j = Job(f"{key_acc}:{slot}", key_acc, kind, slot, media, cap, cover, source=source)
        if not cap:
            j.problems.append(f"manca la descrizione {cap_name}")
        if needs_cover and not cover:  # regola di Power (22/11/2026): ogni video ha copertina e descrizione
            j.problems.append(f"manca la copertina {(cap_name.rsplit('.', 1)[0] if cap_name else slot)}_cover.png (ogni video deve averla)")
        jobs.append(j)

    if tipo == "REEL":
        videos = {}
        for rel, f in files.items():
            m = REEL_RE.match(rel)
            if m:
                videos[(m.group(1).lower(), int(m.group(2)))] = (rel, f)
        for (typ, n), (rel, f) in sorted(videos.items()):
            base = rel.rsplit(".", 1)[0]
            cap = _caption(files, f"{base}.txt", f"reel{n}.txt")
            cover = _cover(files, base) or _cover(files, f"reel{n}")
            for acc in accounts:
                if typ == "short" and acc != "youtube":
                    continue
                if acc == "youtube":
                    if typ == "reel" and ("short", n) in videos:
                        continue
                    add(acc, "short", f"short{n}", [f], cap, cover, raw_name(raw, f), True, f"{base}.txt")
                else:
                    add(acc, "reel", f"reel{n}", [f], cap, cover, raw_name(raw, f), True, f"{base}.txt")

    elif tipo == "CAROSELLI":
        imgs = sorted([f for rel, f in files.items() if "/" not in rel and rel.lower().endswith(IMG_EXT)
                       and "_cover" not in rel.lower()],
                      key=lambda f: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", f.rel)])
        if imgs:
            txts = [f for rel, f in files.items() if rel.lower().endswith(".txt")
                    and Path(rel).stem.lower() not in ("confermato", "id")
                    and not any(rel.lower().endswith(f".{pl}.txt") for pl in PLATFORMS)]
            cap = txts[0] if len(txts) == 1 else None
            for acc in accounts:
                add(acc, "carousel", "carosello", imgs[:35 if acc == "tiktok" else 10], cap,
                    source=f"{len(imgs)} immagini", cap_name="(un solo file .txt nella cartella)")
                j = jobs[-1]
                if len(txts) > 1:
                    j.problems.append(f"ci sono {len(txts)} file .txt: ne serve uno solo (la descrizione)")
                if len(imgs) < 2:
                    j.problems.append("il carosello ha meno di 2 immagini")
                if len(imgs) > 10 and acc != "tiktok":
                    j.problems.append(f"il carosello ha {len(imgs)} immagini: su Instagram massimo 10")

    elif tipo == "STORIE":
        for rel, f in sorted(files.items()):
            m = STORIA_RE.match(rel)
            if m:
                n = int(m.group(1))
                cap = _caption(files, f"storia{n}.txt")
                for acc in accounts:
                    jobs.append(Job(f"{acc}:storia{n}", acc, "story", f"storia{n}", [f], cap, source=raw_name(raw, f)))
    for j in jobs:  # descrizioni dedicate a una piattaforma: <nome>.<piattaforma>.txt
        if j.caption:
            stem = j.caption.rel.rsplit(".", 1)[0]
            for pl in PLATFORMS:
                if f"{stem}.{pl}.txt" in files:
                    j.alt[pl] = files[f"{stem}.{pl}.txt"]
    return jobs


def raw_name(raw: dict[str, FileRef], f: FileRef) -> str:
    return f.rel


def parse_ids(text: str, jobs: list[Job]) -> None:
    """ID.txt: 'reel1=A0012' una riga per reel, oppure un solo ID (carosello)."""
    pairs = dict(re.findall(r"(?im)^\s*((?:reel|short|storia)\d+)\s*=\s*([A-Za-z]+\d+)", text))
    single = re.findall(r"(?m)^\s*([A-Za-z]+\d+)\s*$", text)
    # un solo ID nella cartella (una cartella = un video): vale anche se il portale ha spostato il video in un altro posto
    # del giorno (reel3.mp4 diventato reel1.mp4, ID.txt ancora «reel3=A0009»: Power, 24/11, il primo posto libero)
    unico = next(iter(set(pairs.values()))) if len(set(pairs.values())) == 1 else ""
    for j in jobs:
        n = re.sub(r"^short", "reel", j.slot)
        j.cid = pairs.get(j.slot) or pairs.get(n) or (single[0] if single else "") or unico


def adapt_caption(text: str, platform: str) -> str:
    """Adatta la descrizione alla piattaforma: tiene solo i primi hashtag consentiti
    (Instagram e TikTok 5, YouTube 15) e aggiunge #Shorts su YouTube."""
    limit = MAX_HASHTAGS.get(platform, 30)
    seen = 0

    def keep(m):
        nonlocal seen
        seen += 1
        return m.group(0) if seen <= limit else ""

    out = re.sub(r"(?<![\w/])#\w+", keep, text)
    if platform == "youtube" and "#shorts" not in out.lower():
        out = out.rstrip() + " #Shorts"
    out = re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", out))
    return re.sub(r"\n{3,}", "\n\n", out).strip()


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
