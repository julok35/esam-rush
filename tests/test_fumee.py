"""Test de fumée de bout en bout : serveur + appli + préparation des proxies.

Usage : python tests/test_fumee.py
Prérequis : ffmpeg, et pour la partie navigateur : pip install playwright ; playwright install chromium
Fabrique de faux rushs (VP9) dans un dossier temporaire, lance server.py sur le port 8799
avec une configuration de test (sans toucher à config.json), ouvre l'appli, vérifie le badge
de version, la liste des interventions, puis lance « Préparer » et attend la fin des proxies.
"""
import json, os, subprocess, sys, tempfile, time, urllib.request, asyncio
from pathlib import Path

ICI = Path(__file__).resolve().parent; RACINE = ICI.parent; PORT = 8799

def statut():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/status", timeout=2) as r:
        return json.load(r)

async def timeline_compacte(pg):
    """Temps morts repliés : les deux vols DJI des faux rushs sont séparés de 85 s sans image, soit une coupure ;
    tlX et tlT sont réciproques et croissantes, aucune image ne tombe dans une coupure, la bascule revient à l'échelle réelle."""
    segs = await pg.evaluate("ESAM_TEST.tl.segs()"); cuts = [s for s in segs if s["cut"]]
    print("coupures :", [(round(c["t0"]), round(c["t1"]), round(c["x1"] - c["x0"])) for c in cuts])
    assert len(cuts) == 1 and abs(cuts[0]["t0"] - 90) < 1 and abs(cuts[0]["t1"] - 175) < 1, cuts
    assert 0 < cuts[0]["x1"] - cuts[0]["x0"] <= 52
    for piste in await pg.evaluate("ESAM_TEST.tl.clips()"):
        for s, e in piste:
            assert not any(s < c["t1"] - 1e-6 and e > c["t0"] + 1e-6 for c in cuts), ("image dans une coupure", s, e)
    ecart = await pg.evaluate("""() => { const d = ESAM_TEST.tl.dur(); let w = 0, prev = -Infinity;
        for(let i = 0; i <= 1000; i++){ const t = d*i/1000, x = ESAM_TEST.tl.x(t); if(x < prev) return -1; prev = x;
          w = Math.max(w, Math.abs(ESAM_TEST.tl.t(x) - t)); } return w; }""")
    assert 0 <= ecart < 1e-6, ecart
    # dans la coupure, 85 s tiennent dans sa largeur ; hors coupure, l'échelle est la même de part et d'autre
    c = cuts[0]
    assert abs(await pg.evaluate("t => ESAM_TEST.tl.x(t)", (c["t0"] + c["t1"])/2) - (c["x0"] + c["x1"])/2) < 1e-6
    k1 = await pg.evaluate("() => ESAM_TEST.tl.x(50) - ESAM_TEST.tl.x(40)"); k2 = await pg.evaluate("() => ESAM_TEST.tl.x(200) - ESAM_TEST.tl.x(190)")
    assert abs(k1 - k2) < 1e-6, (k1, k2)
    assert await pg.is_visible("#tlCut") and await pg.get_attribute("#tlCut", "aria-pressed") == "true"
    await pg.click("#tlCut"); await pg.wait_for_timeout(200)
    assert not [s for s in await pg.evaluate("ESAM_TEST.tl.segs()") if s["cut"]] and await pg.locator("#cuts .cut").count() == 0
    assert await pg.evaluate("localStorage.getItem('esam-tl-echelle')") == "reelle"
    await pg.click("#tlCut"); await pg.wait_for_timeout(200)
    assert await pg.locator("#cuts .cut").count() == 1 and await pg.evaluate("ESAM_TEST.tl.compact()")
    print("timeline compacte : OK")

async def navigateur():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 390, "height": 844})
        erreurs = []; pg.on("pageerror", lambda e: erreurs.append(str(e)))
        await pg.goto(f"http://127.0.0.1:{PORT}/"); await pg.wait_for_selector("#ivList .iv", timeout=15000)
        badge = await pg.inner_text("#ver"); classe = await pg.get_attribute("#ver", "class") or ""
        print("badge :", badge, "|", classe)
        assert "PC" in badge, "l'appli ne voit pas le serveur"
        assert "Chien" in await pg.inner_text("#ivList"), "intervention absente de la liste"
        await pg.click("[data-prep]")
        for _ in range(360):
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/interventions", timeout=5) as r:
                iv = json.load(r)["interventions"][0]
            if iv["proxies"] == iv["videos"]: break
            await asyncio.sleep(0.5)
        else: raise AssertionError("proxies non terminés")
        print("proxies prêts :", iv["proxies"], "sur", iv["videos"])
        await pg.click("[data-open]"); await pg.wait_for_selector("#view:not([hidden])", timeout=20000)
        await pg.wait_for_timeout(1500)
        pistes = await pg.eval_on_selector_all(".lab", "l => l.map(e => e.textContent.trim())")
        print("pistes :", pistes)
        assert len(pistes) >= 3, "pistes manquantes"
        assert any("Pixel 8" in x for x in pistes), "piste du téléphone non nommée d'après l'appareil"
        await timeline_compacte(pg)
        assert not erreurs, erreurs
        await b.close()

def main():
    tmp = Path(tempfile.mkdtemp(prefix="esam_test_"))
    subprocess.run([sys.executable, str(ICI / "fabriquer_rushs.py"), str(tmp / "rushs"), "--vp9"], check=True)
    cfg = json.loads((RACINE / "config.exemple.json").read_text(encoding="utf-8"))
    cfg.update({"dossier_rushs": str(tmp / "rushs"), "port": PORT, "mode_inactivite": "aucun", "_test_vp9": True})
    (tmp / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    env = dict(os.environ, ESAM_CONFIG=str(tmp / "config.json"))
    srv = subprocess.Popen([sys.executable, str(RACINE / "server.py")], env=env)
    try:
        for _ in range(40):
            try: s = statut(); break
            except Exception: time.sleep(0.25)
        else: raise SystemExit("le serveur ne démarre pas")
        print("serveur", s["version"], "| racine ok :", s["racine_ok"])
        assert s["racine_ok"]
        asyncio.run(navigateur())
        print("OK")
    finally:
        srv.terminate()

if __name__ == "__main__":
    main()
