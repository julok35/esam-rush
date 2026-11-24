# Architecture du dérushage drone ESAM

Document pour un développeur qui découvre le projet. Le guide d'installation et d'utilisation est `LISEZMOI.md` ; les consignes données à l'assistant de code sont dans `CLAUDE.md` et renvoient ici.

## 1. Vue d'ensemble

L'outil annote les rushs d'un secours animalier (drone DJI M30T sur plusieurs caméras, téléphones) et prépare les images pour la communication : fiche de dérushage, vidéo compilée, extraits bruts, réel ou story verticale, vidéo LinkedIn (4:5 ou carrée), avec les retouches de chaque passage (flous suivis, flèches, cercles, vitesse).

Deux fichiers de code, aucune étape de construction, aucune dépendance Python :

| Fichier | Rôle | Taille |
|---|---|---|
| `index.html` | Toute l'appli : HTML, CSS et JavaScript (ES2017, une seule fonction englobante). Mobile d'abord, mise en page large à partir de 1100 px. | environ 5 800 lignes |
| `server.py` | Serveur HTTP du PC de traitement (bibliothèque standard, `ThreadingHTTPServer`), calculs ffmpeg, veille. | environ 1 020 lignes |
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

Le CSS vient en premier (variables de la charte dans `:root`, mode sombre par `prefers-color-scheme` ou par le réglage de thème, qui pose `data-theme` sur `<html>`), puis le HTML (une `<section role="tabpanel">` par onglet dans `<main>`, cinq `<dialog>` (fiche de marqueur `#sheet`, fiche à copier `#fallback`, aide `#help`, retouches `#fx`, calcul `#cmp`)), puis le script. Le CSS se termine par un bloc « fondations » : variables transversales (`--ctl`, `--ring`, `--tap`, `--stage`...), anneau de focus, désactivé, appui, cibles tactiles, et les règles transversales qui visent un composant d'une autre partie. Chaque section du script porte un commentaire d'en-tête `/* ---------- nom ---------- */` ; voici l'index.

