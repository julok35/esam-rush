"""Fabrique un faux dossier de rushs pour tester l'appli sans vrai vol.

Usage : python tests/fabriquer_rushs.py DOSSIER [--vp9]
  DOSSIER : dossier racine des rushs (mettre ce chemin dans config.json, dossier_rushs)
  --vp9   : vidéos en VP9 au lieu de H.264 (Chromium headless de Playwright ne décode pas le H.264)

Crée une intervention « 2026-09-12 Chien egare Belledonne » avec deux vols DJI
(pistes W, Z, T) et une vidéo de téléphone en portrait, horodatée par creation_time.
Nécessite ffmpeg dans le PATH (version 6.1 ou plus pour la rotation).
"""
import subprocess, sys
from pathlib import Path

def run(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, check=True)

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    root = Path(sys.argv[1]); vp9 = "--vp9" in sys.argv
    venc = ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "500k"] if vp9 else ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    iv = root / "2026-09-12 Chien egare Belledonne"; iv.mkdir(parents=True, exist_ok=True)
    motifs = {"W": "testsrc2", "Z": "testsrc", "T": "rgbtestsrc"}
    vols = [("20260912143005_0001", 90, "WZT"), ("20260912143300_0002", 40, "WT")]
    for nom, duree, pistes in vols:
        for p in pistes:
            out = iv / f"DJI_{nom}_{p}.MP4"
            run(["-f", "lavfi", "-i", f"{motifs[p]}=size=640x360:rate=30:duration={duree}"] + venc + [str(out)])
            print("cree", out.name)
    # Téléphone : portrait (rotation 90), heure prise dans creation_time (UTC)
    out = iv / "PXL_20260912_143040.mp4"; tmp = iv / "_tmp_tel.mp4"
    run(["-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=15"] + venc + [str(tmp)])
    run(["-display_rotation", "90", "-i", str(tmp), "-c", "copy",
         "-metadata", "creation_time=2026-09-12T12:30:40.000000Z", str(out)])
    tmp.unlink()
    print("cree", out.name)

if __name__ == "__main__":
    main()
