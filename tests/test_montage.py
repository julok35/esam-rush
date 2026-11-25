"""Test de bout en bout du montage : retouches d'un passage, extraits bruts, reprise d'une vidéo compilée.

Usage : python tests/test_montage.py
Prérequis : ffmpeg, playwright (pip install playwright ; playwright install chromium).

1. Mode navigateur : une vidéo où un motif se déplace sur un fond bruité ; un flou est posé dessus et suivi
   automatiquement (l'écart entre le suivi et la vraie trajectoire est mesuré), puis des extraits bruts sont
   calculés dans le navigateur avec un accéléré (durée vérifiée).
2. Mode PC (port 8797, config temporaire) : flou suivi du doigt, flèche, cercle et changement de vitesse sur un
   passage ; vidéo compilée avec habillage, puis extraits bruts en un fichier par passage (durées vérifiées) ;
   enfin la vidéo compilée est rouverte comme source et un morceau en est extrait, sans carton ni logo.
Les captures d'écran sont écrites dans le dossier temporaire affiché.
"""
import asyncio, json, math, os, subprocess, sys, tempfile, time, urllib.parse, urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent; RACINE = ICI.parent; PORT = 8797; PORT_NAV = 8796

def api(path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/{path}", data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r: return json.load(r)

def duree(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(out.stdout.strip())

def cible(t):
    """Centre du motif mobile de la vidéo de suivi, en fraction de l'image, à l'instant t."""
    return (80 + 28 * t + 32) / 640, (140 + 50 * math.sin(t * 0.9) + 32) / 360

async def curseur(pg, sel, valeur):
    await pg.evaluate("([s, v]) => { const e = document.querySelector(s); e.value = v; e.dispatchEvent(new Event('input', {bubbles:true})); e.dispatchEvent(new Event('change', {bubbles:true})); }", [sel, valeur])
    await pg.wait_for_timeout(500)

async def marquer(pg, a, z):
    for t, b in ((a, "#mkS"), (z, "#mkE")):
        await pg.evaluate(f"document.querySelector('#v').currentTime={t}"); await pg.wait_for_timeout(400); await pg.click(b)
    if await pg.is_visible("#sheet"): await pg.click("#shSave")
    await pg.wait_for_timeout(200)

async def navigateur(p, tmp):
    """Suivi automatique et extraits calculés dans le navigateur."""
    src = tmp / "nav"; src.mkdir()
    video = src / "DJI_20260912143005_0001_W.MP4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x5a6e52:s=640x360:r=30:d=14,noise=alls=14:allf=t+u",
                    "-f", "lavfi", "-i", "testsrc=s=64x64:r=30:d=14", "-filter_complex", "[0][1]overlay=x='80+28*t':y='140+50*sin(t*0.9)'",
                    "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "900k", "-f", "mp4", str(video)], check=True)
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT_NAV), "--bind", "127.0.0.1"], cwd=str(RACINE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        await asyncio.sleep(1)
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 390, "height": 844})
        erreurs = []; pg.on("pageerror", lambda e: erreurs.append(str(e)))
        await pg.goto(f"http://127.0.0.1:{PORT_NAV}/index.html")
        await pg.set_input_files("#fileIn", str(video))
        await pg.wait_for_selector("#view:not([hidden])", timeout=30000); await pg.wait_for_timeout(1200)
        await marquer(pg, 1, 11)
        await pg.click("#tabSum"); await pg.click("#list [data-fx]"); await pg.wait_for_selector("#fx[open]"); await pg.wait_for_timeout(1200)
        # flou posé sur le motif, puis suivi automatique jusqu'à la fin du passage
        await pg.click('#fxPanel [data-fxadd="flou"]'); await pg.wait_for_timeout(300)
        t0 = (await pg.evaluate("window.ESAM_TEST.etat()"))["fx"]["t"]
        box = await pg.locator("#fxCv").bounding_box(); x, y = cible(t0)
        await pg.mouse.click(box["x"] + box["width"] * x, box["y"] + box["height"] * y); await pg.wait_for_timeout(300)
        await pg.fill("#fxSize", "24"); await pg.dispatch_event("#fxSize", "input")
        await pg.click("#fxPanel [data-fxtrack]")
        for _ in range(80):
            await pg.wait_for_timeout(500)
            etat = await pg.evaluate("window.ESAM_TEST.etat()")
            if not etat["fx"]["suivi"]: break
        else: raise AssertionError("le suivi ne se termine pas")
        cles = etat["markers"][0]["fx"]["flous"][0]["keys"]
        ecart = max(math.hypot(k["x"] - cible(k["t"])[0], k["y"] - cible(k["t"])[1]) for k in cles)
        print("suivi automatique :", len(cles), "points jusqu'à", round(cles[-1]["t"], 1), "s, écart maximal", round(ecart, 4), "|", await pg.inner_text("#toast"))
        assert cles[-1]["t"] > 10.5, "le suivi s'est arrêté avant la fin du passage"
        assert ecart < 0.02, "le suivi s'écarte du motif"
        # accéléré x4 à partir du milieu : 10 s de passage deviennent 3 + 7/4 s
        await curseur(pg, "#fxSlider", 400)
        await pg.click('#fxPanel [data-fxvit="4"]'); await pg.wait_for_timeout(300)
        await pg.screenshot(path=str(tmp / "m1_suivi.png"))
        await pg.click("#fxDone"); await pg.wait_for_timeout(300)
        await pg.click("#cmpOpen"); await pg.wait_for_timeout(400)
        await pg.click("#cmpHab .chip >> nth=1"); await pg.wait_for_timeout(200)
        await pg.screenshot(path=str(tmp / "m2_extraits.png"))
        await pg.click("#cmpGo"); await pg.wait_for_selector("#cmpDone:not([hidden])", timeout=300000)
        print("navigateur :", await pg.inner_text("#cmpInfo"))
        async with pg.expect_download() as dl: await pg.click("#cmpSave")
        d = await dl.value; out = tmp / d.suggested_filename; await d.save_as(str(out))
        assert out.name.startswith("ESAM_Extraits_2026-09-12"), out.name
        etat = await pg.evaluate("window.ESAM_TEST.etat()"); v = etat["markers"][0]["fx"]["vits"][0]
        attendu = (v["t"] - 1) + (11 - v["t"]) / 4
        print("extraits du navigateur :", out.name, round(duree(out), 2), "s, attendu", round(attendu, 2))
        assert abs(duree(out) - attendu) < 0.4, (duree(out), attendu)       # ni carton ni noir de fin : la durée est celle des passages
        assert not erreurs, erreurs
        await b.close()
    finally:
        srv.terminate()