| Section | Rôle | Fonctions d'entrée |
|---|---|---|
| utils | Formats d'heure, durée, slug, échappement, toast | `clockAbs`, `len`, `esc`, `toast`, `outName` |
| storage, fiche | localStorage, fiche Markdown enregistrée automatiquement | `persist`, `writeFiche`, `restore` |
| loading | Lecture des fichiers choisis, timeline commune | `addFiles`, `parseName`, `rebuild` |
| media | En-têtes MP4 (mp4box), lecture d'échantillons, vignettes WebCodecs | `parseMedia`, `Reader`, `genThumbs`, `canDecode` |
| playback | Lecture du clip de la piste active ; `seek` recharge le fichier après une erreur de lecture | `seek`, `togglePlay`, `setTrack` |
| drawing | Timeline, pistes, marqueurs, en-tête, sommaire, chronologie RETEX | `renderTimeline`, `drawStrips`, `renderMarkers`, `renderSummary`, `chrono` |
| markers | Création et édition des marqueurs (dialogue `#sheet` : noms courants `PRESET_MAIN`, autres noms `PRESET_MORE`) ; suppression annulable, qui rétablit aussi l'élément du réel ; bandeau `#inWin` à hauteur fixe (passage en cours, passage ou repère sous la tête de lecture) | `addMarker`, `markStart`, `markEnd`, `openSheet`, `renderInWin` |
| export / import | Fiche Markdown et sa reprise | `buildMarkdown`, `parseFiche`, `applyFiche` |
| dossier de travail | Import récursif d'un dossier (sauf `proxies` et dossiers cachés) et reprise de sa fiche ; écriture et reprise d'un clic (IndexedDB) avec `showDirectoryPicker` (Chrome, Edge sur ordinateur), lecture seule avec `<input webkitdirectory>` ailleurs (téléphone) | `openDir`, `walkDir`, `importFolder` |
| events | Transport, zoom et pincement, glissement sur la règle et des bords (aperçu de vignette `#scrubPrev`, ouvert et fermé par `showPrev`, `hidePrev`, `releasePrev` seulement), raccourcis clavier, onglets, retour à la liste ou à l'accueil (`#home`, `#reset`) | `setZoom`, `setTab`, `keydown`, `goHome` |
| clavier, onglets, thème | Garde commune des raccourcis (champs, listes, boutons atteints au clavier), boutons de choix de fichier, onglets au clavier (flèches, Début, Fin), hauteur du lecteur collant pour le focus, réglage du thème | `keyTaken`, `syncTabs`, `applyTheme` |
| planche | Grille de vignettes | `renderBoard`, `drawTile` |
| photo | Capture pleine résolution | `captureAt`, `captureLocal`, `decodeFrameAt` |
| retouches | Flous suivis, flèches et cercles, vitesses d'un passage (`m.fx`) : dessin, découpe par vitesse, description pour le PC | `fxGet`, `fxMake`, `fxApply`, `fxSplit`, `fxVitAt`, `fxPayload`, `fxSprite`, `drawFxShape` |
| compilation | Plan de la vidéo compilée ou des extraits bruts (`cmpHab`) et rendu navigateur | `buildPlan`, `planFor`, `effCam`, `runCompile`, `drawCard`, `drawFrame` |
| dialogue de calcul | Vues Setup / Run / Done du `<dialog id="cmp">`, partagées par la compilation et le réel | `jobRun`, `jobProgress`, `jobDone`, `jobError`, `jobCancel` |
| mode PC | Appels HTTP, liste des interventions (filtre au-delà de 8 dossiers), ouverture d'une intervention, suivi d'un calcul | `api`, `srvInit`, `refreshList`, `renderIvList`, `openRemote`, `loadSheets`, `runRemote`, `pollJob` |
| accueil et aide | Rappel du travail gardé dans le navigateur (mode navigateur) ; aide par onglet (`<dialog id="help">`, bouton Aide ou badge de version) | `renderResume`, `openHelp` |
| moteur de calcul | `LOCAL` et `PC`, même interface ; `BACKEND` pointe sur l'un des deux | `BACKEND.saveState`, `.capture`, `.compile`, `.reel`, `.compileFailed`, `.reset` |
| réel et story | Montage court au format `RFMTS` (9:16, LinkedIn 4:5 ou 1:1 ; `RW` x `RH` posés par `reelData`) : plan, calques, aperçu, rendu navigateur, envoi au PC ; flou d'une zone (`softBlur`) | `reelData`, `reelPlan`, `rLayers`, `drawLayers`, `rDraw`, `rRender`, `runReelLocal`, `runReelRemote` |
| éditeur de retouches | Dialogue `#fx` : image du passage, éléments à glisser, réglages, vitesses ; suivi au doigt et suivi automatique | `fxOpen`, `fxDraw`, `fxPanel`, `fxSeek`, `fxTrackStart`, `fxTrackFrame`, `fxSimplify` |

Conventions du script :

- Tout le rendu passe par `innerHTML` et des gabarits `\`...\``, avec `esc()` sur toute valeur venant des données. Les gestionnaires d'événements sont posés une fois sur les conteneurs et lisent des attributs `data-*`.
- Les fonctions sont déclarées (`function f(){}`), donc utilisables avant leur définition ; les constantes et l'état sont en `const` et `let`.
- `$("id")` est le seul accès au DOM ; les identifiants HTML sont en camelCase (`rStage`, `cmpInfo`).
- Les messages sont en français ; une alerte dans un texte est entre crochets (`[Fiche non enregistrée : ...]`) et stylée par la classe `miss`.
- Couleurs : toujours une variable. `--line` pour les séparateurs décoratifs, `--ctl` pour le bord d'un contrôle (3:1), `--onblue` pour l'encre fixe sur bleu ou jaune, `--stage` et `--onstage` pour la scène vidéo ; les couleurs dessinées dans les vidéos produites restent en dur dans le script.
- Clavier : tout nouveau raccourci passe par `keyTaken(e)` ; un champ fichier reste invisible (`tabindex="-1"`) et s'ouvre par un `label.btn`, rendu focalisable par le script.
- Un dialogue modal recouvre la page : `toast()` range le message dans le dialogue ouvert du dessus (`toastHost`), sinon il serait invisible.

