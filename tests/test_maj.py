"""Test de la mise à jour depuis l'appli : api/maj (vérification, récupération par git, relance du serveur).

Usage : python tests/test_maj.py
Prérequis : git et ffmpeg. Aucun navigateur. Copie le programme dans un dépôt git temporaire qui suit un faux « GitHub » (dépôt nu local),
lance server.py (port 8797, configuration temporaire) sous son superviseur, publie une version 9.99 sur le faux GitHub,
puis vérifie que le serveur l'annonce, la récupère, se relance tout seul et répond avec la nouvelle version.
Vérifie aussi le refus pendant un calcul et le refus d'une requête qui n'est pas en JSON.
"""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent; RACINE = ICI.parent; PORT = 8797

def api(path, body=None, ctype="application/json"):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/{path}", data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": ctype} if body is not None else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try: return e.code, json.load(e)
        except Exception: return e.code, {}

def git(d, *a):
    subprocess.run(["git", "-C", str(d), "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false"] + list(a),
                   check=True, capture_output=True)

def attendre(cond, s=30):
    fin = time.time() + s
    while time.time() < fin:
        try:
            r = cond()
            if r: return r
        except Exception: pass
        time.sleep(0.3)
    raise AssertionError("délai dépassé")

def main():
    tmp = Path(tempfile.mkdtemp(prefix="esam_maj_"))
    distant = tmp / "github.git"; pc = tmp / "pc"; autre = tmp / "autre"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(distant)], check=True)
    pc.mkdir()
    for f in ("server.py", "index.html", "config.exemple.json", ".gitignore"): shutil.copy(RACINE / f, pc / f)
    shutil.copytree(RACINE / "vendor", pc / "vendor")
    git(pc, "init", "-q", "-b", "main"); git(pc, "add", "-A"); git(pc, "commit", "-q", "-m", "version installée")
    git(pc, "remote", "add", "origin", str(distant)); git(pc, "push", "-q", "-u", "origin", "main")
    (tmp / "rushs").mkdir()
    cfg = json.loads((RACINE / "config.exemple.json").read_text(encoding="utf-8"))
    cfg.update({"dossier_rushs": str(tmp / "rushs"), "port": PORT, "mode_inactivite": "aucun"})
    (tmp / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    srv = subprocess.Popen([sys.executable, str(pc / "server.py")], env=dict(os.environ, ESAM_CONFIG=str(tmp / "config.json")))
    try:
        st = attendre(lambda: api("api/status")[1])
        v0 = st["version"]; print("serveur", v0, "démarré")
        code, e = api("api/maj")
        print("avant publication :", e)
        assert code == 200 and e["possible"] and e["relance"] and not e["disponible"], e
        assert api("api/maj", {})[1] == {"ok": True, "maj": False, "version": v0}, "une mise à jour sans nouveauté doit ne rien faire"
        api("api/maj")

        # une version 9.99 est publiée sur le faux GitHub depuis un autre poste
        subprocess.run(["git", "clone", "-q", str(distant), str(autre)], check=True)
        src = (autre / "server.py").read_text(encoding="utf-8")
        (autre / "server.py").write_text(re.sub(r'^VERSION = "[^"]+"', 'VERSION = "9.99"', src, count=1, flags=re.M), encoding="utf-8")
        git(autre, "commit", "-q", "-am", "version 9.99"); git(autre, "push", "-q", "origin", "main")
        assert not api("api/maj")[1]["disponible"], "la réponse devait rester en mémoire 10 minutes"
        e = api("api/maj?force=1")[1]; print("après publication :", e)
        assert e["disponible"] and e["nouvelle"] == "9.99", e

        assert api("api/maj", {}, ctype="text/plain")[0] == 403, "une requête qui n'est pas en JSON doit être refusée"
        # pendant un calcul : refus (la relance l'interromprait)
        iv = tmp / "rushs" / "Intervention"; iv.mkdir()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=60",
                        "-c:v", "libx264", "-preset", "ultrafast", str(iv / "DJI_20260912143005_0001_W.MP4")], check=True)
        j = api("api/proxies", {"d": "Intervention"})[1]
        code, r = api("api/maj", {}); print("pendant un calcul :", code, r)
        assert code == 400 and "calcul" in r["erreur"], r
        api("api/annuler", {"id": j["id"]})
        attendre(lambda: all(t["etat"] not in ("attente", "en_cours") for t in api("api/status")[1]["travaux"]))

        code, r = api("api/maj", {}); print("mise à jour :", r)
        assert code == 200 and r == {"ok": True, "maj": True, "relance": True, "version": "9.99"}, r
        st2 = attendre(lambda: (lambda s: s if s["demarre"] != st["demarre"] else None)(api("api/status")[1]))
        print("serveur relancé en", st2["version"])
        assert st2["version"] == "9.99"
        assert not api("api/maj?force=1")[1]["disponible"]
        assert srv.poll() is None, "le superviseur doit rester en marche"
        print("OK")
    finally:
        srv.terminate()
        try: srv.wait(5)
        except Exception: srv.kill()
        time.sleep(0.5); shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()