async def pc(p, tmp, iv):
    """Retouches, vidéo compilée, extraits séparés, puis reprise de la vidéo compilée, en mode PC."""
    d = tmp / "rushs" / iv
    b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    erreurs = []; pg.on("pageerror", lambda e: erreurs.append(str(e)))
    async def calcul():
        await pg.click("#cmpGo"); await pg.wait_for_selector("#cmpDone:not([hidden])", timeout=600000)
        info = await pg.inner_text("#cmpInfo"); assert "[" not in info, info
        print("résultat :", info, "|", (await pg.inner_text("#cmpFile")).replace("\n", ", "))
    await pg.goto(f"http://127.0.0.1:{PORT}/"); await pg.wait_for_selector("[data-open]", timeout=15000)
    await pg.click("[data-open]"); await pg.wait_for_selector("#view:not([hidden])"); await pg.wait_for_timeout(800)
    await marquer(pg, 5, 17); await marquer(pg, 30, 36)
    await pg.click("#tabSum"); await pg.wait_for_timeout(300)
    # passage 1 : flou rectangle suivi du doigt pendant la lecture, flèche rouge, cercle limité dans le temps, ralenti puis accéléré
    await pg.click("#list [data-fx] >> nth=0"); await pg.wait_for_selector("#fx[open]"); await pg.wait_for_timeout(1000)
    await pg.click('#fxPanel [data-fxadd="flou"]'); await pg.wait_for_timeout(300)
    await pg.click('#fxPanel [data-fxforme="rect"]'); await pg.fill("#fxAr", "200"); await pg.dispatch_event("#fxAr", "input")
    await pg.locator("#fxCv").scroll_into_view_if_needed()
    box = await pg.locator("#fxCv").bounding_box(); cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    await pg.click("#fxPlay"); await pg.wait_for_timeout(300)             # lecture, puis le doigt se pose sur le flou et le suit
    await pg.mouse.move(cx, cy); await pg.mouse.down()
    for i in range(8):
        await pg.mouse.move(cx - 70 + i * 18, cy - 20 + i * 5); await pg.wait_for_timeout(150)
    await pg.mouse.up(); await pg.click("#fxPlay"); await pg.wait_for_timeout(300)
    await pg.click('#fxPanel [data-fxadd="fleche"]'); await pg.wait_for_timeout(300)
    await pg.click('#fxPanel [data-fxcol="#E20C0F"]'); await pg.fill("#fxRot", "-120"); await pg.dispatch_event("#fxRot", "input")
    await pg.click('#fxPanel [data-fxadd="cercle"]'); await pg.wait_for_timeout(300)
    await curseur(pg, "#fxSlider", 400); await pg.click('#fxPanel [data-fxvis="a"]')
    await curseur(pg, "#fxSlider", 0); await pg.click('#fxPanel [data-fxvit="0.5"]'); await pg.wait_for_timeout(200)      # ralenti dès le début
    await curseur(pg, "#fxSlider", 500); await pg.click('#fxPanel [data-fxvit="4"]'); await pg.wait_for_timeout(200)      # accéléré ensuite
    await pg.screenshot(path=str(tmp / "m3_retouches.png"))
    await pg.click("#fxDone"); await pg.wait_for_timeout(500)
    etat = api("api/etat?d=" + urllib.parse.quote(iv)); m1, m2 = sorted(etat["markers"], key=lambda m: m["at"])
    fx = m1["fx"]
    print("retouches :", [(f["forme"], len(f["keys"])) for f in fx["flous"]], [(f["kind"], f.get("a")) for f in fx["formes"]], fx["vits"])
    assert fx["flous"][0]["forme"] == "rect" and len(fx["flous"][0]["keys"]) >= 2 and len(fx["formes"]) == 2 and [v["v"] for v in fx["vits"]] == [0.5, 4]
    base = (await pg.evaluate("window.ESAM_TEST.etat()"))["base"]
    t1, t2 = m1["at"] - base, m1["to"] - base; cut = fx["vits"][1]["t"]
    d1 = (cut - t1) / 0.5 + (t2 - cut) / 4; d2 = m2["to"] - m2["at"]
    # liste des plans : « ce qu'on voit » sur la carte, commentaire interne absent sauf demande ; enregistrée aussi sur le PC
    await pg.fill("#list textarea[data-desc] >> nth=0", "Le chien couché sous une barre rocheuse")
    await pg.fill("#list textarea[data-com] >> nth=1", "NE PAS PUBLIER ce commentaire")
    await pg.wait_for_timeout(1000)
    bande = await pg.inner_text("#durs"); print("bande des durées :", bande.replace("\n", " "))
    assert "2 plans" in bande and "Réseaux" in bande, bande
    await pg.click("#tabExp"); await pg.wait_for_selector("#expo:not([hidden])")
    assert "2 plans" in await pg.inner_text("#xCmpDur")
    async with pg.expect_download() as dl: await pg.click("#xPlansDl")
    assert (await dl.value).suggested_filename.startswith("ESAM_Plans_2026-09-12")
    await pg.wait_for_timeout(500)
    plans = next(d.glob("ESAM_Plans_*.md")).read_text(encoding="utf-8")
    assert "Le chien couché sous une barre rocheuse" in plans and "NE PAS PUBLIER" not in plans and "### Plan 2" in plans, plans
    assert "NE PAS PUBLIER" in await pg.evaluate("window.ESAM_TEST.plans(true)")
    assert len(list(d.glob("ESAM_Derushage_*.md"))) == 1, "la liste des plans a remplacé la fiche"
    print("liste des plans :", next(d.glob("ESAM_Plans_*.md")).name, len(plans), "caractères")
    # vidéo compilée avec habillage, lancée depuis l'étape Export : ouverture, cartons, passages retouchés
    await pg.click("#xCmpGo"); await pg.wait_for_timeout(400)
    await pg.screenshot(path=str(tmp / "m4_compilation.png"))
    assert await pg.inner_text("#cmpTitle") == "Vidéo compilée"
    await calcul()
    comp = next(d.glob("ESAM_Compilation_*.mp4"))
    print("vidéo compilée :", comp.name, round(duree(comp), 2), "s ; passages attendus :", round(d1, 2), "+", round(d2, 2))
    assert abs(duree(comp) - (3 + 3 + 3 + d1 + d2)) < 1.0, duree(comp)             # ouverture 3 s, deux cartons de 3 s
    # extraits bruts, un fichier par passage : ni carton, ni logo
    await pg.click("#cmpBack"); await pg.wait_for_timeout(300)
    await pg.click("#cmpHab .chip >> nth=1"); await pg.click("#cmpSep .chip >> nth=1"); await pg.wait_for_timeout(200)
    assert await pg.inner_text("#cmpTitle") == "Extraits"
    await pg.screenshot(path=str(tmp / "m5_extraits.png"))
    await calcul()
    ex = sorted(d.glob("ESAM_Extraits_*.mp4"))
    print("extraits :", [(f.name, round(duree(f), 2)) for f in ex])
    assert len(ex) == 2 and "_01" in ex[0].name and "_02" in ex[1].name
    assert abs(duree(ex[0]) - d1) < 0.5 and abs(duree(ex[1]) - d2) < 0.5, (duree(ex[0]), d1, duree(ex[1]), d2)
    await pg.click("#cmpClose2")
    # reprise de la vidéo compilée comme source : préparation, ouverture, un morceau extrait sans habillage
    await pg.click("#home"); await pg.wait_for_selector("[data-openc]", timeout=15000)
    assert await pg.get_attribute("[data-openc]", "data-ready") == "0"
    await pg.click("[data-openc]")
    await pg.wait_for_selector('[data-openc][data-ready="1"]', timeout=180000)
    await pg.screenshot(path=str(tmp / "m6_liste.png"))
    await pg.click("[data-openc]"); await pg.wait_for_selector("#empty", state="hidden")      # l'appli rouvre sur l'étape quittée (Export)
    await pg.click("#tabView"); await pg.wait_for_selector("#view:not([hidden])"); await pg.wait_for_timeout(1000)
    pistes = await pg.eval_on_selector_all(".lab", "l => l.map(e => e.textContent.trim())"); print("source :", pistes, "|", await pg.inner_text("#mMeta"))
    await marquer(pg, 10, 14)
    await pg.click("#tabSum"); await pg.wait_for_timeout(300)
    assert "extraits" in (await pg.inner_text("#cmpOpen")).lower()
    await pg.click("#cmpOpen"); await pg.wait_for_timeout(400)
    assert await pg.inner_text("#cmpTitle") == "Extraits"              # d'office sans habillage : la source est une vidéo déjà montée
    await pg.screenshot(path=str(tmp / "m7_reprise.png"))
    avant = set(d.glob("ESAM_Extraits_*.mp4"))
    await calcul()
    neuf = [f for f in d.glob("ESAM_Extraits_*.mp4") if f not in avant]
    print("morceau de la vidéo compilée :", [(f.name, round(duree(f), 2)) for f in neuf])
    assert len(neuf) == 1 and abs(duree(neuf[0]) - 4) < 0.4, neuf
    assert (d / ".derushage" / "etat-compil.json").exists() and len(api("api/etat?d=" + urllib.parse.quote(iv))["markers"]) == 2      # marqueurs des rushs intacts
    assert len(list(d.glob("ESAM_Derushage_*.md"))) == 1
    await pg.click("#cmpClose2")
    pcw = await b.new_page(viewport={"width": 1400, "height": 900})
    await pcw.goto(f"http://127.0.0.1:{PORT}/"); await pcw.wait_for_selector("[data-open]"); await pcw.click("[data-open]")
    await pcw.wait_for_selector("#view:not([hidden])"); await pcw.click("#tabSum"); await pcw.wait_for_timeout(500)
    await pcw.click("#list [data-fx] >> nth=0"); await pcw.wait_for_selector("#fx[open]"); await pcw.wait_for_timeout(1500)
    await pcw.click('#fxPanel [data-fxsel] >> nth=0'); await pcw.wait_for_timeout(400)
    await pcw.screenshot(path=str(tmp / "m8_pc.png"))
    assert not erreurs, erreurs
    await b.close()

async def tout(tmp, iv):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        await navigateur(p, tmp)
        await pc(p, tmp, iv)

def main():
    tmp = Path(tempfile.mkdtemp(prefix="esam_montage_test_"))
    subprocess.run([sys.executable, str(ICI / "fabriquer_rushs.py"), str(tmp / "rushs"), "--vp9"], check=True, stdout=subprocess.DEVNULL)
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
        asyncio.run(tout(tmp, iv))
        print("OK, captures dans", tmp)
    finally:
        srv.terminate()

if __name__ == "__main__":
    main()
