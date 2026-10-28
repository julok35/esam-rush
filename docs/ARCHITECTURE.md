# Architecture du dérushage drone ESAM

Document pour un développeur qui découvre le projet. Le guide d'installation et d'utilisation est `LISEZMOI.md` ; les consignes données à l'assistant de code sont dans `CLAUDE.md` et renvoient ici.

## 1. Vue d'ensemble

L'outil annote les rushs d'un secours animalier (drone DJI M30T sur plusieurs caméras, téléphones) et prépare les images pour la communication : fiche de dérushage, vidéo compilée, réel ou story verticale.

Deux fichiers de code, aucune étape de construction, aucune dépendance Python :

| Fichier | Rôle | Taille |
|---|---|---|
| `index.html` | Toute l'appli : HTML, CSS et JavaScript (ES2017, une seule fonction englobante). Mobile d'abord, mise en page large à partir de 1100 px. | environ 4 200 lignes |
| `server.py` | Serveur HTTP du PC de traitement (bibliothèque standard, `ThreadingHTTPServer`), calculs ffmpeg, veille. | environ 870 lignes |
| `vendor/` | mp4box 0.5.3 (lecture des en-têtes MP4), mp4-muxer 5.2.1 (écriture MP4), polices Anton et Montserrat. Servis en local, repli sur jsDelivr si un fichier manque. | 290 Ko |
| `tests/` | Fabrique de faux rushs, tests de bout en bout (Playwright), tests unitaires. | |

Deux modes d'exécution, choisis au chargement par `srvInit()` (appel de `api/status`) :

```
Mode navigateur (GitHub Pages ou fichier ouvert directement)
  téléphone ou PC ──► index.html ──► fichiers choisis par l'utilisateur
                                     décodage WebCodecs, rendu canvas, MP4 écrit par morceaux

Mode PC (PC Windows qui synchronise le Drive ESAM)
  téléphone ──Tailscale (HTTPS)──► server.py (127.0.0.1:8765) ──► Drive : rushs, proxies, fiche, vidéos
                                      │
                                      └─ ffmpeg (NVENC si disponible) : proxies 540p, planches, vidéo, réel
```

Le même `index.html` sert les deux modes. Ce qui diffère est isolé dans un objet `BACKEND` (section 4).

## 2. Carte de `index.html`

Le CSS vient en premier (variables de la charte dans `:root`, mode sombre par `prefers-color-scheme`), puis le HTML (une `<section>` par onglet, trois `<dialog>`), puis le script. Chaque section du script porte un commentaire d'en-tête `/* ---------- nom ---------- */` ; voici l'index.

