"""Tests unitaires : fonctions pures de server.py, et calculs en miroir entre l'appli et le serveur.

Usage : python tests/test_unitaire.py
Sans dépendance pour la partie serveur ; la comparaison storyCuts (index.html) / story_cuts (server.py)
demande Playwright (pip install playwright ; playwright install chromium) et est sautée sinon.
Le serveur est importé avec une configuration temporaire (variable ESAM_CONFIG) : config.json n'est pas touché.
"""
import json, os, shutil, struct, subprocess, sys, tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent; RACINE = ICI.parent
TMP = Path(tempfile.mkdtemp(prefix="esam_unit_"))
cfg = json.loads((RACINE / "config.exemple.json").read_text(encoding="utf-8")); cfg["dossier_rushs"] = str(TMP / "rushs")
(TMP / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
os.environ["ESAM_CONFIG"] = str(TMP / "config.json")
sys.path.insert(0, str(RACINE))
import server  # noqa: E402

def test_clean_slug():
    assert server.clean("a \u2014 b \u2013 c") == "a - b - c"   # tirets longs écrits en échappement
    assert server.slug("Chien égaré, combe de Lancey !") == "Chien_egare_combe_de_Lancey"
    assert len(server.slug("x" * 100)) == 40

def test_folder_refuse_les_chemins():
    (TMP / "rushs" / "2026-09-12 Test").mkdir(parents=True, exist_ok=True)
    assert server.folder("2026-09-12 Test").name == "2026-09-12 Test"
    for mauvais in ("../x", "a/b", "a\\b", ".cache", "", "inexistant"):
        try: server.folder(mauvais)
        except ValueError: continue
        raise AssertionError("accepté : %r" % mauvais)

def test_crop_box():
    # (largeur, hauteur, course horizontale, course verticale) ; zoom 1 : le plus grand cadre au format dans l'image
    assert server.crop_box(1920, 1080) == (608, 1080, 1312, 0)       # 16:9 : cadre plein hauteur, course horizontale
    assert server.crop_box(1080, 1920) == (1080, 1920, 0, 0)        # déjà vertical
    assert server.crop_box(1000, 1000) == (562, 1000, 438, 0)        # carré : cadre plein hauteur, course de 438 px
    assert server.crop_box(1920, 1080, 1080, 1350) == (864, 1080, 1056, 0)   # LinkedIn 4:5 dans du 16:9
    assert server.crop_box(1920, 1080, 1080, 1080) == (1080, 1080, 840, 0)   # LinkedIn carré dans du 16:9
    assert server.crop_box(1080, 1920, 1080, 1350) == (1080, 1350, 0, 570)   # 4:5 dans une vidéo de téléphone : course verticale
    # cadre libre : zoom (cadre plus petit, course dans les deux sens), image entière (cadre plus grand que l'image : course négative)
    assert server.crop_box(1080, 1920, 1080, 1350, 2) == (540, 676, 540, 1244)
    assert server.crop_box(1080, 1920, 1080, 1350, 9) == server.crop_box(1080, 1920, 1080, 1350, 4)      # zoom 4 au plus
    assert server.crop_box(1920, 1080, 9, 16, 0) == (1920, 3414, 0, -2334)       # image entière d'un 16:9 en 9:16
    assert server.crop_box(1080, 1920, 1080, 1080, 0) == (1920, 1920, -840, 0)   # image entière d'un téléphone en carré

def test_frame_chain():
    """Mise au format d'un morceau : un filtre que ffmpeg accepte dans les trois cas (zoom fixe, débord, zoom qui varie),
    avec ou sans points d'avant le cadre libre ({t, x} seuls)."""
    cas = [([{"t": 0, "x": 0.2}, {"t": 1, "x": 0.8}], "crop=w=608:h=1080"),
           ([{"t": 0, "x": 0.5, "y": 0.2, "z": 1.5}], "crop=w="),
           ([{"t": 0, "x": 0.5, "y": 0.5, "z": 0}], "overlay=x="),
           ([{"t": 0, "x": 0.5, "y": 0.5, "z": 0.4}, {"t": 1, "x": 0.3, "y": 0.6, "z": 3}], "zoompan=")]
    for cles, attendu in cas:
        mise, fx, fy, hs = server.frame_chain(1920, 1080, cles, 1080, 1920, 1.5)
        assert attendu in mise, (cles, mise[:200])
        assert hs > 0 and "*" in fx("(0.5)") and "*" in fy("(0.5)")
    mise = server.frame_chain(1920, 1080, [], 1080, 1920, 1)[0]
    assert mise.startswith("crop=w=608:h=1080:x='(0.5000)*(1312)':y='0'"), mise       # sans cadrage : cadre centré, comme avant
    if not shutil.which("ffmpeg"):
        print("  (ffmpeg absent : filtres de cadrage non lancés)"); return
    src = TMP / "portrait.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=180x320:rate=30:duration=1.5", "-pix_fmt", "yuv420p", str(src)], check=True)
    for fmt in ("li", "carre"):
        rw, rh = server.REEL_FMTS[fmt]
        for cles, _ in cas:
            mise, fx, fy, hs = server.frame_chain(180, 320, cles, rw, rh, 1.5)
            out = TMP / "cadre.mp4"
            r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", "[0:v]" + mise + ",setpts=PTS-STARTPTS,fps=30[v]",
                                "-map", "[v]", "-t", "1.5", "-c:v", "libx264", "-preset", "ultrafast", str(out)], capture_output=True, text=True)
            assert r.returncode == 0, (fmt, cles, r.stderr[-500:])
            i = server.probe(out); assert (i["w"], i["h"]) == (rw, rh), (fmt, cles, i)

