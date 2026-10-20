---
titre: Analyse du code et de l'interface - dérushage drone ESAM
version_analysee: 0.11
date: 2026-10-20
statut: proposition
---

# Analyse du code et de l'interface (v0.11)

Objectifs fixés par Julien : garder l'appli légère, la faire évoluer facilement, la rendre lisible pour un développeur extérieur, améliorer l'ergonomie. Cette analyse part d'une lecture complète de `index.html`, `server.py`, des tests et de la documentation, de mesures automatiques et de captures d'écran en 390 x 844 (téléphone) et 1400 x 900 (PC) sur les faux rushs de `tests/`.

## 1. Synthèse

L'appli tient ses promesses d'architecture : un seul fichier HTML sans étape de construction, un serveur Python sans dépendance, deux modes (navigateur et PC) qui partagent la même interface. Le test de fumée passe (`python tests/test_fumee.py` : badge, liste, proxies, pistes), et aucune erreur JavaScript n'apparaît pendant le parcours complet en mode navigateur sur téléphone ni sur PC.

Trois sujets méritent un investissement, par ordre d'importance :

1. **Lisibilité pour un développeur extérieur.** Le mode PC est greffé sur le mode navigateur par neuf remplacements de fonctions à la volée (`var _persist = persist; persist = function(){...}`), le style JavaScript mélange ES5 (`var`, `function`) et ES2017 (`async`, `for await`), et la seule documentation technique est `CLAUDE.md`, écrite pour un assistant et non pour une personne. Il manque un document d'architecture avec le modèle de données, l'API HTTP et les conventions.
2. **Légèreté réelle sur le terrain.** La page dépend de jsDelivr (mp4box, mp4-muxer) et de Google Fonts. En mode PC via Tailscale, le téléphone a donc besoin d'Internet pour charger l'appli, alors que le serveur est à portée. Les deux bibliothèques peuvent être servies localement.
3. **Ergonomie.** L'essentiel est bon (gros boutons, retours « Annuler », raccourcis clavier, mode sombre, dialogues natifs). Les points faibles sont concentrés sur téléphone : le toast masque la timeline au moment où l'on vient de poser un marqueur, le Sommaire affiche huit « [non marqué] » en rouge avant le premier marqueur, l'onglet Réel impose un long défilement entre le montage et le passage en cours de réglage.

## 2. Mesures

| Mesure | Valeur | Lecture |
|---|---|---|
| `index.html` | 269 Ko, 3 985 lignes | 239 Ko hors logos ; CSS 407 lignes, HTML 301, JS 3 263 |
| Logo ESAM en base64 | 2 copies de 12 Ko | la même image est embarquée deux fois (`.logo` et `#logoImg`) |
| Fonctions JS | environ 260, dans une seule IIFE | pas de module, pas de classe |
| Fonctions JS de plus de 80 lignes | `rRender`, `runCompile`, `rDraw` | les trois cœurs de rendu |
| Lignes JS de plus de 220 caractères | 50 (2 de plus de 400) | surtout les gabarits HTML concaténés |
| `innerHTML` | 28 points de rendu | tout le rendu passe par des chaînes |
| `catch(e){}` silencieux | 37 | normal pour des API navigateur optionnelles, mais sans trace |
| Remplacements de fonctions à la volée (mode PC et réel) | 9 | voir section 3.2 |
| Classes CSS définies mais jamais utilisées | 12 | `brand`, `caprow`, `clipb`, `clockrow`, `markbar`, `marks`, `more`, `mrow`, `mtitle`, `qrow`, `quick`, `vtop` |
| Sélecteurs CSS redéfinis 3 fois ou plus | 7 | `.wrap`, `.stage`, `.keys` (4 fois chacun), `.transport`, `.pending`, `.top .tabs`, `.rstage.v canvas` |
| `server.py` | 848 lignes, 46 fonctions, 10 docstrings | `do_reel` 155 lignes, `do_video` 132, `do_POST` 59 |
| pyflakes | 1 avertissement | `sys` importé sans usage |
| Tirets longs | 0 | règle respectée |
| Versions | 0.11 partout | `APP_VERSION`, `VERSION`, `LISEZMOI.md` cohérents |
| Tests | 3 scripts, 0 test unitaire | fumée, réel de bout en bout, fabrique de rushs |

## 3. Code : ce qui tient, ce qui freine

### 3.1 Points forts à préserver

