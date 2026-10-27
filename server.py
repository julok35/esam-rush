#!/usr/bin/env python3
"""ESAM - Serveur local de dérushage drone.

Tourne sur le PC Windows qui synchronise le Drive ESAM (Google Drive pour ordinateur).
Sert l'appli de dérushage et exécute les traitements vidéo avec ffmpeg :
proxies 540p + vignettes, photos pleine résolution, vidéo compilée en résolution d'origine.

Dépendances : Python 3.10+ (bibliothèque standard uniquement) et ffmpeg/ffprobe dans le PATH.
Écoute uniquement sur 127.0.0.1 : l'accès depuis le téléphone passe par « tailscale serve ».
"""
import base64, json, math, os, re, shutil, struct, subprocess, tempfile, threading, time, traceback, unicodedata, urllib.parse
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

VERSION = "0.14"
HERE = Path(__file__).resolve().parent
CFG_PATH = Path(os.environ.get("ESAM_CONFIG") or HERE / "config.json")  # ESAM_CONFIG : tests
if not CFG_PATH.exists() and (HERE / "config.exemple.json").exists():
    shutil.copyfile(HERE / "config.exemple.json", CFG_PATH)
CFG = json.loads(CFG_PATH.read_text(encoding="utf-8"))
ROOT = Path(CFG["dossier_rushs"]).expanduser()
PORT = int(CFG.get("port", 8765))
HOST = CFG.get("ecoute", "127.0.0.1")
IDLE_MIN = float(CFG.get("veille_apres_minutes", 20))
IDLE_MODE = CFG.get("mode_inactivite", "veille")      # veille | arret | aucun
PROXY_H = int(CFG.get("proxy_hauteur", 540))
THUMB_EVERY = float(CFG.get("vignette_toutes_secondes", 3))
FINAL_CODEC = CFG.get("codec_video_finale", "h264")    # h264 | h265
WORK_ROOT = Path(CFG.get("dossier_travail") or tempfile.gettempdir())
JOBS_FILE = HERE / "travaux.json"
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
PROXY_DIR = "proxies"
WORK_DIR = ".derushage"
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
WIN = os.name == "nt"
NOWIN = subprocess.CREATE_NO_WINDOW if WIN else 0

LOG = HERE / "derushage.log"
def log(*a):
    """Écrit une ligne horodatée dans derushage.log et sur la sortie standard."""
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")
    except Exception: pass
    print(line, flush=True)

def clean(s):  # règle typographique ESAM : pas de tiret long
    """Remplace les tirets longs par un tiret simple (règle typographique ESAM)."""
    return str(s).replace("\u2014", "-").replace("\u2013", "-")

def slug(s):
    """Nom de fichier sûr : sans accent, lettres, chiffres et tirets bas seulement, 40 caractères au plus."""
    s = unicodedata.normalize("NFD", clean(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:40]

# ---------------------------------------------------------------- ffmpeg
def run(cmd, total=None, progress=None, job=None):
    """Lance ffmpeg ; appelle progress(fraction) ; annulable via job['cancel']."""
    cmd = [cmd[0], "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", "-loglevel", "error"] + cmd[1:]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", creationflags=NOWIN)
    if job is not None: job["_proc"] = p
    err = []
    t = threading.Thread(target=lambda: err.extend(p.stderr.readlines()), daemon=True); t.start()
    for line in p.stdout:
        if job is not None and job.get("cancel"):
            p.kill(); break
        if progress and total and line.startswith("out_time_us="):
            try: progress(min(1.0, int(line.split("=")[1]) / 1e6 / total))
            except ValueError: pass
    p.wait(); t.join(2)
    if job is not None: job.pop("_proc", None)
    if job is not None and job.get("cancel"): raise Cancelled()
    if p.returncode != 0:
        log("ffmpeg a échoué (code %s) : %s\n%s" % (p.returncode, " ".join(cmd), "".join(err[-30:])))
        raise RuntimeError("ffmpeg (code %s) : %s" % (p.returncode, "".join(err[-4:]).strip()[:400] or "pas de message"))

class Cancelled(Exception): pass

def probe(path):
    """Métadonnées d'une vidéo par ffprobe : largeur et hauteur après rotation, durée, codec, heure de création (UTC) ; None sans piste vidéo."""
    out = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NOWIN)
    d = json.loads(out.stdout or "{}")
    vs = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    if not vs: return None
    rot = 0
    for sd in vs.get("side_data_list", []) or []:
        if "rotation" in sd: rot = int(float(sd["rotation"]))
    if not rot and "rotate" in (vs.get("tags") or {}): rot = int(vs["tags"]["rotate"])
    w, h = int(vs.get("width", 0)), int(vs.get("height", 0))
    if abs(rot) % 180 == 90: w, h = h, w
    dur = float(d.get("format", {}).get("duration") or vs.get("duration") or 0)
    ct = (d.get("format", {}).get("tags") or {}).get("creation_time") or (vs.get("tags") or {}).get("creation_time")
    created = None
    if ct:
        try:
            created = datetime.fromisoformat(ct.replace("Z", "+00:00")).timestamp()
            if created < 1.2e9: created = None
        except ValueError: pass
    return {"w": w, "h": h, "dur": dur, "codec": vs.get("codec_name"), "created": created}