def test_key_expr():
    assert server.key_expr([], "x") == "(0.5000)"
    assert server.key_expr([{"t": 2, "x": 0.25}], "x") == "(0.2500)"
    e = server.key_expr([{"t": 0, "x": 0}, {"t": 4, "x": 1}], "x")
    assert e == "(0.0000+(1.0000)*clip((t-(0.000))/4.000,0,1)*clip((t-(0.000))/4.000,0,1)*(3-2*clip((t-(0.000))/4.000,0,1)))", e
    assert server.key_expr([{"t": 0, "x": 0.3}, {"t": 4, "x": 0.3}], "x") == "(0.3000)"      # intervalle sans mouvement : aucun terme

def ffexpr(e, t):
    """Évalue une expression ffmpeg de key_expr à l'instant t."""
    return eval(e, {"__builtins__": {}}, {"t": t, "clip": lambda x, a, b: max(a, min(b, x))})

def test_zone_box_et_masques():
    assert server.zone_box({"s": 0.2}, 1920, 1080) == (216, 216)                      # carré : comme avant la v0.17
    assert server.zone_box({"s": 0.1, "ar": 2.5}, 1920, 1080) == (270, 108)           # plaque : plus large que haute
    assert server.zone_box({"s": 0.9, "ar": 4}, 640, 360) == (640, 324)               # bornée à l'image
    assert server.speed_of({"vitesse": 0.5}) == 0.5 and server.speed_of({}) == 1.0 and server.speed_of({"vitesse": 99}) == 16.0
    assert server.speed_of({}, 4) == 4.0 and server.speed_of({"vitesse": "x"}) == 1.0

def test_sources():
    assert server.is_source("DJI_20260912143005_0001_W.MP4") and not server.is_source("ESAM_Compilation_2026-09-12_Test.mp4")
    assert not server.is_source("ESAM_Extraits_2026-09-12_Test_01_Bonne_piste.mp4") and not server.is_source("notes.txt")
    assert server.is_source("ESAM_Compilation_2026-09-12_Test.mp4", "compil") and server.is_source("ESAM_Extraits_x.mp4", "compil")
    assert not server.is_source("ESAM_Reel_2026-09-12_Test.mp4", "compil") and not server.is_source("ESAM_LinkedIn_2026-09-12_Test_carre.mp4") and not server.is_source("DJI_20260912143005_0001_W.MP4", "compil")
    d = TMP / "rushs" / "2026-09-12 Test"; d.mkdir(parents=True, exist_ok=True)
    assert server.etat_file(d).name == "etat.json" and server.etat_file(d, "compil").name == "etat-compil.json"

def test_chaines_de_filtres():
    """Flous et formes : le filtre produit garde le bon nombre d'entrées et d'étiquettes (sans lancer ffmpeg pour les formes)."""
    args, fc = server.shape_chain([{"image": "a", "ref": 2160, "ax": 100, "ay": 50, "cles": [{"t": 0, "x": 0.5, "y": 0.5}], "debut": 1, "fin": 3},
                                   {"image": "absente", "cles": []}], {"a": Path("a.png")}, 2, lambda e: e + "*1920", lambda e: e + "*1080", 1080)
    assert args == ["-i", "a.png"] and "[2:v]scale=w='max(2,iw*0.50000)'" in fc and "overlay=x='(0.5000)*1920-(50.00)':y='(0.5000)*1080-(25.00)'" in fc
    assert "enable='between(t,1.000,3.000)'" in fc and fc.startswith("[sa0];") and not fc.endswith("]")
    assert server.shape_chain([], {}, 1, None, None, 1080) == ([], "")

