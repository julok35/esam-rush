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
