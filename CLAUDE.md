# Consignes pour Claude Code

Projet : outil de dérushage des vidéos drone de l'ESAM (secours animalier en montagne). Utilisateur principal : Julien, pilote drone bénévole ; destinataires des sorties : l'équipe communication. Toute l'interface, les messages et la documentation sont en français.

**Lire d'abord `docs/ARCHITECTURE.md`** : vue d'ensemble, carte de `index.html`, modèle de données (`S`, marqueurs, `S.meta.reel`), moteurs `LOCAL` et `PC` (`BACKEND`), API HTTP de `server.py`, fichiers produits, calculs en miroir, conventions et tests. Ce fichier ne répète que les règles à appliquer à chaque changement.

## Règles à chaque changement

- **Tirets** : jamais de tiret cadratin (U+2014) ni demi-cadratin (U+2013), ni dans le code, ni dans les textes, ni dans les noms de fichiers. Tiret simple uniquement. Dans `server.py`, les écrire en échappement (`"\u2014"`) quand il faut les détecter. Vérifier avant chaque commit :
  `python -c "import sys;[print(f, open(f,encoding='utf-8').read().count(chr(0x2014))+open(f,encoding='utf-8').read().count(chr(0x2013))) for f in sys.argv[1:]]" index.html server.py LISEZMOI.md README.md CLAUDE.md docs/ARCHITECTURE.md`
- **Version** : à chaque changement livré, incrémenter ensemble `APP_VERSION` dans `index.html` et `VERSION` dans `server.py` (le badge passe au jaune si elles diffèrent), puis `version`/`date_maj` du frontmatter de `LISEZMOI.md` et une ligne dans son Changelog (succincte, orientée utilisateur).
- Les commentaires internes ESAM ne doivent jamais être incrustés dans la vidéo compilée (fichier `.srt` à part) : la vidéo doit rester publiable telle quelle.
- `config.json` est propre à chaque PC et ignoré par git ; les nouveaux réglages vont dans `config.exemple.json` avec une valeur par défaut, et `server.py` doit fonctionner s'ils sont absents (`CFG.get`).
- Mobile d'abord (téléphone en portrait), mais la mise en page PC doit exploiter l'écran large. Respecter la charte ESAM existante dans `index.html` (polices Anton et Montserrat embarquées dans `vendor/`, couleurs de `:root`).
- Pas de framework, pas de build : `index.html` reste un seul fichier (ES2017, une fonction englobante), `server.py` reste en bibliothèque standard. Les bibliothèques tierces vont dans `vendor/` avec leur version dans le nom de fichier.
- Le mode PC ne se greffe pas par remplacement de fonctions : ce qui diffère entre navigateur et PC va dans `LOCAL` ou `PC` (même interface), le reste appelle `BACKEND`.
- Un calcul qui existe à la fois dans l'appli et dans `server.py` (liste dans `docs/ARCHITECTURE.md`, section 7) porte un commentaire « miroir de ... » des deux côtés.

## Points délicats déjà rencontrés

- Vidéos de téléphone en portrait : matrice de rotation à appliquer (vignettes et compilation). Heure de début prise dans `creation_time` (UTC).
- Vidéos DJI : heure de début lue dans le nom de fichier `DJI_AAAAMMJJHHMMSS_NNNN_X`, X = W (grand angle), Z (zoom), T (thermique), S (écran).
- Une compilation de plusieurs Go dans le navigateur plantait à 100 % : ne jamais accumuler la sortie en mémoire.
- La caméra compilée pour un passage est `effCam(m)` : le choix `m.cam` s'il a de l'image, sinon la première caméra disponible.
- Mode PC : une vignette est une case d'une planche JPEG (`{img, sx, sy, w, h}`), jamais un ImageBitmap par vignette (152 s d'ouverture et 1 Go sur 3 h de rushs). Dessiner avec `drawThumb`, mesurer avec `tests/fabriquer_longue.py`.
- Les tests de bout en bout supposent le fuseau Europe/Paris (heure des faux rushs) : `TZ=Europe/Paris python tests/test_reel.py` ailleurs.

## Tester

- `python tests/test_unitaire.py` après toute modification de `server.py` ou des calculs en miroir.
- `python tests/test_fumee.py` après toute modification de `server.py` ou du mode PC.
- `python tests/test_reel.py` après toute modification de l'onglet Réel (6 à 10 minutes sans carte NVIDIA).
- Vérifier visuellement par capture d'écran en 390x844 (téléphone) et 1400x900 (PC) ; mode navigateur : servir le dossier (`python -m http.server`), ouvrir `index.html` et charger des fichiers de `tests` avec `set_input_files('#fileIn', ...)`.

## Livraison

- Pousser sur `main` publie le mode navigateur sur https://julok35.github.io/esam-rush/ (GitHub Pages, une à deux minutes).
- Sur le PC de traitement, Julien lance `mettre-a-jour.ps1` (git pull + redémarrage de la tâche « ESAM Derushage »).