| Section | Rôle | Fonctions d'entrée |
|---|---|---|
| utils | Formats d'heure, durée, slug, échappement, toast | `clockAbs`, `len`, `esc`, `toast`, `outName` |
| storage, fiche | localStorage, fiche Markdown enregistrée automatiquement | `persist`, `writeFiche`, `restore` |
| loading | Lecture des fichiers choisis, timeline commune | `addFiles`, `parseName`, `rebuild` |
| media | En-têtes MP4 (mp4box), lecture d'échantillons, vignettes WebCodecs | `parseMedia`, `Reader`, `genThumbs`, `canDecode` |
| playback | Lecture du clip de la piste active ; écran maintenu allumé (Wake Lock) pendant la lecture et les calculs | `seek`, `togglePlay`, `setTrack`, `keepAwake` |
| drawing | Timeline, pistes, marqueurs, en-tête, sommaire, chronologie RETEX ; nom de la mission obligatoire avant toute production (`needName`) | `renderTimeline`, `drawStrips`, `renderMarkers`, `renderSummary`, `chrono` |
| markers | Création et édition des marqueurs (dialogue `#sheet`) | `addMarker`, `markStart`, `markEnd`, `openSheet` |
| export / import | Fiche Markdown et sa reprise | `buildMarkdown`, `parseFiche`, `applyFiche` |
| dossier de travail | Import récursif d'un dossier (sauf `proxies` et dossiers cachés) et reprise de sa fiche ; écriture et reprise d'un clic (IndexedDB) avec `showDirectoryPicker` (Chrome, Edge sur ordinateur), lecture seule avec `<input webkitdirectory>` ailleurs (téléphone) | `openDir`, `walkDir`, `importFolder` |
| events | Transport (x16 maintenu, -5 s et +5 s répétés), zoom et pincement, glissement des bords (au doigt : plage sélectionnée par « Ajuster », `SEL`), clavier, onglets, barre de commande fixe en bas sur téléphone (`.ctrl`, hauteur dans `--ctrlh`) | `holdRepeat`, `fastStop`, `setZoom`, `setTab`, `keydown` |
| revue | Dialogue `#rev` : relecture en boucle d'un passage depuis le sommaire (caméra effective, sans marge), nom et caméra modifiables, Précédent / Suivant ; bandes de vignettes des cartes du sommaire | `openReview`, `renderReview`, `revPieces`, `drawFilms` |
| photo | Capture pleine résolution | `captureAt`, `captureLocal`, `decodeFrameAt` |
| compilation | Plan de la vidéo compilée et rendu navigateur | `buildPlan`, `planFor`, `effCam`, `runCompile`, `drawCard`, `drawFrame` |
| dialogue de calcul | Vues Setup / Run / Done du `<dialog id="cmp">`, partagées par la compilation et le réel | `jobRun`, `jobProgress`, `jobDone`, `jobError`, `jobCancel` |
| mode PC | Appels HTTP, liste des interventions, ouverture d'une intervention, suivi d'un calcul | `api`, `srvInit`, `refreshList`, `openRemote`, `loadSheets`, `runRemote`, `pollJob` |
| moteur de calcul | `LOCAL` et `PC`, même interface ; `BACKEND` pointe sur l'un des deux | `BACKEND.saveState`, `.capture`, `.compile`, `.reel`, `.compileFailed`, `.reset` |
| réel et story | Montage vertical 9:16 : plan, calques, aperçu, rendu navigateur, envoi au PC | `reelData`, `reelPlan`, `rLayers`, `drawLayers`, `rDraw`, `rRender`, `runReelLocal`, `runReelRemote` |

Conventions du script :

- Tout le rendu passe par `innerHTML` et des gabarits `\`...\``, avec `esc()` sur toute valeur venant des données. Les gestionnaires d'événements sont posés une fois sur les conteneurs et lisent des attributs `data-*`.
- Les fonctions sont déclarées (`function f(){}`), donc utilisables avant leur définition ; les constantes et l'état sont en `const` et `let`.
- `$("id")` est le seul accès au DOM ; les identifiants HTML sont en camelCase (`rStage`, `cmpInfo`).
- Les messages sont en français ; une alerte dans un texte est entre crochets (`[Fiche non enregistrée : ...]`) et stylée par la classe `miss`.

## 3. Modèle de données

### 3.1 État de l'appli (`S`)

```js
S = {
  clips: [],        // un par fichier : {id, name, size, url, lens, start (heure absolue ou null), dur, ok,
                    //   media (mode navigateur : en-têtes MP4), remote (mode PC), thumbs, sheet, s, e (place sur la timeline)}
  tracks: [],       // une par caméra : {lens, name, clips}, triées par ORDER (W, Z, T, V, N, S, autres)
  active: 0,        // piste affichée
  t: 0,             // instant courant, en secondes depuis S.base
  base: 0,          // heure absolue (secondes Unix) du début de la timeline ; 0 si aucun fichier n'est daté
  dur: 0,           // durée de la timeline
  real: true,       // true : les heures affichées sont des heures réelles ; false : relatives (00:00:00)
  markers: [],      // voir 3.2
  meta: {intervention, version, log, auteur, reel},   // version et log : changelog de la fiche
  offsets: {},      // décalage manuel par caméra, en secondes (calage des pistes)
  key: null,        // empreinte des fichiers chargés : clé localStorage
  dirHandle: null   // dossier des rushs ouvert par showDirectoryPicker
}
```