- **Pas de framework, pas de build** : un développeur lit le fichier et comprend ; la mise à jour sur le PC est un `git pull`.
- **Serveur minimal et sûr** : écoute locale, chemins vérifiés (`folder()` refuse `/`, `\`, `..` ; `/files/` résout dans la racine), requêtes Range pour les proxies, file de calculs persistée et reprise propre (« interrompu »), encodeurs détectés au démarrage, fichiers écrits en `.tmp` puis `os.replace`.
- **Mémoire maîtrisée** : sortie vidéo écrite par morceaux (`blobTarget`, OPFS), décodage WebCodecs avec files d'attente bornées (`waitQ`), vignettes de la planche dessinées à la demande (IntersectionObserver), bitmaps libérés au changement de vol.
- **Rendu partagé entre aperçu et fichier final** : `drawLayers`, `drawCropped`, `softBlur` servent à l'aperçu et au rendu navigateur, et sont envoyés en PNG au PC. Un seul code dessine ce que l'utilisateur voit.
- **Retours utilisateur soignés** : toasts avec « Annuler », états de chargement, messages d'erreur conservés, bandeau « Dans la plage » contextuel.

### 3.2 Freins à l'évolution

**Le mode PC par remplacement de fonctions.** `persist`, `captureAt`, `renderCmpSetup`, `cmpOpen`, `cmpGo`, `cmpCancel`, `reset`, `cmpSave`, `cmpBack` sont redéfinis plus bas dans le fichier en gardant l'ancienne version sous `_persist`, `_cap`, etc. Le comportement d'une fonction dépend donc de l'ordre des sections, et un développeur qui lit `captureAt` ne voit pas qu'elle est remplacée 500 lignes plus loin. Proposition : un objet `BACKEND` avec deux implémentations de la même interface (`saveState`, `capture`, `compile`, `cancel`, `reel`, `listPhotos`, `photoUrl`), choisi une fois dans `srvInit()`. Le code appelant devient `BACKEND.capture(tr, t)` sans condition `SRV && SRVD` dispersée (14 occurrences aujourd'hui).

**Le dialogue de compilation réutilisé pour le réel.** `#cmp` sert à la vidéo compilée et au réel, avec des drapeaux `REEL.showing`, des boutons cachés ou montrés selon le mode, et des gestionnaires `close` qui remettent l'état. Proposition : un composant `jobDialog({titre, apercu, onCancel, onSave})` paramétré, sans état global.

**Un style JavaScript daté et inégal.** Le code utilise `async/await`, `for await`, `Promise.all`, `dialog.showModal`, WebCodecs : il exige un navigateur récent. Mais il s'écrit en ES5 (`var`, `function(){}`, concaténation de chaînes). Passer à `const`/`let`, fonctions fléchées et gabarits `\`...\`` réduirait le volume d'environ 15 % et surtout permettrait d'écrire les gabarits HTML sur plusieurs lignes lisibles. Les 50 lignes de plus de 220 caractères sont presque toutes des gabarits.

**Des miroirs navigateur/PC sans lien explicite.** Plusieurs calculs existent deux fois, une fois en JavaScript et une fois en Python : `storyCuts` et `story_cuts`, `rKeyAt` et `key_expr`, `softBlur` et `blur_chain`, `buildSrt` et le bloc SRT de `do_video`, les noms de fichiers de sortie. C'est inhérent à deux moteurs de rendu, mais chaque paire devrait porter un commentaire nommant son jumeau (fait pour les flous, pas pour le reste) et un test qui vérifie qu'elles donnent le même résultat sur les mêmes entrées (les découpes de story notamment).

**Le nommage des fichiers de sortie est répété.** L'expression `"ESAM_..."+(S.real ? isoDay(new Date(S.base*1000)) : isoDay(new Date()))+(S.meta.intervention ? "_"+slug(...) : "")` apparaît quatre fois (`ficheName`, `cmpName`, `runRemote`, `rBaseName`). Une fonction `outName(prefix, suffix)` suffit.

**Le CSS porte trois couches.** Les sections « UX v2 » et « UX v3 » redéfinissent des règles antérieures au lieu de les remplacer (`.top .sub` est stylé puis masqué par `display:none!important`). Résultat : 12 classes mortes, 7 sélecteurs définis trois ou quatre fois, et un développeur qui ne sait pas quelle règle gagne. Un nettoyage à plat ramènerait le CSS vers 300 lignes sans changer le rendu (vérifiable par comparaison de captures).

**Le serveur.** Routage par chaîne de `if` dans `do_GET` et `do_POST` (lisible à 12 routes, à surveiller), `list_interventions` parcourt chaque dossier trois fois (`videos`, détection de fiche, détection de compilation) ce qui coûte sur un Drive en mode flux, `server_version` reste à « 1.0 » alors que `VERSION` vaut 0.11, et `datetime` est importé à chaque appel de `probe`. Rien de bloquant.

### 3.3 Légèreté : où gagner

| Action | Gain | Effort |
|---|---|---|
| Servir mp4box et mp4-muxer depuis un dossier `vendor/` du dépôt (licences MIT), avec le CDN en secours | appli utilisable via Tailscale sans Internet ; versions figées par git plutôt que par URL | faible |
| Embarquer une seule copie du logo (le `<img>` de l'en-tête prend sa source sur `#logoImg` au chargement) | 12 Ko, et une seule image à mettre à jour | très faible |
| Polices : garder Google Fonts mais vérifier le rendu des cartons avec les polices de secours (Impact, Arial) hors ligne, ou embarquer Anton seule (environ 15 Ko en woff2) | cartons identiques en ligne et hors ligne | faible |
| Nettoyage CSS (section 3.2) | environ 100 lignes | moyen |
| Mode PC : garder les planches de vignettes en `Image` et dessiner des sous-rectangles au lieu de créer un `ImageBitmap` par vignette | moins d'objets en mémoire sur téléphone pour les longues interventions (plusieurs heures de rushs, 4 pistes : plusieurs milliers de bitmaps) | moyen, à mesurer avant |

Point de vigilance, non vérifié sur un vrai vol : en mode PC, `loadSheets` crée un bitmap par vignette pour toutes les pistes dès l'ouverture. Pour une intervention de trois heures avec quatre caméras et une vignette toutes les 3 secondes, cela fait environ 14 000 bitmaps de 160 x 90. À tester sur le téléphone de terrain avant de décider.

## 4. Documentation pour un développeur extérieur

Aujourd'hui : `README.md` (présentation), `LISEZMOI.md` (installation et guide utilisateur, bon niveau), `CLAUDE.md` (notes techniques denses mais adressées à un assistant). Un développeur qui arrive n'a nulle part : le modèle de données, la liste des routes HTTP, le cycle de vie d'un calcul, le format de la fiche et de `etat.json`, les conventions (français, tirets, versions, tests).

Proposition : un fichier `docs/ARCHITECTURE.md` d'environ 200 lignes, et `CLAUDE.md` réduit aux consignes propres à l'assistant avec un renvoi vers ce document. Contenu :

1. **Vue d'ensemble** : les deux modes, le schéma « téléphone, Tailscale, PC, Drive », ce qui s'exécute où.
2. **Carte de `index.html`** : la liste des sections avec leur rôle et leurs fonctions d'entrée (`addFiles`, `rebuild`, `seek`, `renderTimeline`, `openSheet`, `buildMarkdown`, `runCompile`, `srvInit`, `reelPlan`, `rRender`). Les commentaires de section existent déjà, il manque l'index.
3. **Modèle de données** : `S` (clips, tracks, markers, meta, offsets), un marqueur (`id, at, to, preset, title, themes, interest, sens, note, comment, cam`), `S.meta.reel` (déjà décrit dans `CLAUDE.md`, à déplacer), ce qui est persisté où (localStorage, `etat.json`, bloc `<!-- derushage-data -->` de la fiche) et les règles de reprise (la fiche remplace, ne cumule pas).
4. **API HTTP** : tableau des 12 routes avec méthode, paramètres, réponse, erreurs (`{"erreur": ...}` en 400 ou 500). Exemple : `POST /api/video` avec le JSON `passages`.
5. **Cycle de vie d'un calcul** : `new_job`, file, `worker`, états `attente`, `en_cours`, `termine`, `erreur`, `annule`, `interrompu`, persistance dans `travaux.json`, annulation par `job["cancel"]`.
6. **Fichiers produits** : repris du tableau de `LISEZMOI.md`, avec les règles de nommage et le rôle de `proxies/*.json`.
7. **Conventions** : français partout, tiret simple, version en trois endroits, `config.exemple.json`, mobile d'abord, charte (polices, couleurs).
8. **Tester** : les trois scripts, le réglage `_test_vp9`, comment faire des captures en 390 x 844 et 1400 x 900.
9. **Limites connues et idées** : reprises de `LISEZMOI.md` et `CLAUDE.md`.

Dans le code lui-même : un commentaire d'en-tête par section de `index.html` (deux ou trois lignes : rôle, état manipulé, fonctions d'entrée), des docstrings sur les 36 fonctions Python qui n'en ont pas (une ligne suffit), et un commentaire « miroir de `x` côté PC » sur chaque paire navigateur/PC.

## 5. Ergonomie

Captures de référence : parcours complet en mode navigateur, téléphone et PC, sur les faux rushs. Les constats ci-dessous sont classés par écran, du plus gênant au plus léger.

### 5.1 Visionner (téléphone)

- **Le toast cache la timeline.** Il apparaît en bas, centré, c'est-à-dire exactement sur les pistes où l'on vient de poser la plage, et il porte le bouton « Annuler ». L'utilisateur ne voit ni la plage posée ni les poignées de réglage pendant 5 secondes. Proposition : afficher le toast sous la barre d'onglets (en haut) sur téléphone, ou juste au-dessus des boutons Début/Fin/Repère. Sur PC, bas centré convient.
- **L'en-tête de mission prend trois lignes** (« Nommer la mission », la date et les pistes, « Vidéo compilée : aucun passage pour l'instant ») sur un écran où chaque ligne compte. La ligne de compilation n'apporte rien tant qu'il n'y a pas de passage : la masquer à zéro passage, et la fusionner avec le badge du Sommaire ensuite.
- **« Hors des passages sélectionnés »** s'affiche avant tout marqueur, et « sélectionnés » laisse penser qu'une sélection existe. Masquer le bandeau à zéro marqueur, ou écrire « Aucun passage à cet instant ».
- **Zoom de la timeline** uniquement par les boutons « - x1 + ». Sur téléphone, le pincement est le geste attendu ; `touch-action: pan-x` l'empêche aujourd'hui. À ajouter avec les événements Pointer déjà en place.
- **Raccourci « R »** (bascule début/fin) existe dans le code mais pas dans l'aide des raccourcis.