## 3. Modèle de données

### 3.1 État de l'appli (`S`)

```js
S = {
  clips: [],        // un par fichier : {id, name, size, url, lens, start (heure absolue ou null), dur, ok,
                    //   media (mode navigateur : en-têtes MP4), remote (mode PC), thumbs, sheet, s, e (place sur la timeline)}
  tracks: [],       // une par caméra : {lens, name, clips}, triées par ORDER (S, W, Z, T, V, N, autres) ; caméra par défaut : CAM_PRIO
  active: 0,        // piste affichée
  t: 0,             // instant courant, en secondes depuis S.base
  base: 0,          // heure absolue (secondes Unix) du début de la timeline ; 0 si aucun fichier n'est daté
  dur: 0,           // durée de la timeline
  real: true,       // true : les heures affichées sont des heures réelles ; false : relatives (00:00:00)
  markers: [],      // voir 3.2
  meta: {intervention, version, log, auteur, reel, pistes},   // version et log : changelog de la fiche ; pistes : 2 une fois les pistes d'avant la v0.19 migrées
  offsets: {},      // décalage manuel par caméra, en secondes (calage des pistes)
  key: null,        // empreinte des fichiers chargés : clé localStorage
  dirHandle: null   // dossier des rushs ouvert par showDirectoryPicker
}
```

Caméras (`LENS`) : lettre finale du nom DJI `DJI_AAAAMMJJHHMMSS_NNNN_X` : W grand angle, Z zoom, T thermique, S écran ; V et N réservés ; `?` pour tout autre fichier (téléphone). Deux ordres distincts : `ORDER` pour l'affichage des pistes (écran en premier), `CAM_PRIO` pour la caméra prise quand le choix d'un passage n'a pas d'image (`tracksByCam`, utilisé par `camsFor`, `planFor`, `rTrack`). L'heure de début vient du nom DJI (heure locale) ou, à défaut, de `creation_time` du conteneur (UTC, converti). Sans nom DJI (téléphone, ou galerie Android qui renomme en `1000012345.mp4`), `autoLens()` devine la piste : image 5:4 = thermique ; appareil connu = une piste par appareil (`@<slug>`, nommée par `devName` : « iPhone 15 Pro », « Google Pixel 7 », d'après la marque et le modèle lus dans le fichier par `mp4Device` en mode navigateur ou `device()` de `server.py` en mode PC ; ignoré pour DJI) ; sinon `?` (« Autre caméra », vidéo repassée par une messagerie). Deux fichiers qui se chevauchent vont sur des pistes distinctes (`?2`, `@Pixel_7_2`...). Une vidéo produite par l'outil (`PROD_RE`) garde la piste `?` pour elle seule (« Vidéo montée »). Les fiches d'avant la v0.19 (`S.meta.pistes` absent) nommaient ces pistes `?`, `?2`... : `migrateCams` et `migrateOffsets` reportent une fois caméras des passages, retouches, réel et calage sur les nouvelles pistes.

### 3.2 Marqueur

```js
{id, at, to,          // heures absolues ; to = null pour un repère
 preset, title,       // nom choisi dans PRESETS (numéroté pour Décollage, Atterrissage, Fausse piste, Bonne piste) ou titre libre
 themes: [],          // THEMES, plusieurs possibles
 interest: 0,         // 0 à 3 (INTEREST)
 sens: ["Aucune"],    // SENS : sensibilités avant diffusion
 note: "",            // texte du carton, visible dans la vidéo compilée
 comment: "",         // commentaire interne, jamais incrusté : fichier .srt à part
 cam: "W",            // caméra souhaitée pour la compilation ; effCam(m) rend la caméra réellement utilisée
 fx: {flous, formes, vits}}   // retouches du passage, absentes tant qu'il n'y en a pas : voir 3.3
```

