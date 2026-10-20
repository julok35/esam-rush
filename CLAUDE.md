# Consignes pour Claude Code

Projet : outil de dérushage des vidéos drone de l'ESAM (secours animalier en montagne). Utilisateur principal : Julien, pilote drone bénévole ; destinataires des sorties : l'équipe communication. Toute l'interface, les messages et la documentation sont en français.

## Architecture

- `index.html` : appli complète en un seul fichier (HTML + CSS + JS vanilla dans une IIFE). Pas de framework, pas de build. Bibliothèques chargées depuis jsDelivr, versions figées : mp4box 0.5.3 (démux, ftyp+moov seulement), mp4-muxer 5.2.1.
- Deux modes, détectés au démarrage par `srvInit()` (appel `api/status`) :
  - **Mode PC** : `server.py` répond, le badge affiche « vX PC ». Les vidéos viennent du dossier Drive synchronisé, proxies 540p et planches de vignettes faites par ffmpeg, vidéo compilée montée par ffmpeg (NVENC si disponible).
  - **Mode navigateur** (GitHub Pages ou fichier local) : fichiers choisis par l'utilisateur, compilation par WebCodecs + OffscreenCanvas, sortie écrite par morceaux (blobTarget, jamais un ArrayBuffer géant). `showDirectoryPicker` seulement si `window.self === window.top`.