Caméras (`LENS`) : lettre finale du nom DJI `DJI_AAAAMMJJHHMMSS_NNNN_X` : W grand angle, Z zoom, T thermique, S écran ; V et N réservés ; `?` pour tout autre fichier (téléphone). L'heure de début vient du nom DJI (heure locale) ou, à défaut, de `creation_time` du conteneur (UTC, converti). Sans nom DJI (galerie Android, qui renomme en `1000012345.mp4`), `autoLens()` devine la piste : image 5:4 = thermique, et deux fichiers qui se chevauchent vont sur des pistes distinctes (`?`, `?2`, ...).

### 3.2 Marqueur

```js
{id, at, to,          // heures absolues ; to = null pour un repère
 preset, title,       // nom choisi dans PRESETS (numéroté pour Décollage, Atterrissage, Fausse piste, Bonne piste) ou titre libre
 themes: [],          // THEMES, plusieurs possibles
 interest: 0,         // 0 à 3 (INTEREST)
 sens: ["Aucune"],    // SENS : sensibilités avant diffusion
 note: "",            // texte du carton, visible dans la vidéo compilée
 comment: "",         // commentaire interne, jamais incrusté : fichier .srt à part
 cam: "W"}            // caméra souhaitée pour la compilation ; effCam(m) rend la caméra réellement utilisée
```

### 3.3 Réglages du réel (`S.meta.reel`)

```js
{items: [            // montage, dans l'ordre
   {id,              // id du marqueur ; "ph..." pour une photo
    a, z,            // plage en secondes de timeline (passage)
    cam, vit,        // caméra, vitesse 1 à 8
    keys: [{t, x}],  // cadrage : position horizontale du cadre (0 à 1) par instant, lissée (rKeyAt)
    photo, dur, x, zoom,         // photo : chemin relatif, durée, cadrage, zoom lent
    texte, tBox: {x, y, s, c, fond}, tDur,   // texte du passage, sa boîte, sa durée (0 = tout le passage)
    flous: [{id, s, keys: [{t, x, y}]}]}],   // zones de flou doux, en fraction de l'image source
 titre, titreDur, titreBox: {x, y, s, c},
 elems: [{id, kind: "texte"|"fleche"|"cercle"|"cadre", a, d, x, y, s, rot, c, texte, fond}],  // temps du réel
 logo: {mode: "cartouche"|"logo"|"non", x, y, s},
 fin: {on, texte, sous},
 musique: {nom, fichier}, musDebut}
```

Les positions `x`, `y` sont des fractions de l'image (0 à 1), `s` un facteur de taille, `c` une couleur de `RCOLS`. `reelData()` complète les champs manquants, ce qui permet d'ajouter un réglage sans migration.

### 3.4 Persistance

| Où | Quoi | Quand |
|---|---|---|
| localStorage `esam-derush:<clé>` | `{markers, meta, offsets}` | à chaque `persist()` |
| localStorage `esam-auteur` | auteur des commentaires | à la saisie |
| `.derushage/etat.json` (mode PC) | `{markers, meta, offsets}` | `persist()`, 0,7 s après la dernière modification |
| `ESAM_Derushage_<date>_<mission>.md` | fiche lisible + bloc `<!-- derushage-data {...} -->` | 1,5 s après la dernière modification (PC ou dossier ouvert) |

Reprendre une fiche remplace les marqueurs (pas de fusion) ; l'opération est annulable par le toast. Le bloc `derushage-data` contient `{app, v, base, real, meta, offsets, markers, files}`.

## 4. Les deux moteurs (`BACKEND`)

`LOCAL` et `PC` exposent la même interface ; `BACKEND = LOCAL` au chargement, `BACKEND = PC` dès que `api/status` répond.