Ce qui marche bien : les trois gros boutons avec « Fin » désactivé tant que « Début » n'est pas posé, le bandeau « Dans la plage » avec « Début ici / Fin ici », l'aperçu de vignette pendant le glissement sur la règle, l'horloge incrustée.

### 5.2 Sommaire

- **Chronologie RETEX avant le premier marqueur** : huit lignes « [non marqué] » en rouge, la couleur réservée aux erreurs. Proposition : gris atténué et libellé « à marquer », bloc replié tant qu'aucun « Décollage » n'existe, rouge uniquement pour une incohérence (atterrissage avant décollage).
- **Six boutons par carte** (« Voir en Grand angle », « Voir en Zoom », « Voir en Thermique », « Voir en Autre caméra », « Photo », « Modifier »). La caméra est déjà choisie dans le sélecteur de la carte : un seul bouton « Voir » qui lit `effCam(m)` suffit, les autres caméras restant accessibles par le sélecteur ou depuis Visionner. La carte tient alors sur une ligne d'actions.
- **Deux boutons principaux** côte à côte (« Exporter la fiche », « Créer la vidéo compilée »). En mode PC et en mode dossier, la fiche est enregistrée automatiquement : « Enregistrer la fiche maintenant » peut passer en style discret, un seul bouton principal par écran.
- **Nom d'intervention saisi à deux endroits** (en-tête et Sommaire), synchronisés. Garder l'en-tête seul évite une question (« lequel fait foi ? »).