ENC = {}
def detect_encoders():
    """Choisit les encodeurs ffmpeg (NVENC si la carte NVIDIA répond, sinon logiciel) pour les proxies et la vidéo finale."""
    def ok(enc):
        r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=black:s=320x240:d=0.2",
                            "-c:v", enc, "-f", "null", "-"], capture_output=True, creationflags=NOWIN)
        return r.returncode == 0
    nv264, nv265 = ok("h264_nvenc"), ok("hevc_nvenc")
    ENC["proxy"] = (["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "28"] if nv264
                    else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "28"])
    if CFG.get("_test_vp9"): ENC["proxy"] = ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "600k"]  # tests internes
    if FINAL_CODEC == "h265":
        ENC["final"] = (["-c:v", "hevc_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "22", "-tag:v", "hvc1"] if nv265
                        else ["-c:v", "libx265", "-preset", "medium", "-crf", "22", "-tag:v", "hvc1"])
    else:
        ENC["final"] = (["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "20"] if nv264
                        else ["-c:v", "libx264", "-preset", "medium", "-crf", "19"])
    ENC["gpu"] = nv264
    log("Encodage :", "carte NVIDIA (NVENC)" if nv264 else "processeur (logiciel)")

# ---------------------------------------------------------------- dossiers
def folder(name):
    """Dossier d'intervention à partir de son nom, en refusant tout chemin (séparateurs, point initial, '..')."""
    name = clean(name or "")
    if not name or "/" in name or "\\" in name or name.startswith(".") or ".." in name:
        raise ValueError("dossier invalide")
    p = ROOT / name
    if not p.is_dir(): raise ValueError("dossier introuvable : " + name)
    return p

def videos(d):
    """Rushs du dossier : fichiers vidéo hors productions ESAM (compilation, réel, story) et fichiers cachés."""
    return sorted(f for f in d.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXT and not f.name.startswith(("ESAM_Compilation", "ESAM_Reel", "ESAM_Story", ".")))

def proxy_of(f): return f.parent / PROXY_DIR / (f.stem + ".mp4")

IMG_EXT = {".jpg", ".jpeg"}

def photos(d):
    """Photos JPEG de l'intervention (dossier des rushs et sous-dossier Photos), en chemins relatifs."""
    out = []
    for sub in (d, d / "Photos"):
        if not sub.is_dir(): continue
        for f in sub.iterdir():
            if f.is_file() and f.suffix.lower() in IMG_EXT and not f.name.startswith("."):
                out.append({"nom": f.relative_to(d).as_posix(), "heure": f.stat().st_mtime})
    out.sort(key=lambda x: x["nom"].lower())
    return out

def photo_file(d, nom):
    """Chemin d'une photo de l'intervention à partir de son nom relatif, vérifié dans la liste de photos()."""
    nom = clean(nom or "")
    if not any(x["nom"] == nom for x in photos(d)): raise ValueError("photo introuvable : " + nom)
    return d / nom

def jpeg_orientation(p):
    """Orientation EXIF d'un JPEG (1 à 8), 1 si absente ou illisible."""
    try:
        with open(p, "rb") as f:
            if f.read(2) != b"\xff\xd8": return 1
            while True:
                m = f.read(4)
                if len(m) < 4 or m[0] != 0xFF or m[1] == 0xDA: return 1
                ln = int.from_bytes(m[2:4], "big")
                if m[1] != 0xE1: f.seek(ln - 2, 1); continue
                seg = f.read(ln - 2)
                if seg[:6] != b"Exif\0\0": continue
                t = seg[6:]; e = "<" if t[:2] == b"II" else ">"
                off = struct.unpack(e + "I", t[4:8])[0]
                for i in range(struct.unpack(e + "H", t[off:off + 2])[0]):
                    en = t[off + 2 + i * 12: off + 14 + i * 12]
                    if struct.unpack(e + "H", en[:2])[0] == 0x0112: return struct.unpack(e + "H", en[8:10])[0]
                return 1
    except (OSError, struct.error, IndexError): return 1

ORIENT = {2: "hflip", 3: "hflip,vflip", 4: "vflip", 5: "transpose=0", 6: "transpose=1", 7: "transpose=3", 8: "transpose=2"}
PHOTO_SIZES = {"petite": 360, "moyenne": 3200}

def photo_copy(d, nom, taille):
    """Copie redressée et réduite d'une photo (vignette ou version de travail), gardée en cache dans proxies/photos."""
    src = photo_file(d, nom); side = PHOTO_SIZES.get(taille, 360)
    out = d / PROXY_DIR / "photos" / ("%s_%s_%s.jpg" % (re.sub(r"[^A-Za-z0-9]+", "_", nom)[:80], taille, int(src.stat().st_mtime)))
    if out.exists(): return out
    out.parent.mkdir(parents=True, exist_ok=True)
    info = probe(src) or {}
    o = jpeg_orientation(src); w, h = info.get("w") or side, info.get("h") or side
    if o >= 5: w, h = h, w
    k = min(1.0, side / max(w, h, 1))
    vf = ([ORIENT[o]] if o in ORIENT else []) + ["scale=%d:%d" % (max(2, int(w * k) // 2 * 2), max(2, int(h * k) // 2 * 2))]
    tmp = out.with_suffix(".tmp.jpg")
    run([FFMPEG, "-noautorotate", "-i", str(src), "-vf", ",".join(vf), "-frames:v", "1", "-q:v", "3", str(tmp)])
    os.replace(tmp, out)
    return out

def list_interventions():
    """Sous-dossiers du dossier des rushs, du plus récent au plus ancien, avec l'avancement des proxies.
    Un seul parcours par dossier : sur un Drive en mode flux, chaque listage coûte un aller-retour."""
    out = []
    if not ROOT.is_dir(): return out
    for d in ROOT.iterdir():
        if not d.is_dir() or d.name.startswith((".", "_")): continue
        try:
            names = [x.name for x in d.iterdir()]
            vids = [n for n in names if Path(n).suffix.lower() in VIDEO_EXT and not n.startswith(("ESAM_Compilation", "ESAM_Reel", "ESAM_Story", "."))]
            done = sum(1 for n in vids if (d / PROXY_DIR / (Path(n).stem + ".json")).exists())
            out.append({"nom": d.name, "videos": len(vids), "proxies": done,
                        "fiche": any(n.startswith("ESAM_Derushage") for n in names),
                        "compilation": any(n.startswith("ESAM_Compilation") for n in names),
                        "maj": d.stat().st_mtime})
        except OSError as e:
            log("Lecture impossible", d, e)
    out.sort(key=lambda x: -x["maj"])
    return out

def manifest(d):
    """Ce que l'appli charge à l'ouverture : métadonnées de chaque proxy (avec les URL des planches) et photos."""
    clips = []
    for f in videos(d):
        meta_p = d / PROXY_DIR / (f.stem + ".json")
        if not meta_p.exists(): continue
        m = json.loads(meta_p.read_text(encoding="utf-8"))
        rel = lambda p: "files/" + urllib.parse.quote(d.name) + "/" + urllib.parse.quote(PROXY_DIR) + "/" + urllib.parse.quote(p)
        m["proxy"] = rel(f.stem + ".mp4")
        m["thumbs"]["sheets"] = [rel(s) for s in m["thumbs"]["sheets"]]
        clips.append(m)
    return {"dossier": d.name, "clips": clips, "photos": photos(d)}

# ---------------------------------------------------------------- travaux
JOBS, JLOCK, QUEUE = [], threading.Lock(), []
QCOND = threading.Condition(JLOCK)
LAST_ACTIVITY = [time.time()]

def new_job(kind, d, payload=None):
    """Crée un calcul (proxies, video ou reel), le met en file et le persiste ; 30 calculs gardés dans l'historique."""
    job = {"id": "%x" % int(time.time() * 1000), "type": kind, "dossier": d.name, "etat": "attente",
           "avance": 0.0, "libelle": "En attente", "erreur": None, "resultat": None, "debut": time.time(), "_payload": payload}
    with QCOND:
        JOBS.append(job); del JOBS[:-30]
        QUEUE.append(job); QCOND.notify()
    save_jobs()
    return job

def public(job): return {k: v for k, v in job.items() if not k.startswith("_") and k != "cancel"}

SAVE_LOCK = threading.Lock()
def save_jobs():
    """Écrit travaux.json de façon atomique ; un seul écrivain à la fois."""
    try:
        with JLOCK: data = [public(j) for j in JOBS]
        with SAVE_LOCK:  # deux threads ne doivent pas ecrire le meme fichier temporaire
            tmp = JOBS_FILE.with_suffix(".tmp"); tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, JOBS_FILE)
    except Exception as e: log("Sauvegarde des travaux impossible :", e)

def load_jobs():
    """Relit travaux.json au démarrage ; un calcul resté en cours est marqué « interrompu »."""
    if not JOBS_FILE.exists(): return
    try: data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except Exception: return
    for j in data:
        if j.get("etat") in ("attente", "en_cours"):
            j["etat"] = "interrompu"
            j["erreur"] = "Le programme du PC s'est arrêté pendant le calcul (veille, redémarrage ou arrêt). Relancez le calcul."
        JOBS.append(j)
    del JOBS[:-30]

def worker():
    """Fil unique qui exécute les calculs de la file dans l'ordre et tient le PC éveillé pendant ce temps."""
    while True:
        with QCOND:
            while not QUEUE: QCOND.wait()
            job = QUEUE.pop(0)
        job["etat"] = "en_cours"
        save_jobs()
        log("Début", job["type"], job["dossier"])
        keep_awake(True)
        try:
            if job["type"] == "proxies": do_proxies(job)
            elif job["type"] == "video": do_video(job)
            elif job["type"] == "reel": do_reel(job)
            job["etat"], job["avance"] = "termine", 1.0
        except Cancelled:
            job["etat"], job["libelle"] = "annule", "Annulé"
        except Exception as e:
            job["etat"], job["erreur"] = "erreur", clean(str(e))[:500]
            log("ERREUR", job["type"], job["dossier"], traceback.format_exc())
        finally:
            job.pop("_payload", None)
            log("Fin", job["type"], job["dossier"], job["etat"], job.get("erreur") or "")
            save_jobs()
            with JLOCK: busy = bool(QUEUE)
            if not busy: keep_awake(False)
            LAST_ACTIVITY[0] = time.time()

def do_proxies(job):
    """Calcul « proxies » : pour chaque rush sans .json, proxy 540p et planches de vignettes 10 x 10 en une passe ffmpeg, puis métadonnées."""
    d = folder(job["dossier"]); pdir = d / PROXY_DIR; pdir.mkdir(exist_ok=True)
    todo = [f for f in videos(d) if not (pdir / (f.stem + ".json")).exists()]
    infos = [(f, probe(f)) for f in todo]
    total = sum(i["dur"] for _, i in infos if i) or 1
    acc = 0.0
    for k, (f, info) in enumerate(infos):
        if not info: log("Pas de piste vidéo :", f); continue
        job["libelle"] = "Proxy %d sur %d : %s" % (k + 1, len(infos), f.name)
        tw = max(2, int(round(90 * info["w"] / max(1, info["h"]) / 2)) * 2)
        tmp_proxy = pdir / (f.stem + ".tmp.mp4")
        thumb_pat = pdir / (f.stem + ".thumbs_%03d.jpg")
        for old in pdir.glob(f.stem + ".thumbs_*.jpg"): old.unlink()
        fc = ("[0:v]split=2[a][b];[a]scale=-2:'min(%d,ih)',format=yuv420p[p];"
              "[b]fps=1/%g,scale=%d:90,tile=10x10[t]") % (PROXY_H, THUMB_EVERY, tw)
        cmd = [FFMPEG, "-hwaccel", "auto", "-i", str(f), "-filter_complex", fc,
               "-map", "[p]"] + ENC["proxy"] + ["-g", "30", "-an", "-map_metadata", "0", "-movflags", "+faststart", "-f", "mp4", str(tmp_proxy),
               "-map", "[t]", "-q:v", "6", str(thumb_pat)]
        base = acc
        run(cmd, info["dur"], lambda x: job.__setitem__("avance", (base + x * info["dur"]) / total), job)
        os.replace(tmp_proxy, pdir / (f.stem + ".mp4"))
        sheets = sorted(p.name for p in pdir.glob(f.stem + ".thumbs_*.jpg"))
        meta = {"nom": f.name, "dur": info["dur"], "w": info["w"], "h": info["h"], "codec": info["codec"], "cree": info["created"],
                "thumbs": {"sheets": sheets, "tw": tw, "th": 90, "cols": 10, "rows": 10, "every": THUMB_EVERY,
                           "count": int(math.ceil(info["dur"] / THUMB_EVERY))}}
        (pdir / (f.stem + ".json")).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        acc += info["dur"]
    job["libelle"] = "Proxies prêts"
    job["resultat"] = {"fichiers": len(infos)}

def do_video(job):
    """Calcul « video » : cartons (PNG envoyés par l'appli) et extraits à la résolution d'origine, concaténés avec chapitres, logo et sous-titres internes à part."""
    d = folder(job["dossier"]); pl = job["_payload"]
    fmt = pl.get("format", "h")
    items = pl["passages"]
    srcs = {}
    for it in items:
        for pc in it["morceaux"]:
            name = pc["fichier"]
            if name not in srcs:
                f = d / name
                if not f.is_file() or f.parent != d: raise ValueError("rush introuvable : " + name)
                srcs[name] = probe(f)
    W = max(i["w"] for i in srcs.values()); H = max(i["h"] for i in srcs.values())
    H += H % 2
    if fmt == "v": W = int(round(H * 9 / 16))
    W += W % 2
    if fmt == "v":
        vclip = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (W, H, W, H)
    else:
        vclip = "scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:black" % (W, H, W, H)
    vcard = "scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:black" % (W, H, W, H)
    tail = ",fps=30,setsar=1,format=yuv420p"
    segs = [("carte", pl["ouverture"]["image"], float(pl["ouverture"]["duree"]), None, "Ouverture", None)]
    for n, it in enumerate(items):
        segs.append(("carte", it["image"], float(it["duree"]), None, clean(it.get("titre") or "Passage %d" % (n + 1)), None))
        for pc in it["morceaux"]:
            segs.append(("clip", pc["fichier"], float(pc["fin"]) - float(pc["debut"]), float(pc["debut"]), None, n))
    total = sum(s[2] for s in segs) or 1
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    need = total * (W * H / (3840 * 2160)) * 8e6 * 2.5      # estimation large : segments + assemblage
    free = shutil.disk_usage(WORK_ROOT).free
    log("Vidéo %s : %dx%d, %d segments, %.0f s, %.1f Go libres dans %s" % (pl.get("nom"), W, H, len(segs), total, free / 1e9, WORK_ROOT))
    if free < need:
        raise RuntimeError("Espace disque insuffisant dans %s : %.1f Go libres, environ %.1f Go nécessaires" % (WORK_ROOT, free / 1e9, need / 1e9))
    work = Path(tempfile.mkdtemp(prefix="esam_video_", dir=str(WORK_ROOT)))
    try:
        files, acc, chapters, pos, spans = [], 0.0, [], 0.0, {}
        logo = None
        if pl.get("logo"):
            logo = work / "logo.png"
            logo.write_bytes(base64.b64decode(pl["logo"].split(",", 1)[-1]))
        m = min(W, H); LH = int(round(m * 0.09)) // 2 * 2; MG = int(round(m * 0.03))
        for k, (kind, src, dur, start, chap, idx) in enumerate(segs):
            out = work / ("s%03d.mp4" % k)
            if kind == "carte":
                png = work / ("c%03d.png" % k)
                png.write_bytes(base64.b64decode(src.split(",", 1)[-1]))
                job["libelle"] = "Carton %d" % (k + 1)
                cmd = [FFMPEG, "-loop", "1", "-framerate", "30", "-i", str(png), "-t", "%.3f" % dur, "-vf", vcard + tail]
            else:
                job["libelle"] = "Extrait %d sur %d : %s" % (k + 1, len(segs), src)
                cmd = [FFMPEG, "-hwaccel", "auto", "-ss", "%.3f" % start, "-t", "%.3f" % dur, "-i", str(d / src)]
                if logo:      # petit logo ESAM en bas à droite de toutes les images
                    cmd += ["-i", str(logo), "-filter_complex",
                            "[0:v]%s%s[b];[1:v]scale=%d:%d,format=rgba,colorchannelmixer=aa=0.9[l];[b][l]overlay=W-w-%d:H-h-%d:eof_action=repeat,format=yuv420p"
                            % (vclip, tail, LH, LH, MG, MG)]
                else:
                    cmd += ["-vf", vclip + tail]
            cmd += ENC["final"] + ["-g", "60", "-an", "-r", "30", str(out)]
            base = acc
            run(cmd, dur, lambda x: job.__setitem__("avance", 0.97 * (base + x * dur) / total), job)
            if not out.exists() or out.stat().st_size < 1000:
                raise RuntimeError("segment %d vide (%s)" % (k + 1, src if kind == "clip" else "carton"))
            real = (probe(out) or {}).get("dur") or dur       # durée réelle, pour des chapitres exacts
            if chap: chapters.append([pos, chap])
            if idx is not None:
                sp = spans.setdefault(idx, [pos, pos]); sp[1] = pos + real
            pos += real
            files.append(out); acc += dur
        job["libelle"] = "Assemblage"
        lst = work / "liste.txt"
        lst.write_text("".join("file '%s'\n" % f.as_posix() for f in files), encoding="utf-8")
        name = clean(pl.get("nom") or "ESAM_Compilation.mp4")
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        if not name.lower().endswith(".mp4"): name += ".mp4"
        tmp = work / "final.mp4"
        meta = work / "chapitres.txt"
        def esc_meta(t): return re.sub(r"([=;#\\\n])", r"\\\1", t)
        lines = [";FFMETADATA1", "title=" + esc_meta(clean(pl.get("titre") or name[:-4]))]
        for i, (a, t) in enumerate(chapters):
            b = chapters[i + 1][0] if i + 1 < len(chapters) else pos
            lines += ["[CHAPTER]", "TIMEBASE=1/1000", "START=%d" % round(a * 1000), "END=%d" % round(b * 1000), "title=" + esc_meta(t)]
        meta.write_text("\n".join(lines) + "\n", encoding="utf-8")
        run([FFMPEG, "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(meta), "-map", "0", "-map_metadata", "1", "-map_chapters", "1",
             "-c", "copy", "-movflags", "+faststart", str(tmp)], None, None, job)
        info = probe(tmp)
        if not info or info["dur"] < 0.5:
            raise RuntimeError("la vidéo assemblée est illisible")
        job["libelle"] = "Copie dans le Drive"
        part = d / (name + ".partiel")
        size = tmp.stat().st_size
        try:
            shutil.copyfile(str(tmp), str(part))      # contenu seul : le disque Drive refuse parfois les attributs
            if part.stat().st_size != size: raise RuntimeError("copie incomplète")
            os.replace(str(part), str(d / name))
        except Exception as e:
            try: part.unlink()
            except OSError: pass
            keep = WORK_ROOT / name
            shutil.copyfile(str(tmp), str(keep))
            raise RuntimeError("copie dans le Drive impossible (%s). La vidéo est gardée sur le PC : %s" % (e, keep))
        def ts(x):
            x = int(x); h, m, sec = x // 3600, x % 3600 // 60, x % 60
            return ("%d:%02d:%02d" % (h, m, sec)) if h else ("%d:%02d" % (m, sec))
        chap_txt = "\n".join("%s %s" % (ts(a), t) for a, t in chapters) + "\n"
        chap_name = name[:-4] + "_chapitres.txt"
        try: (d / chap_name).write_text(clean(chap_txt), encoding="utf-8")
        except OSError as e: log("Fichier de chapitres non écrit :", e); chap_name = None
        # commentaires internes : fichier de sous-titres à part, jamais incrusté dans la vidéo (miroir de buildSrt dans index.html)
        def st(x):
            ms_ = int(round(max(0, x) * 1000))
            return "%02d:%02d:%02d,%03d" % (ms_ // 3600000, ms_ % 3600000 // 60000, ms_ % 60000 // 1000, ms_ % 1000)
        who = clean(pl.get("auteur") or "").strip()
        srt, nb = [], 0
        for n, it in enumerate(items):
            com = clean(it.get("commentaire") or "").strip()
            if not com or n not in spans: continue
            a, b = spans[n]; nb += 1
            srt += [str(nb), "%s --> %s" % (st(a), st(max(b, a + 2))), "Passage %d, %s :" % (n + 1, clean(it.get("nom_passage") or "")),
                    com + (" (%s)" % who if who else ""), ""]
        srt_name = None
        if nb:
            srt_name = name[:-4] + ".commentaires-ESAM.srt"
            try: (d / srt_name).write_text("\n".join(srt), encoding="utf-8")
            except OSError as e: log("Sous-titres non écrits :", e); srt_name = None
        job["resultat"] = {"fichier": name, "largeur": W, "hauteur": H, "duree": round(total, 1),
                           "commentaires": nb, "fichier_commentaires": srt_name,
                           "taille_mo": round((d / name).stat().st_size / 1048576, 1),
                           "chapitres": len(chapters), "fichier_chapitres": chap_name}
        job["libelle"] = "Vidéo enregistrée : " + name
    finally:
        shutil.rmtree(work, ignore_errors=True)

# ---------------------------------------------------------------- réel et story (1080 x 1920)
RW, RH = 1080, 1920
PHOTO_ZOOM = 0.08      # zoom lent sur les photos : +8 % sur la durée de la photo
MUSIC_EXT = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac"}

def crop_box(w, h):
    """Cadre 9:16 le plus grand possible dans l'image source : (largeur, hauteur, course horizontale, y)."""
    if w / h > 9 / 16:
        ch = h - h % 2; cw = int(ch * 9 / 16) // 2 * 2
        return cw, ch, max(0, w - cw), (h - ch) // 2
    cw = w - w % 2; ch = min(h, int(cw * 16 / 9)) // 2 * 2
    return cw, ch, 0, (h - ch) // 2

def key_expr(keys, f, default=0.5):
    """Valeur du champ f (0 à 1) en fonction de t (secondes depuis le début du morceau), lissée entre les points
    (expression ffmpeg ; miroir de rKeyAt dans index.html, même lissage en S)."""
    ks = sorted(({"t": float(k["t"]), "v": min(1.0, max(0.0, float(k[f])))} for k in (keys or [])), key=lambda k: k["t"])
    if not ks: return "%.4f" % default
    e = "%.4f" % ks[-1]["v"]
    for i in range(len(ks) - 2, -1, -1):
        a, b = ks[i], ks[i + 1]
        span = max(0.001, b["t"] - a["t"])
        sm = "clip((t-(%.3f))/%.3f,0,1)" % (a["t"], span)
        e = "if(lt(t,%.3f),%.4f+(%.4f)*%s*%s*(3-2*%s),%s)" % (b["t"], a["v"], b["v"] - a["v"], sm, sm, sm, e)
    return "if(lt(t,%.3f),%.4f,%s)" % (ks[0]["t"], ks[0]["v"], e)

def x_expr(keys, course):
    """Position x du cadre en pixels."""
    if course <= 0: return "0"
    return "(%s)*%d" % (key_expr(keys, "x"), course)

BLUR, FEATHER = 0.1, 0.4   # flous : écart type du flou et largeur du fondu de bord, en fraction de la zone (comme le navigateur)

def blur_mask(work, zs):
    """Masque d'ellipse aux bords fondus (niveaux de gris) pour une zone de zs pixels, fait une fois par taille."""
    out = work / ("masque_%d.png" % zs)
    if not out.exists():
        a = "255*clip((1-hypot((X-W/2)/(W/2),(Y-H/2)/(H/2)))/%g,0,1)" % FEATHER
        run([FFMPEG, "-f", "lavfi", "-i", "color=c=black:s=%dx%d,format=gray" % (zs, zs), "-vf", "geq=lum='%s'" % a, "-frames:v", "1", str(out)])
    return out

def blur_chain(flous, w, h, work, first):
    """Zones de flou suivies, appliquées à l'image source avant le cadrage : (entrées ffmpeg des masques, filtre de [0:v] vers la suite)."""
    fc, last, args = "", "[0:v]", []
    for j, z in enumerate(flous or []):
        zs = max(8, int(float(z.get("s") or 0.2) * h) // 2 * 2)
        if zs > min(w, h): zs = min(w, h) // 2 * 2
        ex = "clip(%s*%d-%d,0,%d)" % (key_expr(z.get("cles"), "x"), w, zs // 2, w - zs)
        ey = "clip(%s*%d-%d,0,%d)" % (key_expr(z.get("cles"), "y"), h, zs // 2, h - zs)
        args += ["-loop", "1", "-i", str(blur_mask(work, zs))]
        fc += ("%ssplit[fa%d][fb%d];[fb%d]crop=%d:%d:x='%s':y='%s',gblur=sigma=%.1f,format=yuva420p[fc%d];[%d:v]format=gray[fm%d];"
               "[fc%d][fm%d]alphamerge[fz%d];[fa%d][fz%d]overlay=x='%s':y='%s':shortest=1[fo%d];") % (
               last, j, j, j, zs, zs, ex, ey, zs * BLUR, j, first + j, j, j, j, j, j, j, ex, ey, j)
        last = "[fo%d]" % j
    return args, fc + last

def story_cuts(total, bounds, limit):
    """Instants de coupe d'une story : morceaux de `limit` secondes au plus, coupés de préférence à une limite de passage (miroir de storyCuts dans index.html)."""
    cuts, last = [0.0], 0.0
    while total - last > limit + 0.01:
        cand = [b for b in bounds if last + 10 < b <= last + limit]
        last = cand[-1] if cand else last + limit - 2
        cuts.append(last)
    cuts.append(total)
    return cuts

def png_from(data, path):
    """Écrit une image envoyée en base64 (data URL) dans un fichier."""
    path.write_bytes(base64.b64decode(data.split(",", 1)[-1]))
    return path

def do_reel(job):
    """Calcul « reel » : passages recadrés en 1080 x 1920 avec flous et cadrage animés, photos, calques PNG, carton de fin, musique ; story découpée sans réencodage."""
    d = folder(job["dossier"]); pl = job["_payload"]
    story = pl.get("mode") == "story"
    segs_in = pl.get("segments") or []
    if not segs_in: raise ValueError("aucun passage")
    srcs = {}
    for sg in segs_in:
        for pc in sg.get("morceaux") or []:
            name = pc["fichier"]
            if name not in srcs:
                f = d / name
                if not f.is_file() or f.parent != d: raise ValueError("rush introuvable : " + name)
                srcs[name] = probe(f)
                if not srcs[name]: raise ValueError("rush illisible : " + name)
    music = None
    if pl.get("musique"):
        mname = clean(pl["musique"].get("fichier") or "")
        if not re.fullmatch(r"musique\.[a-z0-9]{2,4}", mname): raise ValueError("musique invalide")
        music = d / WORK_DIR / mname
        if not music.is_file(): raise ValueError("musique introuvable sur le PC, choisissez-la à nouveau")
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="esam_reel_", dir=str(WORK_ROOT)))
    try:
        # calques dessinés par le navigateur (logo, titre, textes, accéléré) : image plein cadre, plage de temps, fondus
        layers = []
        for i, c in enumerate(pl.get("calques") or []):
            layers.append((png_from(c["image"], work / ("c%03d.png" % i)), float(c["debut"]), float(c["fin"]),
                           float(c.get("fi") or 0), float(c.get("fo") or 0)))
        plan, pos = [], 0.0
        for i, sg in enumerate(segs_in):
            if sg.get("type") == "photo":
                img = png_from(sg["image"], work / ("p%03d.jpg" % i))
                dur = max(0.5, float(sg.get("duree") or 3))
                plan.append(("photo", sg, img, 1.0, pos, dur, i)); pos += dur
                continue
            vit = max(1.0, float(sg.get("vitesse") or 1))
            for pc in sg["morceaux"]:
                src_d = max(0.05, float(pc["fin"]) - float(pc["debut"]))
                plan.append(("clip", pc, None, vit, pos, src_d / vit, i))
                pos += src_d / vit
        clips_end = pos
        if pl.get("fin"):
            fin = png_from(pl["fin"]["image"], work / "fin.png")
            plan.append(("fin", None, fin, 1.0, pos, float(pl["fin"].get("duree") or 3), None))
            pos += float(pl["fin"].get("duree") or 3)
        total = pos
        free = shutil.disk_usage(WORK_ROOT).free
        if free < total * 3e6 + 2e8:
            raise RuntimeError("Espace disque insuffisant dans %s" % WORK_ROOT)
        log("Réel %s : %d segments, %d calques, %.1f s, musique : %s" % (pl.get("nom"), len(plan), len(layers), total, music.name if music else "non"))

        def over(at, dur, first):
            """Calques visibles entre at et at + dur, posés sur [b] : entrées ffmpeg et suite du filtre."""
            args, fc, last, k = [], "", "[b]", 0
            for png, a, b, fi, fo in layers:
                if b <= at + 0.001 or a >= at + dur - 0.001: continue
                s0, e0 = a - at, b - at
                f = "format=rgba"
                if fi and s0 >= 0: f += ",fade=t=in:st=%.3f:d=%.3f:alpha=1" % (s0, fi)
                if fo and e0 - fo >= 0: f += ",fade=t=out:st=%.3f:d=%.3f:alpha=1" % (e0 - fo, fo)
                args += ["-loop", "1", "-framerate", "30", "-i", str(png)]
                fc += ";[%d:v]%s[l%d];%s[l%d]overlay=0:0:shortest=1:enable='gte(t,%.3f)*lt(t,%.3f)'[m%d]" % (first + k, f, k, last, k, max(0.0, s0), e0, k)
                last = "[m%d]" % k; k += 1
            return args, fc + ";%sformat=yuv420p[v]" % last

        files, acc, seg_bounds = [], 0.0, []
        for k, (kind, pc, img, vit, at, dur, idx) in enumerate(plan):
            out = work / ("s%03d.mp4" % k)
            if kind == "fin":
                job["libelle"] = "Carton de fin"
                cmd = [FFMPEG, "-loop", "1", "-framerate", "30", "-i", str(img), "-t", "%.3f" % dur,
                       "-vf", "scale=%d:%d,setsar=1,fps=30,format=yuv420p" % (RW, RH)]
            else:
                if not seg_bounds or seg_bounds[-1][1] != idx: seg_bounds.append((at, idx))
                job["libelle"] = "%s %d sur %d : %s" % ("Photo" if kind == "photo" else "Passage", idx + 1, len(segs_in),
                                                        clean(segs_in[idx].get("nom") or (pc or {}).get("fichier") or ""))
                if kind == "photo":
                    if pc.get("zoom"):
                        n = max(1, int(round(dur * 30)))
                        # agrandie 4 fois avant le zoom lent pour éviter les saccades d'arrondi de zoompan
                        cmd = [FFMPEG, "-i", str(img)]
                        fc = ("[0:v]scale=%d:%d,zoompan=z='1+%.4f*on/%d':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=%d:s=%dx%d:fps=30,setsar=1[b]"
                              % (RW * 4, RH * 4, PHOTO_ZOOM, n, n, RW, RH))
                    else:
                        cmd = [FFMPEG, "-loop", "1", "-framerate", "30", "-i", str(img)]
                        fc = "[0:v]scale=%d:%d,setsar=1,fps=30[b]" % (RW, RH)
                else:
                    info = srcs[pc["fichier"]]
                    cw, ch, course, y = crop_box(info["w"], info["h"])
                    bargs, bfc = blur_chain(pc.get("flous"), info["w"], info["h"], work, 1)
                    fc = bfc + ("crop=w=%d:h=%d:x='%s':y=%d,scale=%d:%d:flags=lanczos,setsar=1,setpts=(PTS-STARTPTS)/%g,fps=30[b]"
                          % (cw, ch, x_expr(pc.get("cles"), course), y, RW, RH, vit))
                    cmd = [FFMPEG, "-hwaccel", "auto", "-ss", "%.3f" % float(pc["debut"]), "-t", "%.3f" % (dur * vit), "-i", str(d / pc["fichier"])] + bargs
                oargs, ofc = over(at, dur, 1 + len(bargs) // 4)
                cmd += oargs + ["-filter_complex", fc + ofc, "-map", "[v]", "-t", "%.3f" % dur]
            cmd += ENC["final"] + ["-g", "60", "-an", "-r", "30", str(out)]
            base = acc
            run(cmd, dur, lambda x: job.__setitem__("avance", 0.9 * (base + x * dur) / total), job)
            if not out.exists() or out.stat().st_size < 1000:
                raise RuntimeError("segment %d vide" % (k + 1))
            files.append(out); acc += dur
        job["libelle"] = "Assemblage"
        lst = work / "liste.txt"
        lst.write_text("".join("file '%s'\n" % f.as_posix() for f in files), encoding="utf-8")
        joined = work / "assemble.mp4"
        run([FFMPEG, "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], None, None, job)
        real = (probe(joined) or {}).get("dur") or total
        final = work / "final.mp4"
        meta_t = ["-metadata", "title=" + clean(pl.get("titre_video") or "ESAM")]
        if music:
            job["libelle"] = "Musique"
            fo = min(2.0, real / 3)
            run([FFMPEG, "-i", str(joined), "-ss", "%.3f" % float(pl["musique"].get("debut") or 0), "-i", str(music),
                 "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                 "-af", "afade=t=in:st=0:d=0.5,afade=t=out:st=%.3f:d=%.3f" % (max(0, real - fo), fo),
                 "-t", "%.3f" % real] + meta_t + ["-movflags", "+faststart", str(final)], real, None, job)
        else:
            run([FFMPEG, "-i", str(joined), "-c", "copy"] + meta_t + ["-movflags", "+faststart", str(final)], None, None, job)
        base_name = re.sub(r'[\\/:*?"<>|]', "_", clean(pl.get("nom") or ("ESAM_Story" if story else "ESAM_Reel")))
        outs = []
        if story:
            bounds = [b for b, _ in seg_bounds] + [clips_end]
            cuts = story_cuts(real, bounds, float(pl.get("story_max") or 60))
            n = len(cuts) - 1
            for i in range(n):
                a, b = cuts[i], cuts[i + 1]
                job["libelle"] = "Story %d sur %d" % (i + 1, n)
                part = work / ("story%02d.mp4" % i)
                # coupe sans réencodage : les coupures tombent au début d'un passage, donc sur une image clé
                run([FFMPEG, "-ss", "%.3f" % a, "-i", str(final), "-t", "%.3f" % (b - a), "-map", "0", "-c", "copy",
                     "-avoid_negative_ts", "make_zero"] + meta_t + ["-movflags", "+faststart", str(part)], None, None, job)
                job["avance"] = 0.9 + 0.08 * (i + 1) / n
                outs.append((part, base_name + ("_%dsur%d.mp4" % (i + 1, n) if n > 1 else ".mp4")))
        else:
            outs.append((final, base_name + ".mp4"))
        job["libelle"] = "Copie dans le Drive"
        names, size = [], 0
        for src, name in outs:
            part = d / (name + ".partiel")
            try:
                shutil.copyfile(str(src), str(part))
                if part.stat().st_size != src.stat().st_size: raise RuntimeError("copie incomplète")
                os.replace(str(part), str(d / name))
            except Exception as e:
                try: part.unlink()
                except OSError: pass
                keep = WORK_ROOT / name
                shutil.copyfile(str(src), str(keep))
                raise RuntimeError("copie dans le Drive impossible (%s). La vidéo est gardée sur le PC : %s" % (e, keep))
            names.append(name); size += (d / name).stat().st_size
        job["resultat"] = {"fichiers": names, "largeur": RW, "hauteur": RH, "duree": round(real, 1),
                           "taille_mo": round(size / 1048576, 1), "musique": bool(music)}
        job["libelle"] = "Enregistré : " + ", ".join(names)
    finally:
        shutil.rmtree(work, ignore_errors=True)

def photo(d, name, t):
    """Extrait une image pleine résolution d'un rush à l'instant t, dans le sous-dossier Photos."""
    f = d / name
    if not f.is_file() or f.parent != d: raise ValueError("rush introuvable")
    out_dir = d / "Photos"; out_dir.mkdir(exist_ok=True)
    stem = "ESAM_" + slug(Path(name).stem) + "_" + ("%07.1f" % t).replace(".", "s")
    out = out_dir / (stem + ".jpg")
    run([FFMPEG, "-ss", "%.3f" % t, "-i", str(f), "-frames:v", "1", "-q:v", "2", str(out)])
    return out

# ---------------------------------------------------------------- veille Windows
def keep_awake(on):
    """Empêche (ou autorise à nouveau) la mise en veille de Windows pendant un calcul."""
    if not WIN: return
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))

def user_idle_seconds():
    """Secondes écoulées depuis la dernière action clavier ou souris sur le PC (Windows)."""
    if not WIN: return 1e9
    import ctypes
    class LII(ctypes.Structure): _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    lii = LII(); lii.cbSize = ctypes.sizeof(LII)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0

def idle_watch():
    """Fil qui met le PC en veille ou l'arrête après `veille_apres_minutes` sans calcul, sans appli et sans utilisateur."""
    while True:
        time.sleep(30)
        if IDLE_MODE == "aucun" or not WIN: continue
        with JLOCK: busy = bool(QUEUE) or any(j["etat"] == "en_cours" for j in JOBS)
        idle = min(time.time() - LAST_ACTIVITY[0], user_idle_seconds())
        if busy or idle < IDLE_MIN * 60: continue
        log("Inactif depuis %d min : %s" % (IDLE_MIN, IDLE_MODE))
        LAST_ACTIVITY[0] = time.time()
        if IDLE_MODE == "arret":
            subprocess.run(["shutdown", "/s", "/t", "60", "/c", "Dérushage ESAM : arrêt après inactivité"], creationflags=NOWIN)
        else:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Add-Type -Assembly System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend',$false,$false)"],
                           creationflags=NOWIN)

# ---------------------------------------------------------------- HTTP
class H(BaseHTTPRequestHandler):
    server_version = "ESAMDerushage/" + VERSION
    def log_message(self, *a): pass

    def send_json(self, obj, code=200):
        """Réponse JSON (UTF-8, non mise en cache)."""
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers()
        self.wfile.write(b)

    def body(self):
        """Corps JSON de la requête, ou {} s'il est vide."""
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}

    def do_GET(self):
        """Routes de lecture : page, état du serveur, interventions, manifeste, images, état de dérushage, fichiers des rushs, vendor."""
        LAST_ACTIVITY[0] = time.time()
        u = urllib.parse.urlparse(self.path); q = dict(urllib.parse.parse_qsl(u.query))
        try:
            if u.path in ("/", "/index.html"): return self.send_file(HERE / "index.html")
            if u.path.startswith("/vendor/"):
                name = u.path[len("/vendor/"):]
                if not re.fullmatch(r"[A-Za-z0-9._-]+", name): return self.send_error(400)
                return self.send_file(HERE / "vendor" / name)
            if u.path == "/api/status":
                with JLOCK: jobs = [public(j) for j in JOBS]
                return self.send_json({"ok": True, "version": VERSION, "racine": str(ROOT), "racine_ok": ROOT.is_dir(), "gpu": ENC.get("gpu"),
                                       "travaux": jobs, "veille": {"mode": IDLE_MODE, "minutes": IDLE_MIN}})
            if u.path == "/api/interventions": return self.send_json({"interventions": list_interventions()})
            if u.path == "/api/manifest": return self.send_json(manifest(folder(q.get("d"))))
            if u.path == "/api/image": return self.send_file(photo_copy(folder(q.get("d")), q.get("f"), q.get("taille")))
            if u.path == "/api/etat":
                p = folder(q.get("d")) / WORK_DIR / "etat.json"
                return self.send_json(json.loads(p.read_text(encoding="utf-8")) if p.exists() else {})
            if u.path.startswith("/files/"):
                parts = [urllib.parse.unquote(x) for x in u.path[len("/files/"):].split("/")]
                if any(x in ("", ".", "..") for x in parts): return self.send_error(400)
                p = (ROOT.joinpath(*parts)).resolve()
                if ROOT.resolve() not in p.parents: return self.send_error(403)
                return self.send_file(p)
            self.send_error(404)
        except ValueError as e: self.send_json({"erreur": str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError): pass

    def do_POST(self):
        """Routes d'écriture : musique (fichier brut), lancement et annulation des calculs, état de dérushage, fiche, photo."""
        LAST_ACTIVITY[0] = time.time()
        u = urllib.parse.urlparse(self.path)
        try:
            if u.path == "/api/musique":      # fichier brut, pas du JSON
                q = dict(urllib.parse.parse_qsl(u.query))
                d = folder(q.get("d")); n = int(self.headers.get("Content-Length") or 0)
                ext = Path(clean(q.get("nom") or "")).suffix.lower()
                if ext not in MUSIC_EXT: raise ValueError("format de musique non pris en charge (mp3, m4a, aac, wav, ogg, flac)")
                if n <= 0 or n > 60 * 1048576: raise ValueError("fichier vide ou trop lourd (60 Mo maximum)")
                w = d / WORK_DIR; w.mkdir(exist_ok=True)
                tmp = w / "musique.tmp"
                with open(tmp, "wb") as f:
                    left = n
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk: break
                        f.write(chunk); left -= len(chunk)
                if left > 0: tmp.unlink(); raise ValueError("envoi incomplet")
                for old in w.glob("musique.*"):
                    if old.name != "musique.tmp": old.unlink()
                os.replace(tmp, w / ("musique" + ext))
                return self.send_json({"ok": True, "fichier": "musique" + ext})
            b = self.body()
            if u.path == "/api/proxies":
                d = folder(b.get("d"))
                with JLOCK:
                    j = next((x for x in JOBS if x["dossier"] == d.name and x["type"] == "proxies" and x["etat"] in ("attente", "en_cours")), None)
                return self.send_json(public(j or new_job("proxies", d)))
            if u.path == "/api/video": return self.send_json(public(new_job("video", folder(b.get("d")), b)))
            if u.path == "/api/reel": return self.send_json(public(new_job("reel", folder(b.get("d")), b)))
            if u.path == "/api/annuler":
                with JLOCK: j = next((x for x in JOBS if x["id"] == b.get("id")), None)
                if j:
                    j["cancel"] = True
                    if j["etat"] == "attente":
                        with JLOCK:
                            if j in QUEUE: QUEUE.remove(j)
                        j["etat"] = "annule"
                return self.send_json({"ok": bool(j)})
            if u.path == "/api/etat":
                d = folder(b.get("d")); w = d / WORK_DIR; w.mkdir(exist_ok=True)
                tmp = w / "etat.tmp"; tmp.write_text(json.dumps(b.get("etat", {}), ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, w / "etat.json")
                return self.send_json({"ok": True})
            if u.path == "/api/fiche":
                d = folder(b.get("d"))
                name = re.sub(r'[\\/:*?"<>|]', "_", clean(b.get("nom") or "ESAM_Derushage.md"))
                for old in d.glob("ESAM_Derushage_*.md"):
                    if old.name != name: old.unlink()     # une seule fiche vivante par intervention
                (d / name).write_text(clean(b.get("md", "")), encoding="utf-8")
                return self.send_json({"ok": True, "fichier": name})
            if u.path == "/api/photo":
                out = photo(folder(b.get("d")), b.get("fichier"), float(b.get("t", 0)))
                return self.send_json({"ok": True, "fichier": "Photos/" + out.name})
            self.send_error(404)
        except ValueError as e: self.send_json({"erreur": str(e)}, 400)
        except Exception as e:
            log("ERREUR", u.path, traceback.format_exc()); self.send_json({"erreur": clean(str(e))[:300]}, 500)

    def send_file(self, p):
        """Envoie un fichier avec son type MIME, les requêtes Range (lecture vidéo) et un cache d'une heure sauf pour la page."""
        if not p.is_file(): return self.send_error(404)
        size = p.stat().st_size
        ctype = {".html": "text/html; charset=utf-8", ".mp4": "video/mp4", ".jpg": "image/jpeg", ".json": "application/json",
                 ".md": "text/markdown; charset=utf-8", ".png": "image/png", ".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2",
                 ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".wav": "audio/wav", ".ogg": "audio/ogg", ".flac": "audio/flac"}.get(p.suffix.lower(), "application/octet-stream")
        rng = self.headers.get("Range"); a, z = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
        if m:
            if m.group(1): a = int(m.group(1)); z = int(m.group(2)) if m.group(2) else size - 1
            else: a = max(0, size - int(m.group(2)))
            z = min(z, size - 1)
            if a > z: self.send_response(416); self.send_header("Content-Range", "bytes */%d" % size); self.end_headers(); return
            self.send_response(206); self.send_header("Content-Range", "bytes %d-%d/%d" % (a, z, size))
        else: self.send_response(200)
        self.send_header("Content-Type", ctype); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(z - a + 1))
        self.send_header("Cache-Control", "no-store" if p.suffix == ".html" else "private, max-age=3600")
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(a); left = z - a + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk: break
                self.wfile.write(chunk); left -= len(chunk)

def main():
    """Démarre le serveur : encodeurs, historique des calculs, fil de calcul, fil de veille, HTTP."""
    if not shutil.which("ffmpeg"): log("ATTENTION : ffmpeg introuvable dans le PATH")
    if not ROOT.is_dir(): log("ATTENTION : dossier des rushs introuvable :", ROOT)
    detect_encoders()
    load_jobs()
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=idle_watch, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), H)
    log("Dérushage ESAM v" + VERSION + " prêt sur http://%s:%d  (rushs : %s)" % (HOST, PORT, ROOT))
    srv.serve_forever()

if __name__ == "__main__":
    main()