| Méthode | LOCAL (navigateur) | PC |
|---|---|---|
| `saveState()` | rien de plus que localStorage | `POST api/etat` |
| `capture(tr, t)` | `captureLocal` : WebCodecs, puis téléchargement | `captureRemote` : `POST api/photo` (clip du PC), sinon `captureLocal` |
| `compile()` | `runCompile` : WebCodecs + mp4-muxer | `runRemote` : cartons rendus en PNG, `POST api/video`, `pollJob` |
| `reel(story)` | `runReelLocal` : `rRender` par morceaux de story | `runReelRemote` : calques PNG, `POST api/reel`, `pollJob` |
| `compileFailed(msg)` | erreur dans le dialogue | retour à la vue Setup et toast |
| `reset()` | rien | retour à la liste des interventions |

Le reste du code appelle `BACKEND.x()` sans tester le mode. `pcOpen()` (une intervention est ouverte sur le PC) sert aux quelques textes et chemins qui dépendent du mode (photos, musique).

Dialogue de calcul : `jobRun(message, W, H)` ouvre la vue de progression et rend le canvas d'aperçu ; `jobProgress(fraction, texte)` ; `jobDone({info, url, saveLabel, onSave, onBack})` ou `jobError(message, onBack)` affichent le résultat. Les boutons « Enregistrer » et « Recommencer » exécutent les fonctions passées, ce qui évite tout drapeau global sur ce qui est affiché.

## 5. API HTTP de `server.py`

Toutes les réponses sont en JSON sauf les fichiers. Une erreur de validation rend `{"erreur": "..."}` en 400, une erreur interne en 500. `d` est toujours le nom d'un sous-dossier du dossier des rushs, vérifié par `folder()` (ni séparateur, ni `..`, ni point initial).

| Méthode et route | Entrée | Sortie |
|---|---|---|
| `GET /`, `/index.html` | | la page (jamais mise en cache) |
| `GET /vendor/<nom>` | nom de fichier simple | bibliothèque ou police |
| `GET /api/status` | | `{ok, version, racine, racine_ok, gpu, travaux: [calcul], veille: {mode, minutes}}` |
| `GET /api/interventions` | | `{interventions: [{nom, videos, proxies, fiche, compilation, maj}]}` |
| `GET /api/manifest?d=` | | `{dossier, clips: [{nom, dur, w, h, codec, cree, proxy, thumbs: {sheets, tw, th, cols, rows, every, count}}], photos: [{nom, heure}]}` |
| `GET /api/image?d=&f=&taille=` | `taille` = `petite` (360 px) ou `moyenne` (3200 px) | JPEG redressé selon l'EXIF, gardé dans `proxies/photos` |
| `GET /api/etat?d=` | | contenu de `.derushage/etat.json` ou `{}` |
| `GET /files/<dossier>/<chemin>` | | fichier des rushs (proxies, planches, musique), requêtes Range acceptées |
| `POST /api/proxies` | `{d}` | le calcul créé ou déjà en cours |
| `POST /api/video` | `{d, format: "h"|"v", nom, titre, auteur, logo, ouverture: {image, duree}, passages: [{image, duree, titre, nom_passage, commentaire, morceaux: [{fichier, debut, fin}]}]}` (images en data URL PNG) | le calcul créé |
| `POST /api/reel` | `{d, mode: "reel"|"story", nom, titre_video, segments: [...], calques: [{image, debut, fin, fi, fo}], fin: {image, duree} ou null, musique: {fichier, debut} ou null, story_max}` ; un segment est `{type: "photo", image, duree, zoom, nom}` ou `{type: "video", vitesse, nom, morceaux: [{fichier, debut, fin, cles: [{t, x}], flous: [{s, cles: [{t, x, y}]}]}]}` | le calcul créé |
| `POST /api/annuler` | `{id}` | `{ok}` |
| `POST /api/etat` | `{d, etat}` | `{ok}` |
| `POST /api/fiche` | `{d, nom, md}` ; supprime les autres `ESAM_Derushage_*.md` du dossier | `{ok, fichier}` |
| `POST /api/photo` | `{d, fichier, t}` | `{ok, fichier: "Photos/..."}` |
| `POST /api/musique?d=&nom=` | corps brut (60 Mo au plus, mp3, m4a, aac, wav, ogg, flac) | `{ok, fichier: "musique.<ext>"}` |