### 3.3 Retouches d'un passage (`m.fx`)

Les retouches appartiennent au passage, pas à une vidéo produite : la vidéo compilée, les extraits, le réel et la story les reçoivent toutes. Les temps sont en secondes de timeline (comme `S.t`), les positions en fraction de l'image source d'une caméra.

```js
{flous: [{id, cam,                   // caméra (lens) sur laquelle la zone est posée ; appliquée seulement à cette caméra
          forme: "ellipse"|"rect",   // visage ou plaque
          mode: "doux"|"pixel",      // flou gaussien ou mosaïque, bords fondus dans les deux cas
          s, ar,                     // hauteur en fraction de la hauteur d'image, largeur = hauteur x ar
          keys: [{t, x, y}]}],       // centre suivi, lissé par rKeyAt (un seul point : zone fixe)
 formes: [{id, cam, kind: "fleche"|"cercle",
           s, rot, c, ar,            // taille, orientation en degrés, couleur de RCOLS, largeur du cercle
           a, z,                     // plage d'affichage (absents : tout le passage)
           keys: [{t, x, y}]}],      // point visé par la pointe de la flèche, centre du cercle
 vits: [{t, v}],                    // changements de vitesse : v (0.25 à 8) à partir de t, jusqu'au changement suivant
 t0}                                 // heure absolue de l'origine de la timeline (S.base) quand ces temps ont été écrits
```

- `fxGet` et `fxMake` passent par `fxNorm` : si `S.base` a changé depuis l'écriture (fichier plus ancien ajouté, fiche reprise sur d'autres fichiers), tous les temps sont recalés une fois. Un flou ne doit jamais glisser dans le temps.

- `fxApply(ctx, m, lens, t, g)` dessine flous puis formes sur un canevas où l'image source occupe `g = {x0, y0, k, sw, sh}` : aperçus, rendu navigateur de la compilation (`drawFrame`) et du réel (`drawCropped`).
- `fxSplit(m, morceaux, mult)` recoupe les morceaux d'un passage (un par fichier) aux changements de vitesse ; chaque morceau porte `vit`. La compilation (`planFor`) et le réel (`reelPlan`, où `mult` est l'accéléré du réel) rendent donc un morceau à vitesse constante. Un changement posé au début du passage vaut aussi pour la marge qui le précède (`fxVitAt`).
- `fxPayload(m, lens, morceau, sprites)` décrit au PC les flous et les formes d'un morceau, points de suivi ramenés au début du morceau. Une forme est dessinée une fois par l'appli (`fxSprite`, PNG transparent prévu pour une image source de `ref` pixels de haut) : le tracé « au crayon » est ainsi le même dans le navigateur et sur le PC.
- Suivi automatique (`fxTrackStart`) : la vidéo est lue à vitesse normale ; à chaque image présentée (`requestVideoFrameCallback`), le motif en niveaux de gris de la zone est recherché autour de sa position précédente dans une copie de 640 px de large (écart moyen, moyennes retirées), le motif s'adapte doucement, et un point est posé tous les 0,2 s. Dix images sans retrouver le motif arrêtent le suivi. À la fin, `fxSimplify` ne garde que les points qui changent la trajectoire lissée.
- Les flous d'une photo du réel restent sur l'élément du réel (`it.flous`, même format sans `cam`). Les réels d'avant la v0.17 rangeaient aussi là les flous des passages vidéo : `reelData()` les déplace dans `m.fx`.

### 3.4 Réglages du réel (`S.meta.reel`)

