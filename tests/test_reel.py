"""Test de bout en bout de l'onglet Réel en mode PC : montage, cadrage, musique, réel et story.

Usage : python tests/test_reel.py [--garder]
Prérequis : ffmpeg, playwright (pip install playwright ; playwright install chromium).
Fabrique de faux rushs, lance server.py (port 8798, config temporaire), pose trois marqueurs,
monte un réel de plus de 60 s avec cadrage suivi, accéléré, textes et musique, le fait calculer
par le PC puis en story, et vérifie les fichiers produits (1080 x 1920, durée, piste son).
Les captures d'écran sont écrites dans le dossier temporaire affiché.
"""
import asyncio, json, os, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent; RACINE = ICI.parent; PORT = 8798

def api(path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/{path}", data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r: return json.load(r)

def ffprobe(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(p)], capture_output=True, text=True)
    d = json.loads(out.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = [s for s in d["streams"] if s["codec_type"] == "audio"]
    return {"w": v["width"], "h": v["height"], "dur": float(d["format"]["duration"]), "audio": bool(a)}

async def navigateur(tmp, iv):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        erreurs = []; pg.on("pageerror", lambda e: erreurs.append(str(e)))
        await pg.goto(f"http://127.0.0.1:{PORT}/"); await pg.wait_for_selector("[data-open]", timeout=15000)
        await pg.click("[data-open]"); await pg.wait_for_selector("#view:not([hidden])")
        await pg.wait_for_timeout(800)
        async def at(t):
            await pg.evaluate(f"document.querySelector('#v').currentTime={t}"); await pg.wait_for_timeout(350)
        for a, z in ((3, 80), (40, 55)):
            await at(a); await pg.click("#mkS"); await at(z); await pg.click("#mkE")
            if await pg.is_visible("#sheet"): await pg.click("#shCancel")
        await at(70); await pg.click("#mkP")
        if await pg.is_visible("#sheet"): await pg.click("#shSave")
        await pg.click("#tabReel"); await pg.wait_for_timeout(500)
        await pg.screenshot(path=str(tmp / "r0_vide.png"))
        for _ in range(3):
            await pg.click("#rAdd [data-radd] >> nth=0"); await pg.wait_for_timeout(300)
        print("montage :", await pg.inner_text("#rList"))
        # passage 2 : accéléré x4 et texte
        await pg.click("#rList [data-rsel] >> nth=1"); await pg.wait_for_timeout(500)
        await pg.click('#rEdit [data-rvit="4"]'); await pg.fill("#rTexte", "Le chien est repéré au bord du torrent")
        # passage 1 : cadrage suivi pendant la lecture
        await pg.click("#rList [data-rsel] >> nth=0"); await pg.wait_for_timeout(1200)
        box = await pg.locator("#rCv").bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        await pg.mouse.move(cx, cy); await pg.mouse.down()
        await pg.mouse.move(cx - 60, cy, steps=5)
        await pg.click("#rPlay", force=True)
        for i in range(10):
            await pg.mouse.move(cx - 60 + i * 15, cy); await pg.wait_for_timeout(150)
        await pg.mouse.up(); await pg.click("#rPlay"); await pg.wait_for_timeout(300)
        print("cadrage :", await pg.inner_text("#rEdit .grp >> nth=0"))
        await pg.screenshot(path=str(tmp / "r1_cadrage.png"))
        await pg.fill("#rTitre", "Perdu depuis trois jours, retrouvé par le drone")
        await pg.set_input_files("#rMusIn", str(tmp / "musique.mp3"))
        await pg.wait_for_function("document.getElementById('rMusInfo').textContent.indexOf('envoyée') >= 0", timeout=10000)
        await pg.fill("#rMusOff", "2")
        await pg.click("#rMode .chip >> nth=1"); await pg.wait_for_timeout(500)
        await pg.click("#rPlay"); await pg.wait_for_timeout(1800); await pg.click("#rPlay")
        await pg.wait_for_timeout(200)
        print("aperçu :", (await pg.inner_text("#rTime")).replace("\n", " "), "|", await pg.inner_text("#rInfo"))
        await pg.screenshot(path=str(tmp / "r2_apercu.png"), full_page=False)
        await pg.screenshot(path=str(tmp / "r3_page.png"), full_page=True)
        etat = api("api/etat?d=" + urllib.parse.quote(iv))
        reel = etat["meta"]["reel"]
        print("enregistré :", len(reel["items"]), "passages,", [len(x["keys"]) for x in reel["items"]], "points, vitesses", [x["vit"] for x in reel["items"]], "musique", reel.get("musique"))
        for story in (False, True):
            await pg.click("#rGoStory" if story else "#rGoReel")
            await pg.wait_for_selector("#cmpDone:not([hidden])", timeout=600000)
            print("résultat :", await pg.inner_text("#cmpInfo"))
            await pg.click("#cmpClose2")
        pc = await b.new_page(viewport={"width": 1400, "height": 900})
        await pc.goto(f"http://127.0.0.1:{PORT}/"); await pc.wait_for_selector("[data-open]"); await pc.click("[data-open]")
        await pc.wait_for_selector("#view:not([hidden])"); await pc.click("#tabReel"); await pc.wait_for_timeout(1200)
        await pc.screenshot(path=str(tmp / "r4_pc.png"))
        assert not erreurs, erreurs
        await b.close()

def main():
    import urllib.parse
    globals()["urllib"] = urllib
    tmp = Path(tempfile.mkdtemp(prefix="esam_reel_test_"))
    subprocess.run([sys.executable, str(ICI / "fabriquer_rushs.py"), str(tmp / "rushs"), "--vp9"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=150", "-ac", "2", str(tmp / "musique.mp3")], check=True)
    cfg = json.loads((RACINE / "config.exemple.json").read_text(encoding="utf-8"))
    cfg.update({"dossier_rushs": str(tmp / "rushs"), "port": PORT, "mode_inactivite": "aucun", "_test_vp9": True, "dossier_travail": str(tmp / "travail")})
    (tmp / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    srv = subprocess.Popen([sys.executable, str(RACINE / "server.py")], env=dict(os.environ, ESAM_CONFIG=str(tmp / "config.json")))
    try:
        for _ in range(40):
            try: api("api/status"); break
            except Exception: time.sleep(0.25)
        iv = api("api/interventions")["interventions"][0]["nom"]
        api("api/proxies", {"d": iv})
        while True:
            x = api("api/interventions")["interventions"][0]
            if x["proxies"] == x["videos"]: break
            time.sleep(0.5)
        asyncio.run(navigateur(tmp, iv))
        d = tmp / "rushs" / iv
        outs = sorted(p.name for p in d.glob("ESAM_*.mp4"))
        print("fichiers :", outs)
        for n in outs:
            print(" ", n, ffprobe(d / n))
        assert any(n.startswith("ESAM_Reel_") for n in outs)
        assert sum(1 for n in outs if n.startswith("ESAM_Story_")) >= 2
        for n in outs:
            i = ffprobe(d / n); assert (i["w"], i["h"]) == (1080, 1920) and i["audio"], (n, i)
            if n.startswith("ESAM_Story_"): assert i["dur"] <= 61, (n, i)
        print("OK, captures dans", tmp)
    finally:
        srv.terminate()

if __name__ == "__main__":
    main()
