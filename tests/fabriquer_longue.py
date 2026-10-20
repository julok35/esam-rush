"""Fabrique une intervention longue déjà préparée (planches de vignettes et métadonnées, sans vrais rushs).

Usage : python tests/fabriquer_longue.py DOSSIER [--heures 3] [--pistes WZTS]
  DOSSIER : dossier racine des rushs (à mettre dans config.json, dossier_rushs)

Sert à mesurer la mémoire et la fluidité de l'appli en mode PC sur une intervention de plusieurs heures
et plusieurs caméras : les proxies sont des vidéos de 2 s (jamais lues), seules les planches de vignettes
(une image toutes les 3 s, comme server.py) et les fichiers .json sont réalistes. Nécessite ffmpeg.
"""
import json, math, shutil, subprocess, sys
from pathlib import Path

def run(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, check=True)

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    root = Path(sys.argv[1]); heures = 3.0; pistes = "WZTS"
    if "--heures" in sys.argv: heures = float(sys.argv[sys.argv.index("--heures") + 1])
    if "--pistes" in sys.argv: pistes = sys.argv[sys.argv.index("--pistes") + 1]
    dur = heures * 3600; every = 3; tw, th, cols, rows = 160, 90, 10, 10
    iv = root / "2026-09-13 Longue intervention test"; pdir = iv / "proxies"; pdir.mkdir(parents=True, exist_ok=True)
    proxy = pdir / "_proxy.mp4"
    run(["-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=2", "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "200k", str(proxy)])
    for p in pistes:
        stem = "DJI_20260913100000_0001_" + p
        (iv / (stem + ".MP4")).write_bytes(proxy.read_bytes())          # faux rush : jamais lu par l'appli
        shutil.copyfile(proxy, pdir / (stem + ".mp4"))
        run(["-f", "lavfi", "-i", "testsrc2=size=%dx%d:rate=1/%d:duration=%d" % (tw, th, every, int(dur)),
             "-vf", "tile=%dx%d" % (cols, rows), "-q:v", "6", str(pdir / (stem + ".thumbs_%03d.jpg"))])
        sheets = sorted(x.name for x in pdir.glob(stem + ".thumbs_*.jpg"))
        meta = {"nom": stem + ".MP4", "dur": dur, "w": 1920, "h": 1080, "codec": "h264", "cree": None,
                "thumbs": {"sheets": sheets, "tw": tw, "th": th, "cols": cols, "rows": rows, "every": every, "count": int(math.ceil(dur / every))}}
        (pdir / (stem + ".json")).write_text(json.dumps(meta), encoding="utf-8")
        print("piste", p, ":", len(sheets), "planches")
    proxy.unlink()
    print("cree", iv)

if __name__ == "__main__":
    main()
