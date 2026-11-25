"""Fabrique un faux dossier de rushs pour tester l'appli sans vrai vol.

Usage : python tests/fabriquer_rushs.py DOSSIER [--vp9] [--espaces]
  DOSSIER    : dossier racine des rushs (mettre ce chemin dans config.json, dossier_rushs)
  --vp9      : vidéos en VP9 au lieu de H.264 (Chromium headless de Playwright ne décode pas le H.264)
  --espaces  : ajoute deux interventions pour la timeline compacte : « 2026-10-03 Chat bloque Chartreuse »,
               sans drone, cinq vidéos de deux téléphones espacées de 20 à 60 min, et « 2026-10-04 Vol continu »,
               un vol DJI découpé en fichiers qui se suivent sans temps mort

Crée une intervention « 2026-09-12 Chien egare Belledonne » avec deux vols DJI
(pistes W, Z, T), une vidéo de téléphone en portrait, horodatée par creation_time,
et deux photos JPEG (une du drone, une dans le sous-dossier Photos).
Nécessite ffmpeg dans le PATH (version 6.1 ou plus pour la rotation).
"""
import subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

def run(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, check=True)

def telephone(out, heure, duree, marque, modele, venc, portrait=False):
    """Vidéo de téléphone horodatée par creation_time (UTC), heure donnée en heure locale du PC."""
    tmp = out.with_name("_tmp_" + out.name)
    ct = heure.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
    run(["-f", "lavfi", "-i", f"testsrc=size=320x180:rate=30:duration={duree}"] + venc + [str(tmp)])
    rot = ["-display_rotation", "90"] if portrait else []
    run(rot + ["-i", str(tmp), "-c", "copy", "-metadata", "creation_time=" + ct, "-movflags", "use_metadata_tags",
               "-metadata", "com.android.manufacturer=" + marque, "-metadata", "com.android.model=" + modele, str(out)])
    tmp.unlink()
    print("cree", out.name)

def espaces(root, venc):
    """Intervention sans drone (vidéos de téléphone très espacées) et vol DJI continu en plusieurs fichiers."""
    iv = root / "2026-10-03 Chat bloque Chartreuse"; iv.mkdir(parents=True, exist_ok=True)
    for nom, (h, m, s), duree, marque, modele, portrait in (
            ("PXL_20261003_091200.mp4", (9, 12, 0), 40, "Google", "Pixel 8", True),
            ("PXL_20261003_093830.mp4", (9, 38, 30), 25, "Google", "Pixel 8", True),
            ("20261003_093910.mp4", (9, 39, 10), 20, "samsung", "SM-S911B", False),
            ("20261003_103100.mp4", (10, 31, 0), 30, "samsung", "SM-S911B", False),
            ("PXL_20261003_110500.mp4", (11, 5, 0), 35, "Google", "Pixel 8", True)):
        telephone(iv / nom, datetime(2026, 10, 3, h, m, s), duree, marque, modele, venc, portrait)
    iv = root / "2026-10-04 Vol continu"; iv.mkdir(parents=True, exist_ok=True)
    for nom, p in (("20261004101500_0001", "W"), ("20261004101600_0002", "W"), ("20261004101500_0001", "Z"), ("20261004101600_0002", "Z")):
        out = iv / f"DJI_{nom}_{p}.MP4"
        run(["-f", "lavfi", "-i", f"{'testsrc2' if p == 'W' else 'testsrc'}=size=640x360:rate=30:duration=60"] + venc + [str(out)])
        print("cree", out.name)

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
    # Téléphone : portrait (rotation 90), heure prise dans creation_time (UTC) ; 14:30:40 en heure locale du PC,
    # pour tomber pendant le premier vol DJI quel que soit le fuseau de la machine
    out = iv / "PXL_20260912_143040.mp4"; tmp = iv / "_tmp_tel.mp4"
    ct = datetime(2026, 9, 12, 14, 30, 40).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
    run(["-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=15"] + venc + [str(tmp)])
    # marque et modèle comme un Android récent (meta > keys) : la vidéo va sur la piste « Google Pixel 8 »
    run(["-display_rotation", "90", "-i", str(tmp), "-c", "copy", "-metadata", "creation_time=" + ct, "-movflags", "use_metadata_tags",
         "-metadata", "com.android.manufacturer=Google", "-metadata", "com.android.model=Pixel 8", str(out)])
    tmp.unlink()
    print("cree", out.name)
    # Photos JPEG : une du drone (heure dans le nom), une dans le sous-dossier Photos
    (iv / "Photos").mkdir(exist_ok=True)
    for out, motif in ((iv / "DJI_20260912143050_0003_W.JPG", "testsrc2"), (iv / "Photos" / "ESAM_photo_terrain.jpg", "smptebars")):
        run(["-f", "lavfi", "-i", f"{motif}=size=1600x1200:duration=1", "-frames:v", "1", "-q:v", "3", str(out)])
        print("cree", out.name)
    if "--espaces" in sys.argv: espaces(root, venc)

if __name__ == "__main__":
    main()
