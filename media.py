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
    """Versione per Instagram alla massima qualità che Instagram accetta (Power, 26/11 20:08: «alzare la qualità al massimo»).
    Instagram ricomprime sempre: gli si dà il file che chiede il suo centro assistenza e l'API dei reel, così la sua
    ricompressione parte dal meglio possibile. 1080x1920, H.264 High con CABAC, 2 B-frame, GOP chiuso di mezzo secondo,
    frequenza fissa 23-60 fps, VBR quasi senza perdita (CRF 10) con tetto 24 Mbps e file sotto i 95 MB, colori BT.709,
    audio AAC-LC 48 kHz stereo, moov in testa."""
    info = probe(src)
    fps = info["fps"]
    if not 23 <= fps <= 60:
        fps = 60.0 if fps > 60 else 30.0
    fps_r = round(fps)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                         capture_output=True, text=True).stdout.strip()
    dur = float(out or 0) or 60.0
    audio_k = 256
    kbps = int(min(22000, 95_000_000 * 8 / dur / 1000 - audio_k - 300))
    gop = max(1, fps_r // 2)
    vf = (f"scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
          f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps_r},"
          f"scale=out_color_matrix=bt709:out_range=tv,format=yuv420p")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-vf", vf,
           "-c:v", "libx264", "-profile:v", "high", "-level", "4.2", "-preset", "slow",
           "-crf", "10", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps}k",
           "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0", "-bf", "2", "-flags", "+cgop",
           "-x264-params", "cabac=1",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
    if info["audio"]:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", f"{audio_k}k", "-ar", "48000", "-ac", "2"]
    cmd += ["-movflags", "+faststart", str(dest)]
    subprocess.run(cmd, check=True)
    return dest