```js
{fmt,                // format de sortie : "reel" (9:16, réel ou story), "li" (4:5) ou "carre" (1:1), voir RFMTS
 items: [            // montage, dans l'ordre
   {id,              // id du marqueur ; "ph..." pour une photo
    a, z,            // plage en secondes de timeline (passage)
    cam, vit,        // caméra, accéléré du réel 1 à 8 (multiplie les vitesses des retouches du passage)
    keys: [{t, x}],  // cadrage : position horizontale du cadre (0 à 1) par instant, lissée (rKeyAt)
    photo, dur, x, zoom,         // photo : chemin relatif, durée, cadrage, zoom lent
    texte, tBox: {x, y, s, c, fond}, tDur,   // texte du passage, sa boîte, sa durée (0 = tout le passage)
    flous: [{id, s, keys: [{t, x, y}]}]}],   // photo seulement : zones de flou, en fraction de l'image (passage vidéo : m.fx)
 titre, titreDur, titreBox: {x, y, s, c, haut},   // haut : y est le bord haut du titre (sinon son centre, réels plus anciens)
 elems: [{id, kind: "texte"|"fleche"|"cercle"|"cadre", a, d, x, y, s, rot, c, texte, fond}],  // temps du réel
 logo: {mode: "cartouche"|"logo"|"non", x, y, s},
 fin: {on, texte, sous},
 musique: {nom, fichier}, musDebut}
```

Les positions `x`, `y` sont des fractions de l'image (0 à 1), `s` un facteur de taille, `c` une couleur de `RCOLS`. `reelData()` complète les champs manquants, ce qui permet d'ajouter un réglage sans migration.

### 3.5 Persistance