Un calcul (`travaux.json`, 30 derniers conservés) :

```json
{"id": "18c3f2a9b1e", "type": "proxies|video|reel", "dossier": "...", "etat": "attente|en_cours|termine|erreur|annule|interrompu",
 "avance": 0.42, "libelle": "Extrait 3 sur 8 : DJI_...MP4", "erreur": null, "resultat": {...}, "debut": 1760000000.0}
```

Un seul fil `worker()` exécute les calculs dans l'ordre. L'annulation pose `job["cancel"]`, lue entre deux lignes de progression ffmpeg ; le processus est tué. Au redémarrage, un calcul resté en `attente` ou `en_cours` passe à `interrompu`.

Sécurité : le serveur n'écoute que sur 127.0.0.1 ; Tailscale fournit HTTPS et l'authentification. Il n'y a pas d'autre contrôle d'accès.

## 6. Fichiers produits

Dans le dossier de l'intervention (voir aussi le tableau de `LISEZMOI.md`) :

| Élément | Produit par |
|---|---|
| `proxies/<rush>.mp4`, `proxies/<rush>.thumbs_NNN.jpg`, `proxies/<rush>.json` | `do_proxies` : proxy 540p sans son, planches 10 x 10 de vignettes de 90 px de haut toutes les 3 s, métadonnées |
| `proxies/photos/` | copies redressées des photos (`photo_copy`) |
| `.derushage/etat.json`, `.derushage/musique.<ext>` | `api/etat`, `api/musique` |
| `ESAM_Derushage_<date>_<mission>.md` | `api/fiche` (ou le dossier des rushs en mode navigateur) |
| `Photos/ESAM_<rush>_<instant>.jpg` | `api/photo` |
| `ESAM_Compilation_<date>_<mission>[_vertical].mp4`, `.commentaires-ESAM.srt`, `_chapitres.txt` | `do_video` |
| `ESAM_Reel_<date>_<mission>.mp4`, `ESAM_Story_<date>_<mission>[_NsurM].mp4` | `do_reel` |

Le nom de base est construit par `outName()` côté appli (`ESAM_<préfixe>_<date du vol>[_<slug de la mission>]`) et nettoyé par `server.py` (caractères interdits sous Windows).

## 7. Ce qui existe en double, à dessein

Deux moteurs de rendu imposent quelques calculs en miroir. Chaque paire porte un commentaire qui nomme son jumeau ; `tests/test_unitaire.py` vérifie que les découpes de story coïncident.

| Appli (`index.html`) | PC (`server.py`) | Objet |
|---|---|---|
| `storyCuts` | `story_cuts` | instants de coupe d'une story (60 s au plus, à une limite de passage) |
| `rKeyAt` | `key_expr` | lissage en S entre les points de cadrage et de flou |
| `softBlur` | `blur_chain`, `blur_mask` | flou gaussien dans une ellipse aux bords fondus |
| `rCrop` | `crop_box` | cadre 9:16 dans l'image source |
| `buildSrt` | bloc SRT de `do_video` | commentaires internes en sous-titres |
| `outName` | nettoyage des noms dans `do_video`, `do_reel` | noms des fichiers produits |

## 8. Conventions du projet

- Interface, messages, commentaires et documentation en français. Tiret simple uniquement (jamais U+2013 ni U+2014), y compris dans les noms de fichiers ; vérifier avant chaque commit :
  `python -c "import sys;[print(f, open(f,encoding='utf-8').read().count(chr(0x2014))+open(f,encoding='utf-8').read().count(chr(0x2013))) for f in sys.argv[1:]]" index.html server.py LISEZMOI.md README.md CLAUDE.md docs/ARCHITECTURE.md`