- `server.py` : `ThreadingHTTPServer` sur 127.0.0.1 (exposé au téléphone par `tailscale serve`), file de calculs persistée dans `travaux.json` (calcul coupé = « interrompu »), mise en veille du PC après inactivité, requêtes Range pour les proxies.
- Onglet Réel (fin de `index.html`, section « réel et story ») : réglages dans `S.meta.reel` (donc dans `etat.json` et la fiche) : `items` (passage : id du marqueur, plage `a`/`z` en secondes de timeline, `cam`, `vit`, `keys` = points de cadrage `{t, x}` lissés par `rKeyAt` ; photo : `photo` = chemin relatif du JPEG, `dur`, `x`, `zoom` ; pour les deux : `texte`, `tBox` `{x, y, s}`, `tDur` (0 = tout le passage), `flous` = zones de flou doux `{id, s, keys:[{t, x, y}]}` en fraction de l'image source), `titre`, `titreDur`, `titreBox` (`{x, y, s, c}`, `c` = couleur), `elems` (textes libres et formes `{id, kind: texte|fleche|cercle|cadre, a, d, x, y, s, rot, c, texte, fond}`, temps en secondes du réel), `logo` `{mode: cartouche|logo|non, x, y, s}`, `fin`, `musique`, `musDebut`. Habillage = calques (`rLayers` : logo, accéléré, textes, éléments libres, titre, avec plage de temps et fondus), dessinés par `drawLayers` dans l'aperçu et le rendu navigateur, envoyés en PNG plein cadre au PC. Rendu PC : job `reel` dans `server.py` (`do_reel` : flous par `blur_chain` sur l'image source (gblur + masque d'ellipse fondu, même rendu que `softBlur` du navigateur), crop animé par expression ffmpeg, calques superposés avec `enable` et `fade`, photo cadrée par le navigateur puis zoom lent par `zoompan`, concat, musique, story coupée sans réencodage). Rendu navigateur : `runReelLocal`/`rRender` (WebCodecs, 30 i/s rééchantillonnés, son par AudioEncoder). Photos : `photos()`/`api/image` côté PC (copies redressées selon l'EXIF dans `proxies/photos`), fichiers `PH.list` côté navigateur.
- Données par intervention (sous-dossier du dossier des rushs) : `proxies/`, `.derushage/etat.json`, fiche `ESAM_Derushage_*.md` (une seule), `Photos/`, `ESAM_Compilation_*.mp4` + `.commentaires-ESAM.srt` + `_chapitres.txt`.

## Règles du projet

- **Tirets** : jamais de tiret cadratin (U+2014) ni demi-cadratin (U+2013), ni dans le code, ni dans les textes, ni dans les noms de fichiers. Tiret simple uniquement. Dans `server.py`, les écrire en échappement (`"\u2014"`) quand il faut les détecter. Vérifier avant chaque commit :
  `python -c "import sys;[print(f, open(f,encoding='utf-8').read().count(chr(0x2014))+open(f,encoding='utf-8').read().count(chr(0x2013))) for f in sys.argv[1:]]" index.html server.py LISEZMOI.md README.md CLAUDE.md`
- **Version** : à chaque changement livré, incrémenter ensemble `APP_VERSION` dans `index.html` et `VERSION` dans `server.py` (le badge passe au jaune si elles diffèrent), puis `version`/`date_maj` du frontmatter de `LISEZMOI.md` et une ligne dans son Changelog (succincte, orientée utilisateur).
- Les commentaires internes ESAM ne doivent jamais être incrustés dans la vidéo compilée (fichier `.srt` à part) : la vidéo doit rester publiable telle quelle.
- `config.json` est propre à chaque PC et ignoré par git ; les nouveaux réglages vont dans `config.exemple.json` avec une valeur par défaut, et `server.py` doit fonctionner s'ils sont absents (`CFG.get`).
- Mobile d'abord (téléphone en portrait), mais la mise en page PC doit exploiter l'écran large.
- Respecter la charte ESAM existante dans `index.html` (polices Anton et Montserrat, couleurs déjà définies).

## Points délicats déjà rencontrés

- Vidéos de téléphone en portrait : matrice de rotation à appliquer (vignettes et compilation). Heure de début prise dans `creation_time` (UTC).
- Vidéos DJI : heure de début lue dans le nom de fichier `DJI_AAAAMMJJHHMMSS_NNNN_X`, X = W (grand angle), Z (zoom), T (thermique), S (écran).
- Une compilation de plusieurs Go dans le navigateur plantait à 100 % : ne jamais accumuler la sortie en mémoire.
- La caméra compilée pour un passage est `effCam(m)` : le choix `m.cam` s'il a de l'image, sinon la première caméra disponible.

## Tester

- `python tests/test_fumee.py` : fabrique de faux rushs, lance le serveur avec une config temporaire (variable `ESAM_CONFIG`, port 8799), ouvre l'appli dans Chromium (Playwright), prépare les proxies et ouvre l'intervention. À lancer après toute modification de `server.py` ou du mode PC.
- `python tests/fabriquer_rushs.py DOSSIER [--vp9]` : faux rushs seuls. Le Chromium de Playwright ne décode pas le H.264, d'où `--vp9` et le réglage de test `_test_vp9` (proxies en VP9).
- `python tests/test_reel.py` : onglet Réel en mode PC de bout en bout (marqueurs, cadrage, accéléré, musique, réel puis story) et contrôle des fichiers (1080 x 1920, son, stories de 60 s max). Compter 6 à 10 minutes sans carte NVIDIA.
- Mode navigateur : servir le dossier (`python -m http.server`), ouvrir `index.html` et charger des fichiers de `tests` avec `set_input_files('#fileIn', ...)`.
- Vérifier visuellement par capture d'écran en 390x844 (téléphone) et 1400x900 (PC).

## Livraison

- Pousser sur `main` publie le mode navigateur sur https://julok35.github.io/esam-rush/ (GitHub Pages, une à deux minutes).
- Sur le PC de traitement, Julien lance `mettre-a-jour.ps1` (git pull + redémarrage de la tâche « ESAM Derushage »).

## Idées en attente

- Télémétrie : lire les `.SRT` du M30T (heure, GPS 5 décimales, altitudes relative et absolue, focale, zoom, nacelle ; pas de batterie, de signal ni de vitesse) pour afficher altitude, vitesse calculée et distance au décollage, avec incrustation optionnelle dans la compilation. Batterie et signal possibles via un export CSV AirData aligné sur l'heure.
- Durée d'affichage des commentaires internes dans le `.srt` : tout le passage ou quelques secondes (question ouverte).