def test_story_cuts():
    assert server.story_cuts(50, [0, 20, 40], 60) == [0, 50]
    assert server.story_cuts(100, [0, 30, 55, 70], 60) == [0, 55, 100]     # coupe à la limite de passage la plus tardive sous 60 s
    assert server.story_cuts(130, [0, 5], 60) == [0, 58, 116, 130]          # sans limite utile : 60 - 2 s
    for c in server.story_cuts(500, [0, 50, 120, 170, 250, 300, 333, 400, 470], 60):
        assert c <= 500

def test_jpeg_orientation():
    def jpeg(orientation):
        # JPEG minimal : SOI, APP1 Exif avec un seul tag Orientation (0x0112), puis SOS
        ifd = struct.pack(">HHHII", 1, 0x0112, 3, 1, orientation << 16) + b"\0\0\0\0"
        tiff = b"MM\0\x2a" + struct.pack(">I", 8) + ifd
        app1 = b"Exif\0\0" + tiff
        return b"\xff\xd8" + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + b"\xff\xda"
    for o in (1, 3, 6, 8):
        p = TMP / ("o%d.jpg" % o); p.write_bytes(jpeg(o))
        assert server.jpeg_orientation(p) == o, o
    p = TMP / "sans.jpg"; p.write_bytes(b"\xff\xd8\xff\xda"); assert server.jpeg_orientation(p) == 1
    p = TMP / "pas.jpg"; p.write_bytes(b"PNG"); assert server.jpeg_orientation(p) == 1

def test_key_at():
    """key_at (lissage côté serveur, pour la toile du zoom) suit key_expr ; un point sans le champ prend la valeur par défaut."""
    keys = [{"t": 0.5, "x": 0.2, "z": 1}, {"t": 2.0, "x": 0.9, "z": 3}, {"t": 3.0, "x": 0.4}]
    for t in (0, 0.5, 1.1, 2.0, 2.4, 3.0, 5):
        assert abs(server.key_at(keys, t, "x") - ffexpr(server.key_expr(keys, "x"), t)) < 0.0006, t
        assert abs(server.key_at(keys, t, "z", 1) - ffexpr(server.key_expr(keys, "z", 1, "t", 0, 4), t)) < 0.0006, t
    assert "it-(" in server.key_expr(keys, "x", 0.5, "it")

def test_miroir_lissage():
    """rKeyAt (index.html) et key_expr (server.py) donnent la même position entre les points de suivi."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  (Playwright absent : miroir rKeyAt non vérifié)"); return
    keys = [{"t": 0.5, "x": 0.2, "y": 0.8}, {"t": 1.2, "x": 0.35, "y": 0.8}, {"t": 3.0, "x": 0.9, "y": 0.1}, {"t": 3.2, "x": 0.85, "y": 0.4}]
    temps = [-1, 0, 0.5, 0.7, 1.19, 1.2, 2.0, 2.9, 3.1, 3.2, 8]
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.goto((RACINE / "index.html").as_uri())
        for f in ("x", "y"):
            e = server.key_expr(keys, f)
            for t in temps:
                js = pg.evaluate("([k, t, f]) => window.ESAM_TEST.keyAt(k, t, f)", [keys, t, f])
                assert abs(js - ffexpr(e, t)) < 0.0006, (f, t, js, ffexpr(e, t))
        b.close()

def test_miroir_cadre():
    """rCrop (index.html) et crop_box (server.py) donnent le même cadre pour chaque format (à l'arrondi pair près),
    au zoom 1 comme en cadre libre : vidéo de téléphone en portrait, zoom, image entière, place verticale."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  (Playwright absent : miroir rCrop non vérifié)"); return
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.goto((RACINE / "index.html").as_uri())
        for fmt, (rw, rh) in server.REEL_FMTS.items():
            for sw, sh in ((1920, 1080), (3840, 2160), (640, 512), (1080, 1920), (1000, 1000)):
                for x, y, z in ((1, 0.5, 1), (0.3, 0.2, 2.5), (0.5, 0.9, 1.4), (0.5, 0.5, 0), (0.1, 0.7, 0.6), (0, 1, 9)):
                    js = pg.evaluate("([f, w, h, x, y, z]) => window.ESAM_TEST.crop(f, w, h, x, y, z)", [fmt, sw, sh, x, y, z])
                    cw, ch, cx, cy = server.crop_box(sw, sh, rw, rh, z)
                    ok = (abs(js["cw"] - cw) <= 2 and abs(js["ch"] - ch) <= 2 and abs(js["free"] - cx) <= 2 and abs(js["freeY"] - cy) <= 2
                          and abs(js["sx"] - cx * x) <= 2 and abs(js["sy"] - cy * y) <= 2)
                    assert ok, (fmt, sw, sh, x, y, z, js, (cw, ch, cx, cy))
        b.close()