- Version : `APP_VERSION` (`index.html`), `VERSION` (`server.py`) et le frontmatter de `LISEZMOI.md` évoluent ensemble, avec une ligne de changelog orientée utilisateur. Le badge passe au jaune si l'appli et le PC diffèrent.
- Réglages du PC : `config.json` (propre à chaque PC, ignoré par git) ; tout nouveau réglage va dans `config.exemple.json` avec sa valeur par défaut, et `server.py` le lit par `CFG.get`.
- Les commentaires internes ne sont jamais incrustés dans une vidéo : elle doit rester publiable telle quelle.
- Mobile d'abord (téléphone en portrait, 390 px), mise en page large à partir de 1100 px. Charte : Anton pour les titres, Montserrat pour le texte, couleurs de `:root`.
- Jamais de sortie vidéo accumulée en mémoire : écriture par morceaux (OPFS ou Blob).
- Livraison : pousser sur `main` publie le mode navigateur sur GitHub Pages ; sur le PC, `mettre-a-jour.ps1` fait `git pull` et redémarre la tâche planifiée.

## 9. Tester

| Commande | Ce qu'elle fait | Durée |
|---|---|---|
| `python tests/test_unitaire.py` | fonctions pures de `server.py` et miroir `storyCuts` / `story_cuts` (Playwright sur `index.html` en `file://`) | 10 s |
| `python tests/test_fumee.py` | faux rushs, serveur sur le port 8799, appli dans Chromium, préparation des proxies, ouverture | 1 min |
| `python tests/test_reel.py` | onglet Réel de bout en bout en mode PC, réel puis story, contrôle des fichiers (1080 x 1920, son, 60 s au plus) | 6 à 10 min sans NVIDIA |
| `python tests/fabriquer_rushs.py DOSSIER [--vp9]` | faux rushs seuls ; `--vp9` pour le Chromium de Playwright, qui ne décode pas le H.264 (réglage `_test_vp9` du serveur) | |
| `python tests/fabriquer_longue.py DOSSIER` | intervention de 3 h sur 4 caméras, déjà préparée (planches seules), pour mesurer la mémoire | |

Prérequis : ffmpeg, `pip install playwright` et `playwright install chromium`. Les tests créent leur propre `config.json` temporaire (variable `ESAM_CONFIG`) et ne touchent pas au vôtre. L'heure des faux rushs est locale : les tests supposent le fuseau du PC de traitement (Europe/Paris) ; sous un autre fuseau, lancer avec `TZ=Europe/Paris`.

Vérification visuelle : captures en 390 x 844 (téléphone) et 1400 x 900 (PC). Mode navigateur : servir le dossier (`python -m http.server`), ouvrir `index.html` et charger des fichiers de test avec `set_input_files('#fileIn', ...)`.

## 10. Mesures de référence (v0.12)

Intervention factice de 3 h sur 4 caméras (`fabriquer_longue.py`), mode PC, Chromium headless, viewport téléphone :

| | v0.11 (un ImageBitmap par vignette) | v0.12 (planches dessinées par sous-rectangles) |
|---|---|---|
| Ouverture de l'intervention jusqu'aux vignettes prêtes | 152 s | 2 s |
| Mémoire du navigateur en plus de la page vide | 997 Mo | 636 Mo |

La mémoire restante est le cache des planches décodées, que le navigateur peut libérer sous pression (contrairement aux ImageBitmap).

## 11. Limites connues et idées

- Chapitres du MP4 lus par VLC et QuickTime, pas par l'aperçu de Google Drive ; produits en mode PC seulement.
- Pas de son dans la vidéo compilée ; heure incrustée en mode navigateur seulement (elle figure sur les cartons en mode PC).
- Lecture à x16 limitée par le débit montant de la connexion du PC.
- Idée : télémétrie des `.SRT` du M30T (GPS, altitudes, focale) pour afficher altitude, vitesse et distance, avec incrustation optionnelle.
- Question ouverte : durée d'affichage des commentaires internes dans le `.srt` (tout le passage ou quelques secondes).