### 5.3 Planche

Bon écran : chips de piste et d'intervalle, grille responsive, « Marquer » sur chaque vignette. Rien à changer, sinon peut-être afficher la piste compilée du marqueur en surimpression des badges.

### 5.4 Réel (téléphone)

- **Ordre des blocs.** Sur téléphone, la colonne de gauche (scène, lecteur, éditeur du passage, long) précède la colonne de droite (Montage, Habillage). Après avoir touché un passage, l'utilisateur est ramené à la scène et doit redescendre de deux écrans pour revenir au montage. Proposition : sur téléphone, un sélecteur en haut de l'onglet avec trois volets « Montage », « Passage », « Habillage » (les chips « Cadrage du passage / Aperçu du réel » existent déjà et pourraient s'y fondre) ; sur PC, les deux colonnes actuelles.
- **L'éditeur du passage est dense** : Début/Fin ici, cadrage, flous, caméra, vitesse, texte, chacun avec sa phrase d'aide. Les aides pourraient se replier après la première utilisation (une préférence locale), ou passer en infobulle sur PC.
- **Barre « Créer le réel / Créer la story » collante en bas** : bon choix, elle rappelle la cible. Elle recouvre toutefois la dernière ligne du contenu défilé ; un `scroll-padding-bottom` égal à sa hauteur règle le point.
- **Pas de badge sur l'onglet Réel** alors que le Sommaire en a un : afficher le nombre de passages du montage donne le même repère.

Ce qui marche bien : le cadre bleu qui glisse sur l'image entière, les points de suivi sur la barre, la liste « Sur l'image » avec sélection directe sur le canevas, la poignée jaune de redimensionnement, « Remettre à sa place ».

### 5.5 PC (1400 x 900)

La mise en page exploite la largeur : lecteur et timeline à gauche, marqueurs et options à droite, raccourcis visibles. Deux détails : la colonne de droite est vide avant le premier marqueur (le texte d'aide est là, il pourrait y ajouter les trois raccourcis I, O, M), et la hauteur de scène est calculée par une formule `calc()` longue redéfinie trois fois dans le CSS ; une seule règle avec une variable `--stage-max` serait plus sûre.

### 5.6 Transversal

- **Accessibilité** : bons réflexes (`aria-pressed`, `aria-label`, `role=tablist`, `focus-visible`, `dialog`, `prefers-reduced-motion`). Il manque `aria-controls` sur les onglets et un `aria-live` sur le toast pour qu'un lecteur d'écran l'annonce.
- **Mode sombre** : géré par variables, rien à signaler.
- **Messages** : clairs et en français. Les crochets « [H.265 non pris en charge] » et « [non marqué] » servent de convention d'alerte ; la documenter dans l'architecture pour qu'un développeur la respecte.

## 6. Plan d'action proposé

Par ordre de rendement, chaque lot livrable seul avec sa version et sa ligne de changelog.

**Lot 1, documentation et hygiène (une demi-journée, aucun risque fonctionnel)**
- `docs/ARCHITECTURE.md` selon le plan de la section 4 ; `CLAUDE.md` renvoie vers lui.
- Docstrings d'une ligne sur les fonctions Python, commentaires d'en-tête par section JS, commentaires « miroir » sur les paires navigateur/PC.
- Retirer `import sys`, aligner `server_version` sur `VERSION`, un seul parcours de dossier dans `list_interventions`.
- Un seul logo embarqué.

**Lot 2, ergonomie téléphone (une journée)**
- Toast en haut sur téléphone ; bandeau « Dans la plage » masqué à zéro marqueur ; ligne de compilation masquée à zéro passage.
- Sommaire : chronologie en gris « à marquer » et repliée, un bouton « Voir » par carte, un seul bouton principal.
- Réel : trois volets sur téléphone, `scroll-padding-bottom`, badge sur l'onglet.
- Vérification par captures 390 x 844 et 1400 x 900 avant et après.

**Lot 3, structure du code (deux jours, à faire d'un bloc pour ne pas vivre longtemps avec deux styles)**
- Objet `BACKEND` à deux implémentations, suppression des neuf remplacements de fonctions.
- Composant de dialogue de calcul paramétré, suppression de `REEL.showing`.
- Passage à `const`/`let`, fonctions fléchées, gabarits multilignes ; `outName()` pour les noms de sortie.
- CSS à plat, suppression des classes mortes.
- Le test de fumée et `test_reel.py` servent de filet ; ajouter `tests/test_unitaire.py` pour `story_cuts`, `key_expr`, `crop_box`, `jpeg_orientation`, `slug`, et un test Playwright qui compare `storyCuts` (JS) et `story_cuts` (Python) sur les mêmes plans.

**Lot 4, autonomie réseau (une demi-journée)**
- `vendor/mp4box.all.min.js` et `vendor/mp4-muxer.min.js` servis par `server.py` et GitHub Pages, CDN en secours.
- Décision sur les polices après essai hors ligne des cartons.

**Lot 5, à mesurer avant de décider**
- Mémoire des vignettes en mode PC sur une longue intervention, sur le téléphone de terrain ; pincement pour zoomer la timeline.

## 7. Points vérifiés sans anomalie

- Aucune erreur JavaScript sur le parcours complet (accueil, chargement, marqueurs, fiche de marqueur, planche, sommaire, compilation, réel en cadrage et en aperçu), téléphone et PC.
- `python tests/test_fumee.py` : serveur 0.11, racine valide, badge « v0.11 PC » bleu, intervention listée, 6 proxies sur 6, 4 pistes, aucune erreur de page.
- Les trois numéros de version concordent ; aucun tiret long dans les cinq fichiers de la règle.
- Les contrôles de chemin du serveur refusent la remontée de dossier et les noms absolus.
