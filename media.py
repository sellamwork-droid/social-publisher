"""Preparazione dei file prima dell'invio: copertine in JPEG leggero e copertina TikTok come primo frame."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image


def cover_jpeg(src: Path, dest: Path, size=(1080, 1920), max_bytes=1_900_000) -> Path:
    """Copertina verticale 1080x1920 in JPEG sotto i 2 MB (limite YouTube; Instagram accetta fino a 8 MB)."""
    img = Image.open(src).convert("RGB")
    img.thumbnail((size[0] * 2, size[1] * 2))
    # adatta a 9:16 senza deformare: riempie e ritaglia al centro
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - tw) // 2, (img.height - th) // 2
    img = img.crop((left, top, left + tw, top + th))
    for q in (92, 88, 84, 80, 75, 70):
        img.save(dest, "JPEG", quality=q, optimize=True, progressive=True)
        if dest.stat().st_size <= max_bytes:
            break
    return dest


def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout
    streams = json.loads(out)["streams"]
    v = next(s for s in streams if s["codec_type"] == "video")
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    if not 10 <= fps <= 120:
        fps = 30.0
    return {
        "w": int(v["width"]), "h": int(v["height"]), "fps": fps,
        "audio": any(s["codec_type"] == "audio" for s in streams),
    }


def prepend_cover_frame(video: Path, cover: Path, dest: Path) -> Path:
    """Mette la copertina come PRIMO frame (dura un solo frame, ~33 ms: non si vede guardando il video).
    Così su TikTok la copertina scelta col frame 0 è esattamente la nostra immagine."""
    info = probe(video)
    w, h, fps = info["w"], info["h"], info["fps"]
    frame = 1.0 / fps
    delay_ms = round(frame * 1000)
    vf_cover = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"setsar=1,fps={fps},format=yuv420p,trim=end_frame=1[c]")
    vf_main = f"[1:v]scale={w}:{h},setsar=1,fps={fps},format=yuv420p[v]"
    graph = f"{vf_cover};{vf_main};[c][v]concat=n=2:v=1:a=0[outv]"
    cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-t", f"{frame:.5f}",
           "-i", str(cover), "-i", str(video)]
    if info["audio"]:
        graph += f";[1:a]adelay={delay_ms}:all=1[outa]"
        maps = ["-map", "[outv]", "-map", "[outa]", "-c:a", "aac", "-b:a", "192k"]
    else:
        maps = ["-map", "[outv]"]
    cmd += ["-filter_complex", graph, *maps, "-c:v", "libx264", "-crf", "17", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest)]
    subprocess.run(cmd, check=True)
    return dest


def video_instagram(src: Path, dest: Path) -> Path:
    """Versione per Instagram: la stessa esportazione delle chat (esporta_ig.py, 30 fps, Power 26/11 22:32)."""
    from esporta_ig import esporta
    return esporta(src, dest)
