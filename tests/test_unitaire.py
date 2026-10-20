"""Tests unitaires : fonctions pures de server.py, et calculs en miroir entre l'appli et le serveur.

Usage : python tests/test_unitaire.py
Sans dépendance pour la partie serveur ; la comparaison storyCuts (index.html) / story_cuts (server.py)
demande Playwright (pip install playwright ; playwright install chromium) et est sautée sinon.
Le serveur est importé avec une configuration temporaire (variable ESAM_CONFIG) : config.json n'est pas touché.
"""
import json, os, struct, sys, tempfile
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
    assert server.crop_box(1920, 1080) == (606, 1080, 1314, 0)       # 16:9 : cadre plein hauteur, course horizontale
    assert server.crop_box(1080, 1920) == (1080, 1920, 0, 0)        # déjà vertical
    assert server.crop_box(1000, 1000) == (562, 1000, 438, 0)        # carré : cadre plein hauteur, course de 438 px

def test_key_expr():
    assert server.key_expr([], "x") == "0.5000"
    assert server.key_expr([{"t": 2, "x": 0.25}], "x") == "if(lt(t,2.000),0.2500,0.2500)"
    e = server.key_expr([{"t": 0, "x": 0}, {"t": 4, "x": 1}], "x")
    assert e.startswith("if(lt(t,0.000),0.0000,if(lt(t,4.000),0.0000+(1.0000)*") and e.endswith("1.0000))")

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

if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print("ok", name)
    print(n, "tests OK")
