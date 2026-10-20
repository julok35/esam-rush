#!/usr/bin/env python3
"""ESAM - Serveur local de dérushage drone.

Tourne sur le PC Windows qui synchronise le Drive ESAM (Google Drive pour ordinateur).
Sert l'appli de dérushage et exécute les traitements vidéo avec ffmpeg :
proxies 540p + vignettes, photos pleine résolution, vidéo compilée en résolution d'origine.

Dépendances : Python 3.10+ (bibliothèque standard uniquement) et ffmpeg/ffprobe dans le PATH.
Écoute uniquement sur 127.0.0.1 : l'accès depuis le téléphone passe par « tailscale serve ».
"""
import base64, json, math, os, re, shutil, subprocess, sys, tempfile, threading, time, traceback, unicodedata, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

VERSION = "0.8.1"
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
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")
    except Exception: pass
    print(line, flush=True)

def clean(s):  # règle typographique ESAM : pas de tiret long
    return str(s).replace("\u2014", "-").replace("\u2013", "-")

def slug(s):
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
            from datetime import datetime
            created = datetime.fromisoformat(ct.replace("Z", "+00:00")).timestamp()
            if created < 1.2e9: created = None
        except ValueError: pass
    return {"w": w, "h": h, "dur": dur, "codec": vs.get("codec_name"), "created": created}

ENC = {}
def detect_encoders():
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
    name = clean(name or "")
    if not name or "/" in name or "\\" in name or name.startswith(".") or ".." in name:
        raise ValueError("dossier invalide")
    p = ROOT / name
    if not p.is_dir(): raise ValueError("dossier introuvable : " + name)
    return p

def videos(d):
    return sorted(f for f in d.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXT and not f.name.startswith(("ESAM_Compilation", ".")))

def proxy_of(f): return f.parent / PROXY_DIR / (f.stem + ".mp4")

def list_interventions():
    out = []
    if not ROOT.is_dir(): return out
    for d in ROOT.iterdir():
        if not d.is_dir() or d.name.startswith((".", "_")): continue
        try:
            vids = videos(d)
            done = sum(1 for f in vids if (d / PROXY_DIR / (f.stem + ".json")).exists())
            out.append({"nom": d.name, "videos": len(vids), "proxies": done,
                        "fiche": any(x.name.startswith("ESAM_Derushage") for x in d.iterdir()),
                        "compilation": any(x.name.startswith("ESAM_Compilation") for x in d.iterdir()),
                        "maj": d.stat().st_mtime})
        except OSError as e:
            log("Lecture impossible", d, e)
    out.sort(key=lambda x: -x["maj"])
    return out

def manifest(d):
    clips = []
    for f in videos(d):
        meta_p = d / PROXY_DIR / (f.stem + ".json")
        if not meta_p.exists(): continue
        m = json.loads(meta_p.read_text(encoding="utf-8"))
        rel = lambda p: "files/" + urllib.parse.quote(d.name) + "/" + urllib.parse.quote(PROXY_DIR) + "/" + urllib.parse.quote(p)
        m["proxy"] = rel(f.stem + ".mp4")
        m["thumbs"]["sheets"] = [rel(s) for s in m["thumbs"]["sheets"]]
        clips.append(m)
    return {"dossier": d.name, "clips": clips}

# ---------------------------------------------------------------- travaux
JOBS, JLOCK, QUEUE = [], threading.Lock(), []
QCOND = threading.Condition(JLOCK)
LAST_ACTIVITY = [time.time()]

def new_job(kind, d, payload=None):
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
    try:
        with JLOCK: data = [public(j) for j in JOBS]
        with SAVE_LOCK:  # deux threads ne doivent pas ecrire le meme fichier temporaire
            tmp = JOBS_FILE.with_suffix(".tmp"); tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, JOBS_FILE)
    except Exception as e: log("Sauvegarde des travaux impossible :", e)

def load_jobs():
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
        # commentaires internes : fichier de sous-titres à part, jamais incrusté dans la vidéo
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

def photo(d, name, t):
    f = d / name
    if not f.is_file() or f.parent != d: raise ValueError("rush introuvable")
    out_dir = d / "Photos"; out_dir.mkdir(exist_ok=True)
    stem = "ESAM_" + slug(Path(name).stem) + "_" + ("%07.1f" % t).replace(".", "s")
    out = out_dir / (stem + ".jpg")
    run([FFMPEG, "-ss", "%.3f" % t, "-i", str(f), "-frames:v", "1", "-q:v", "2", str(out)])
    return out

# ---------------------------------------------------------------- veille Windows
def keep_awake(on):
    if not WIN: return
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))

def user_idle_seconds():
    if not WIN: return 1e9
    import ctypes
    class LII(ctypes.Structure): _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    lii = LII(); lii.cbSize = ctypes.sizeof(LII)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0

def idle_watch():
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
    server_version = "ESAMDerushage/1.0"
    def log_message(self, *a): pass

    def send_json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers()
        self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}

    def do_GET(self):
        LAST_ACTIVITY[0] = time.time()
        u = urllib.parse.urlparse(self.path); q = dict(urllib.parse.parse_qsl(u.query))
        try:
            if u.path in ("/", "/index.html"): return self.send_file(HERE / "index.html")
            if u.path == "/api/status":
                with JLOCK: jobs = [public(j) for j in JOBS]
                return self.send_json({"ok": True, "version": VERSION, "racine": str(ROOT), "racine_ok": ROOT.is_dir(), "gpu": ENC.get("gpu"),
                                       "travaux": jobs, "veille": {"mode": IDLE_MODE, "minutes": IDLE_MIN}})
            if u.path == "/api/interventions": return self.send_json({"interventions": list_interventions()})
            if u.path == "/api/manifest": return self.send_json(manifest(folder(q.get("d"))))
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
        LAST_ACTIVITY[0] = time.time()
        u = urllib.parse.urlparse(self.path)
        try:
            b = self.body()
            if u.path == "/api/proxies":
                d = folder(b.get("d"))
                with JLOCK:
                    j = next((x for x in JOBS if x["dossier"] == d.name and x["type"] == "proxies" and x["etat"] in ("attente", "en_cours")), None)
                return self.send_json(public(j or new_job("proxies", d)))
            if u.path == "/api/video": return self.send_json(public(new_job("video", folder(b.get("d")), b)))
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
        if not p.is_file(): return self.send_error(404)
        size = p.stat().st_size
        ctype = {".html": "text/html; charset=utf-8", ".mp4": "video/mp4", ".jpg": "image/jpeg", ".json": "application/json",
                 ".md": "text/markdown; charset=utf-8", ".png": "image/png"}.get(p.suffix.lower(), "application/octet-stream")
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