| Où | Quoi | Quand |
|---|---|---|
| localStorage `esam-derush:<clé>` | `{markers, meta, offsets}` | à chaque `persist()` |
| localStorage `esam-auteur` | auteur des commentaires | à la saisie |
| localStorage `esam-theme` | thème choisi (`light` ou `dark`, absent : automatique) | au réglage (Plus d'options) |
| `.derushage/etat.json` (mode PC) | `{markers, meta, offsets}` | `persist()`, 0,7 s après la dernière modification |
| `.derushage/etat-compil.json` (mode PC) | la même chose pour une vidéo compilée rouverte comme source (`SRVS = "compil"`), sans fiche | idem |
| `ESAM_Derushage_<date>_<mission>.md` | fiche lisible + bloc `<!-- derushage-data {...} -->` | 1,5 s après la dernière modification (PC ou dossier ouvert) |

Reprendre une fiche remplace les marqueurs (pas de fusion) ; l'opération est annulable par le toast. Le bloc `derushage-data` contient `{app, v, base, real, meta, offsets, markers, files}`.

## 4. Les deux moteurs (`BACKEND`)

`LOCAL` et `PC` exposent la même interface ; `BACKEND = LOCAL` au chargement, `BACKEND = PC` dès que `api/status` répond.

| Méthode | LOCAL (navigateur) | PC |
|---|---|---|
| `saveState()` | rien de plus que localStorage | `POST api/etat` |
| `capture(tr, t)` | `captureLocal` : WebCodecs, puis téléchargement | `captureRemote` : `POST api/photo` (clip du PC), sinon `captureLocal` |
| `compile()` | `runCompile` : WebCodecs + mp4-muxer ; retouches dessinées par `fxApply`, un fichier ou un par passage | `runRemote` : cartons rendus en PNG, retouches décrites par `fxPayload`, `POST api/video`, `pollJob` |
| `reel(story)` | `runReelLocal` : `rRender` par morceaux de story | `runReelRemote` : calques PNG, `POST api/reel`, `pollJob` |
| `busy(on)` | pendant un calcul : avertissement `beforeunload` et écran maintenu allumé (`navigator.wakeLock`), relâchés à la fin, à l'annulation ou en erreur | rien (le calcul continue sur le PC) |
| `compileFailed(msg)` | erreur dans le dialogue | retour à la vue Setup et toast |
| `reset()` | rien | retour à la liste des interventions |

Habillage : `cmpHab()` dit si la vidéo porte cartons, heure incrustée et logo. Sans habillage (choix de l'utilisateur, ou d'office quand tous les fichiers chargés sont des productions de l'outil, `prodSource()`), les passages sortent bruts sous le nom `ESAM_Extraits_...`, en une vidéo ou un fichier par passage (`CMP.sep`). Une production rouverte comme source n'a pas d'heure réelle (timeline relative).

Le reste du code appelle `BACKEND.x()` sans tester le mode. `pcOpen()` (une intervention est ouverte sur le PC) sert aux quelques textes et chemins qui dépendent du mode (photos, musique).

Dialogue de calcul : `jobRun(message, W, H, titre)` ouvre la vue de progression (titre : « Vidéo compilée », « Réel » ou « Story ») et rend le canvas d'aperçu ; `jobProgress(fraction, texte)` ; `jobDone({info, url, files: [{name, href}], where, title, saveLabel, onSave, onBack})` ou `jobError(message, onBack)` affichent le résultat (en mode PC, `href` lit le fichier produit par `/files/`). Les messages d'erreur passent par `errMsg()` (jamais de nom d'exception à l'écran). Les boutons « Enregistrer » et « Recommencer » exécutent les fonctions passées, ce qui évite tout drapeau global sur ce qui est affiché.

## 5. API HTTP de `server.py`

Toutes les réponses sont en JSON sauf les fichiers. Une erreur de validation rend `{"erreur": "..."}` en 400, une erreur interne en 500. `d` est toujours le nom d'un sous-dossier du dossier des rushs, vérifié par `folder()` (ni séparateur, ni `..`, ni point initial).

| Méthode et route | Entrée | Sortie |
|---|---|---|
| `GET /`, `/index.html` | | la page (jamais mise en cache) |
| `GET /vendor/<nom>` | nom de fichier simple | bibliothèque ou police |
| `GET /api/status` | | `{ok, version, racine, racine_ok, gpu, travaux: [calcul], veille: {mode, minutes}}` |
| `GET /api/interventions` | | `{interventions: [{nom, videos, proxies, fiche, compilation, compil, compil_proxies, maj}]}` (`compil` : vidéos compilées ou extraits que l'on peut rouvrir comme source) |
| `GET /api/manifest?d=[&src=compil]` | `src=compil` : les vidéos compilées de l'intervention au lieu des rushs | `{dossier, source, clips: [{nom, dur, w, h, codec, cree, appareil: {marque, modele} ou null, proxy, thumbs: {sheets, tw, th, cols, rows, every, count}}], photos: [{nom, heure}]}` |
| `GET /api/image?d=&f=&taille=` | `taille` = `petite` (360 px) ou `moyenne` (3200 px) | JPEG redressé selon l'EXIF, gardé dans `proxies/photos` |
| `GET /api/etat?d=[&src=compil]` | | contenu de `.derushage/etat.json` (ou `etat-compil.json`) ou `{}` |
| `GET /files/<dossier>/<chemin>` | | fichier des rushs (proxies, planches, musique), requêtes Range acceptées |
| `POST /api/proxies` | `{d, src}` | le calcul créé ou déjà en cours (un par source) |
| `POST /api/video` | `{d, format: "h"|"v", nom, titre, auteur, habillage, separes, logo, ouverture: {image, duree}, sprites: {id: image}, passages: [{image, duree, titre, nom_passage, commentaire, morceaux: [morceau]}]}` (images en data URL PNG). `habillage: false` : ni ouverture, ni cartons, ni logo ; `separes` : un fichier par passage | le calcul créé |
| `POST /api/reel` | `{d, mode: "reel"|"story", format: "reel"|"li"|"carre", largeur, hauteur, nom, titre_video, segments: [...], sprites, calques: [{image, debut, fin, fi, fo}], fin: {image, duree} ou null, musique: {fichier, debut} ou null, story_max}` ; un segment est `{type: "photo", image, duree, zoom, nom}` ou `{type: "video", nom, morceaux: [morceau]}`, où un morceau porte en plus `cles: [{t, x}]` (cadrage au format ; story seulement en 9:16) | le calcul créé |
| `POST /api/annuler` | `{id}` | `{ok}` |
| `POST /api/etat` | `{d, src, etat}` | `{ok}` |
| `POST /api/fiche` | `{d, nom, md}` ; supprime les autres `ESAM_Derushage_*.md` du dossier | `{ok, fichier}` |
| `POST /api/photo` | `{d, fichier, t}` | `{ok, fichier: "Photos/..."}` |
| `POST /api/musique?d=&nom=` | corps brut (60 Mo au plus, mp3, m4a, aac, wav, ogg, flac) | `{ok, fichier: "musique.<ext>"}` |

Un morceau est un extrait d'un fichier à vitesse constante, avec les retouches du passage (temps en secondes depuis le début du morceau, positions en fraction de l'image source) :

```json
{"fichier": "DJI_..._W.MP4", "debut": 12.5, "fin": 20.0, "vitesse": 0.5,
 "flous": [{"s": 0.2, "ar": 1, "forme": "ellipse|rect", "mode": "doux|pixel", "cles": [{"t": 0, "x": 0.4, "y": 0.5}]}],
 "formes": [{"image": "<id de sprites>", "ref": 2160, "ax": 310.5, "ay": 120, "cles": [...], "debut": 0, "fin": null}]}
```

Ordre des filtres ffmpeg d'un morceau : flous sur l'image source (`blur_chain`), mise au format (échelle et bandes, ou cadre 9:16), formes à la taille de sortie (`shape_chain`), vitesse (`setpts`), puis habillage (logo ou calques du réel). Un suivi de plusieurs centaines de points donne un filtre plus long que la ligne de commande de Windows : au-delà de 4 000 caractères, `fc_args` l'écrit dans un fichier (`-/filter_complex` à partir de ffmpeg 7, `-filter_complex_script` avant, détecté au démarrage).

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
| `ESAM_Extraits_<date>_<mission>[_vertical].mp4`, ou `..._<NN>_<passage>.mp4` par passage | `do_video` sans habillage |
| `.derushage/etat-compil.json`, proxies de la vidéo compilée | source « compil » (`api/etat`, `do_proxies`) |
| `ESAM_Reel_<date>_<mission>.mp4`, `ESAM_Story_<date>_<mission>[_NsurM].mp4`, `ESAM_LinkedIn_<date>_<mission>[_carre].mp4` | `do_reel` |

Le nom de base est construit par `outName()` côté appli (`ESAM_<préfixe>_<date du vol>[_<slug de la mission>]`) et nettoyé par `server.py` (caractères interdits sous Windows).

## 7. Ce qui existe en double, à dessein

Deux moteurs de rendu imposent quelques calculs en miroir. Chaque paire porte un commentaire qui nomme son jumeau ; `tests/test_unitaire.py` vérifie que les découpes de story et le lissage des points coïncident.

| Appli (`index.html`) | PC (`server.py`) | Objet |
|---|---|---|
| `storyCuts` | `story_cuts` | instants de coupe d'une story (60 s au plus, à une limite de passage) |
| `rKeyAt` | `key_expr` | lissage en S entre les points de cadrage et de suivi |
| `rZone` | `zone_box` et les `clip()` de `blur_chain` | taille et place d'une zone de flou, gardée dans l'image |
| `softBlur` | `blur_chain`, `blur_mask` | flou gaussien ou mosaïque, dans un ovale ou un rectangle aux bords fondus |
| `fxApply` (place d'une forme) | `shape_chain` et ses `fx`, `fy` | position et taille d'une forme dans l'image mise au format |
| nom des extraits dans `runCompile` | `do_video`, fichiers séparés | `<base>_<NN>_<nom du passage>.mp4` |
| `PROD_RE` | `PROD`, `COMPIL` | noms des vidéos produites par l'outil |
| `rCrop` | `crop_box` | cadre au format de sortie dans l'image source |
| `RFMTS` | `REEL_FMTS` | tailles des formats du réel et de la vidéo LinkedIn |
| `buildSrt` | bloc SRT de `do_video` | commentaires internes en sous-titres |
| `outName` | nettoyage des noms dans `do_video`, `do_reel` | noms des fichiers produits |

## 8. Conventions du projet

- Interface, messages, commentaires et documentation en français. Tiret simple uniquement (jamais U+2013 ni U+2014), y compris dans les noms de fichiers ; vérifier avant chaque commit :
  `python -c "import sys;[print(f, open(f,encoding='utf-8').read().count(chr(0x2014))+open(f,encoding='utf-8').read().count(chr(0x2013))) for f in sys.argv[1:]]" index.html server.py LISEZMOI.md README.md CLAUDE.md docs/ARCHITECTURE.md`
- Version : `APP_VERSION` (`index.html`), `VERSION` (`server.py`) et le frontmatter de `LISEZMOI.md` évoluent ensemble, avec une ligne de changelog orientée utilisateur. Le badge passe au jaune si l'appli et le PC diffèrent.
- Réglages du PC : `config.json` (propre à chaque PC, ignoré par git) ; tout nouveau réglage va dans `config.exemple.json` avec sa valeur par défaut, et `server.py` le lit par `CFG.get`.
- Les commentaires internes ne sont jamais incrustés dans une vidéo : elle doit rester publiable telle quelle.
- Mobile d'abord (téléphone en portrait, 390 px), mise en page large à partir de 1100 px. Charte : Anton pour les titres, Montserrat pour le texte, couleurs de `:root`.
- Échelle visuelle : texte de 12 px au minimum, champs de saisie à 16 px sur écran tactile ; titres Anton en 22, 28 ou 40 px ; rayons de 6, 10 ou 16 px (plus les pastilles rondes) ; cible tactile de 44 px (`--tap`) ; bord de contrôle `--ctl`, anneau de focus `--ring`. Un état sélectionné ne repose jamais sur le seul bleu pâle (bord à l'encre), ni la sensibilité sur la seule couleur (pastille jaune et texte).
- Vocabulaire de l'interface : « intervention » (le dossier chargé), « passage » (début et fin), « repère » (un instant). Le message de sauvegarde de l'en-tête passe par `setSave(détail, erreur, court)`.
- Jamais de sortie vidéo accumulée en mémoire : écriture par morceaux (OPFS ou Blob).
- Livraison : pousser sur `main` publie le mode navigateur sur GitHub Pages ; sur le PC, `mettre-a-jour.ps1` fait `git pull` et redémarre la tâche planifiée.

## 9. Tester

| Commande | Ce qu'elle fait | Durée |
|---|---|---|
| `python tests/test_unitaire.py` | fonctions pures de `server.py` et miroirs `storyCuts` / `story_cuts`, `rKeyAt` / `key_expr`, `rCrop` / `crop_box` (Playwright sur `index.html` en `file://`) | 10 s |
| `python tests/test_fumee.py` | faux rushs, serveur sur le port 8799, appli dans Chromium, préparation des proxies, ouverture | 1 min |
| `python tests/test_reel.py` | onglet Réel de bout en bout en mode PC, réel, story puis vidéo LinkedIn 4:5, contrôle des fichiers (1080 x 1920 ou 1080 x 1350, son, 60 s au plus) | 6 à 10 min sans NVIDIA |
| `python tests/test_montage.py` | retouches et extraits : suivi automatique mesuré sur un motif mobile et extraits calculés dans le navigateur ; en mode PC, flou suivi, formes, vitesses, vidéo compilée, extraits en un fichier par passage, reprise de la vidéo compilée comme source (durées contrôlées) | 3 min |
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
- Suivi automatique : comparaison de motifs, sans reconnaissance de visage ; il décroche sur un sujet masqué ou une zone uniforme. Un ralenti répète les images (pas d'interpolation).
- Les formes suivies n'ont pas de fondu d'apparition ; les éléments libres de l'aperçu du réel (`elems`) restent fixes à l'écran.
- Lecture à x16 limitée par le débit montant de la connexion du PC.
- Idée : télémétrie des `.SRT` du M30T (GPS, altitudes, focale) pour afficher altitude, vitesse et distance, avec incrustation optionnelle.
- Question ouverte : durée d'affichage des commentaires internes dans le `.srt` (tout le passage ou quelques secondes).
