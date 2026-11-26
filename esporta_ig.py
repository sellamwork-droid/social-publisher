#!/usr/bin/env python3
"""Esportazione finale di ogni reel, fatta direttamente come la chiede Instagram (Power, 26/11 20:13: «falla direttamente
come chiede ig»). È l'ULTIMO passo prima del pacchetto: si lancia sul video finito (con audio) e il file che esce è
quello che si consegna. Vale per IT ed EN, per Instagram, YouTube e TikTok.

    python3 esporta_ig.py <video_finito.mp4> <reel1.mp4>

Specifiche (centro assistenza Instagram e API dei reel di Meta): 1080x1920 9:16, H.264 High con CABAC, 2 B-frame,
GOP chiuso di mezzo secondo, frequenza fissa tra 23 e 60 fps (si tiene quella del video), VBR sotto i 25 Mb/s
(CRF 10 quasi senza perdita, tetto 22 Mb/s), file sotto i 95 MB (limite API 100 MB), colori BT.709,
audio AAC-LC 48 kHz stereo 256 kb/s, moov in testa. Il controllo è in cervello.py pacchetto (controlla_ig)."""
import json
import subprocess
import sys
from pathlib import Path


def info(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(p)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def esporta(src, dest):
    j = info(src)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    has_a = any(s["codec_type"] == "audio" for s in j["streams"])
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    fps = min(60, max(23, round(fps)))
    dur = float(j["format"].get("duration") or 60)
    audio_k = 256
    kbps = int(min(22000, 95_000_000 * 8 / dur / 1000 - audio_k - 300))
    gop = max(1, fps // 2)
    vf = (f"scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
          f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps},"
          f"scale=out_color_matrix=bt709:out_range=tv,format=yuv420p")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-vf", vf,
           "-c:v", "libx264", "-profile:v", "high", "-level", "4.2", "-preset", "slow",
           "-crf", "10", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps}k",
           "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0", "-bf", "2", "-flags", "+cgop",
           "-x264-params", "cabac=1",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
    if has_a:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", f"{audio_k}k", "-ar", "48000", "-ac", "2"]
    cmd += ["-movflags", "+faststart", str(dest)]
    subprocess.run(cmd, check=True)
    return dest


def controlla(p):
    """Errori se il file non è come lo chiede Instagram (lista vuota = va bene)."""
    err = []
    try:
        j = info(p)
    except Exception as e:
        return [f"non leggibile ({e})"]
    vs = [s for s in j["streams"] if s["codec_type"] == "video"]
    au = [s for s in j["streams"] if s["codec_type"] == "audio"]
    if not vs:
        return ["senza video"]
    v = vs[0]
    if (v.get("width"), v.get("height")) != (1080, 1920):
        err.append(f"{v.get('width')}x{v.get('height')}, serve 1080x1920")
    if v.get("codec_name") != "h264" or (v.get("profile") or "") != "High":
        err.append(f"{v.get('codec_name')} {v.get('profile')}, serve H.264 High")
    num, den = (v.get("avg_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0
    if not 22.9 <= fps <= 60.1:
        err.append(f"{fps:.2f} fps, serve tra 23 e 60")
    if v.get("color_space") != "bt709":
        err.append("colori non BT.709")
    size = int(j["format"].get("size") or 0)
    br = int(j["format"].get("bit_rate") or 0)
    if br > 25_000_000:
        err.append(f"{br // 1000} kb/s, Instagram accetta al massimo 25 Mb/s")
    if size > 95_000_000:
        err.append(f"{size / 1e6:.0f} MB, serve sotto i 95 MB")
    if au:
        a = au[0]
        if a.get("codec_name") != "aac" or a.get("sample_rate") != "48000" or a.get("channels") != 2:
            err.append(f"audio {a.get('codec_name')} {a.get('sample_rate')} Hz {a.get('channels')} canali, serve AAC 48 kHz stereo")
    # GOP chiuso di mezzo secondo: fotogrammi chiave al massimo ogni 0,5 s (+ un margine)
    try:
        kf = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                             "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(p)],
                            capture_output=True, text=True, timeout=120).stdout.split()
        t = [float(x.strip(",")) for x in kf if x.strip(",")]
        if len(t) > 1 and max(b - a for a, b in zip(t, t[1:])) > 0.6:
            err.append(f"fotogrammi chiave ogni {max(b - a for a, b in zip(t, t[1:])):.1f} s, Instagram li vuole ogni 0,5 s")
    except Exception:
        pass
    return err


if __name__ == "__main__":
    if len(sys.argv) == 2:
        e = controlla(sys.argv[1])
        print("OK: come lo chiede Instagram" if not e else "NON VA: " + " · ".join(e))
        sys.exit(1 if e else 0)
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dest = Path(sys.argv[1]), Path(sys.argv[2])
    if src.resolve() == dest.resolve():
        sys.exit("l'uscita deve essere un file diverso dall'ingresso")
    esporta(src, dest)
    e = controlla(dest)
    print(f"{dest}: " + ("OK, come lo chiede Instagram" if not e else "NON VA: " + " · ".join(e)))
    sys.exit(1 if e else 0)