COULEURS = [{}, {"lum": 20}, {"con": -40}, {"sat": 60}, {"sat": -100}, {"temp": 50}, {"temp": -70},
            {"lum": 20, "con": -15, "sat": 10, "temp": 5}, {"lum": -35, "con": 80, "sat": -30, "temp": -100},
            {"lum": 100, "con": 100, "sat": 100, "temp": 100}, {"lum": "12.5", "con": None, "sat": 300}]
PIXELS = [[0, 0, 0], [255, 255, 255], [128, 128, 128], [30, 30, 30], [220, 220, 220], [200, 40, 30], [20, 160, 60],
          [40, 70, 210], [250, 240, 30], [90, 120, 140], [180, 150, 120], [10, 200, 250], [64, 64, 200], [127, 128, 129]]

def ref_pix(p, q):
    """Modèle des couleurs écrit à part (fxColPix dans index.html, color_chain dans server.py) : un pixel de 0 à 255."""
    cl = lambda x: min(1.0, max(0.0, x))
    r, g, b = (cl((cl(cl(v / 255 * gn) * p["b"]) - 0.5) * p["c"] + 0.5) for v, gn in zip(q, (p["gr"], p["gg"], p["gb"])))
    s = p["s"]
    r, g, b = (cl((0.213 + 0.787 * s) * r + (0.715 - 0.715 * s) * g + (0.072 - 0.072 * s) * b),
               cl((0.213 - 0.213 * s) * r + (0.715 + 0.285 * s) * g + (0.072 - 0.072 * s) * b),
               cl((0.213 - 0.213 * s) * r + (0.715 - 0.715 * s) * g + (0.072 + 0.928 * s) * b))
    return [round(r * 255), round(g * 255), round(b * 255)]

def ffmpeg_pix(c, px):
    """Pixels passés par le filtre de color_chain dans ffmpeg (image RGB d'une ligne, sans passage par le YUV)."""
    import subprocess
    f = server.color_chain(c) or "null"
    raw = bytes(v for q in px for v in q)
    out = subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx1" % len(px), "-i", "-",
                          "-vf", f, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], input=raw, capture_output=True, check=True).stdout
    return [list(out[i * 3:i * 3 + 3]) for i in range(len(px))]

def test_couleurs_serveur():
    assert server.color_chain({}) == "" and server.color_chain(None) == "" and server.color_chain({"lum": 0.4}) == ""
    assert server.color_params({"lum": 20, "con": -15, "sat": 10, "temp": 5}) == {"b": 1.1, "c": 0.925, "s": 1.1, "gr": 1, "gg": 0.997, "gb": 0.99}
    assert "colorchannelmixer" not in server.color_chain({"lum": 30}) and "colorchannelmixer" in server.color_chain({"sat": 30})
    args, fc = server.blur_chain([], 1920, 1080, TMP, 1, {"lum": 30})
    assert args == [] and fc.startswith("[0:v]format=gbrp,lutrgb=") and fc.endswith("[cc];[cc]"), fc
    assert server.blur_chain([], 1920, 1080, TMP, 1, {}) == ([], "[0:v]")
    # retour au YUV avec la matrice de la source : une vidéo BT.709 presque inchangée garde ses teintes
    import re, subprocess
    src = TMP / "bt709.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=0.2", "-vf", "scale=out_color_matrix=bt709,format=yuv420p",
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-c:v", "libx264", "-qp", "0", str(src)], check=True)
    info = server.probe(src); assert info["matrice"] == "bt709", info
    _, fc = server.blur_chain([], info["w"], info["h"], TMP, 1, {"lum": 1}, info)
    assert "out_color_matrix=bt709:out_range=tv" in fc, fc
    r = subprocess.run(["ffmpeg", "-i", str(src), "-i", str(src), "-filter_complex", fc + "null[o];[o][1:v]psnr", "-f", "null", "-"], capture_output=True, text=True).stderr
    psnr = float(re.findall(r"average:([0-9.]+)", r)[-1]); assert psnr > 35, psnr
    for c in COULEURS:            # le filtre ffmpeg suit le modèle à l'arrondi près
        p = server.color_params(c)
        for q, o in zip(PIXELS, ffmpeg_pix(c, PIXELS)):
            assert max(abs(a - b) for a, b in zip(o, ref_pix(p, q))) <= 2, (c, q, o, ref_pix(p, q))

def test_miroir_couleurs():
    """fxColParams (index.html) et color_params (server.py) donnent les mêmes paramètres ; le canevas (ctx.filter, et le
    calcul pixel par pixel des navigateurs sans ctx.filter) donne les mêmes pixels que ffmpeg."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  (Playwright absent : miroir des couleurs non vérifié)"); return
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.goto((RACINE / "index.html").as_uri())
        for c in COULEURS:
            js = pg.evaluate("c => window.ESAM_TEST.colParams(c)", c)
            assert js == server.color_params(c), (c, js, server.color_params(c))
            ff = ffmpeg_pix(c, PIXELS)
            for pix in (False, True):
                cv = pg.evaluate("([c, px, pix]) => window.ESAM_TEST.colCanvas(c, px, pix)", [c, PIXELS, pix])
                for q, o, f in zip(PIXELS, cv, ff):
                    assert max(abs(a - b) for a, b in zip(o, f)) <= 3 and o[3] == 255, (c, pix, q, o, f)
        # seule l'image source change : une bande (ici les 3 premiers pixels) reste telle quelle et opaque
        for pix in (False, True):
            cv = pg.evaluate("([c, px, pix]) => window.ESAM_TEST.colCanvas(c, px, pix, 3)", [COULEURS[-2], PIXELS, pix])
            assert [o for o in cv[:3]] == [q + [255] for q in PIXELS[:3]], (pix, cv[:3])
            assert all(o[3] == 255 for o in cv) and cv[5][:3] != PIXELS[5], cv
        b.close()

def test_miroir_story_cuts():
    """storyCuts (index.html) et story_cuts (server.py) coupent aux mêmes instants sur les mêmes plans."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  (Playwright absent : miroir storyCuts non vérifié)"); return
    plans = [([12, 25, 7], 3), ([40, 30, 50, 20], 0), ([70], 3), ([8, 8, 8, 8, 8, 8, 8, 8, 8], 3), ([59, 2, 2, 2], 3)]
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.goto((RACINE / "index.html").as_uri())
        for durs, fin in plans:
            js = pg.evaluate("([durs, fin]) => window.ESAM_TEST.storyCuts(durs, fin)", [durs, fin])
            bounds, pos = [], 0.0
            for d in durs: bounds.append(pos); pos += d
            bounds.append(pos)
            py = server.story_cuts(pos + fin, bounds, 60)
            assert [round(x, 3) for x in js] == [round(x, 3) for x in py], (durs, fin, js, py)
        b.close()

def test_fiche_ancienne_avec_retex():
    """Une fiche ancienne (section Chronologie RETEX, thèmes sous « Ce qu'on voit ») se reprend toujours."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  (Playwright absent : reprise de fiche non vérifiée)"); return
    data = {"app": "esam-derushage", "v": 1, "base": 1789223405, "real": True, "meta": {"intervention": "Test", "version": 0.3, "log": []},
            "offsets": {}, "markers": [{"id": "a1", "at": 1789223410, "to": 1789223420, "preset": "Décollage", "title": "Décollage",
                                        "themes": ["Recherche"], "interest": 2, "sens": ["Aucune"], "note": "", "comment": "", "cam": "W"}]}
    fiche = ("# Dérushage drone - Test\n\n### 1. 14:30:10 - Décollage #1\n\n- Ce qu'on voit : Recherche\n\n"
             "## Chronologie RETEX\n\n| Indicateur | Valeur |\n|---|---|\n| Nombre de vols | 1 |\n\n"
             "<!-- derushage-data " + json.dumps(data, ensure_ascii=False) + " -->")
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.goto((RACINE / "index.html").as_uri())
        assert pg.evaluate("t => window.ESAM_TEST.fiche(t)", fiche) == 1
        b.close()

if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print("ok", name)
    print(n, "tests OK")
