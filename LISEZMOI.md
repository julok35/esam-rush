---
titre: Dérushage drone ESAM - installation sur le PC de traitement
statut: brouillon
version: 0.21
date_maj: 2026-11-24
---

# Dérushage drone ESAM - installation sur le PC de traitement

Le PC (Windows 11) fait tout le travail lourd : il lit les rushs dans le Drive ESAM synchronisé, fabrique les proxies et les vignettes, sert l'appli de dérushage et monte la vidéo compilée en résolution d'origine. Le téléphone ne sert qu'à piloter et à marquer, via Tailscale.

Rien n'est exposé sur Internet : le serveur n'écoute que sur le PC lui-même, et seul Tailscale y donne accès, depuis vos propres appareils.

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| `server.py` | Le programme du PC (Python, sans dépendance) |
| `index.html` | L'appli de dérushage, servie par le PC et publiée sur GitHub Pages |
| `vendor/` | Bibliothèques vidéo et polices embarquées : l'appli n'a pas besoin d'Internet |
| `config.exemple.json` | Modèle des réglages, copié en `config.json` au premier lancement |
| `config.json` | Les réglages de ce PC (jamais envoyé sur GitHub) |
| `installer.ps1` | L'installation automatique |
| `mettre-a-jour.ps1` | Récupère la dernière version sur GitHub et redémarre le serveur |
| `derushage.log` | Journal, créé au premier lancement |

## 1. Google Drive pour ordinateur

1. Installez Google Drive pour ordinateur et connectez le compte ESAM qui voit le dossier des rushs.
2. Laissez le mode « Diffuser les fichiers » (par défaut) : les rushs ne sont téléchargés que lorsqu'un traitement en a besoin.
3. Dans l'Explorateur, repérez le chemin du dossier qui contient un sous-dossier par intervention, par exemple `G:\Mon Drive\ESAM\Rushs drone` ou `G:\Drive partagés\ESAM\Rushs drone`.

Convention de rangement : un sous-dossier par intervention, dont le nom commence par la date, par exemple `2026-09-12 Chien égaré Belledonne`. Les vidéos du drone et des téléphones sont posées directement dedans.

## 2. Dossier du programme

1. Installez Git : dans PowerShell, `winget install --id Git.Git -e`, puis fermez et rouvrez PowerShell.
2. Récupérez le programme hors du Drive : `git clone https://github.com/julok35/esam-rush C:\ESAM\derushage`.
3. Dans ce dossier, copiez `config.exemple.json` en `config.json`, ouvrez-le avec le Bloc-notes et remplacez `dossier_rushs` par votre chemin, avec des barres obliques `/` : `"G:/Mon Drive/ESAM/Rushs drone"`.

Réglages disponibles :

| Réglage | Valeur par défaut | Effet |
|---|---|---|
| `mode_inactivite` | `veille` | `veille`, `arret` ou `aucun` après inactivité |
| `veille_apres_minutes` | `20` | Délai sans traitement, sans appli et sans clavier ni souris |
| `proxy_hauteur` | `540` | Hauteur des proxies en pixels |
| `vignette_toutes_secondes` | `3` | Intervalle entre deux vignettes |
| `codec_video_finale` | `h264` | `h265` pour un fichier environ deux fois plus léger |
| `dossier_travail` | vide (dossier temporaire Windows) | Disque local où la vidéo est montée avant sa copie dans le Drive ; prévoir plusieurs Go libres |

## 3. Installation

Clic droit sur `installer.ps1`, puis « Exécuter avec PowerShell ». Le script installe Python et ffmpeg s'ils manquent (relancez-le après chaque installation qu'il signale), crée la tâche « ESAM Derushage » lancée à l'ouverture de session, puis démarre le serveur et indique si la carte NVIDIA est utilisée pour l'encodage.

Si Windows refuse le script : ouvrez PowerShell et tapez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, puis recommencez.

## 4. Tailscale (accès depuis le téléphone)

1. Installez Tailscale sur le PC et sur le téléphone, connectés au même compte.
2. Dans la console d'administration Tailscale, onglet DNS : activez MagicDNS et les certificats HTTPS.
3. Sur le PC, dans PowerShell : `tailscale serve --bg 8765` (l'installateur le fait si Tailscale est déjà présent). La commande affiche l'adresse de l'appli, de la forme `https://nom-du-pc.xxxx.ts.net`.
4. Sur le téléphone, ouvrez cette adresse dans Chrome, puis menu, « Ajouter à l'écran d'accueil ».

L'adresse en `https` est indispensable : sans elle, le navigateur du téléphone bloque une partie des fonctions de l'appli.

## 5. Réveil à distance

- Mode `veille` (recommandé) : la session Windows reste ouverte, Drive et le serveur reprennent tout seuls au réveil. Dans le Gestionnaire de périphériques, propriétés de la carte réseau, onglet « Gestion de l'alimentation », cochez « Autoriser ce périphérique à sortir l'ordinateur du mode veille » et « N'autoriser qu'un paquet magique ». Le PC doit être relié en Ethernet.
- Mode `arret` : il faut en plus activer le Wake-on-LAN dans le BIOS, désactiver le démarrage rapide de Windows, et ouvrir la session automatiquement au démarrage (outil Autologon de Microsoft Sysinternals). Sans session ouverte, ni Drive ni le serveur ne démarrent.

## 6. Utilisation

1. Réveillez le PC depuis Home Assistant, puis ouvrez l'appli sur le téléphone : la liste des interventions s'affiche.
2. « Préparer » lance la fabrication des proxies et des vignettes. La progression s'affiche ; vous pouvez fermer l'appli pendant ce temps.
3. « Ouvrir » charge l'intervention. L'appli se parcourt en quatre étapes numérotées : **1 Sélection** (visionner et marquer les plans), **2 Compilation** (les plans retenus pour la vidéo longue, avec leurs retouches), **3 Réseaux** (vidéo courte 9:16, 4:5 ou 1:1), **4 Export** (tout ce que l'on peut produire). La bande sous le nom de l'intervention donne en permanence le nombre de plans et leur durée, la durée estimée de la vidéo compilée (cartons et marges compris) et celle du montage réseaux.
   Dans Sélection, Début, Fin et Repère posent les marqueurs ; juste après, le bandeau sous ces boutons propose les noms courants : un toucher suffit, sans arrêter la lecture (« Autre... » ouvre la fiche complète, qui s'enregistre en se fermant ; « Annuler » dans le message qui suit la remet comme avant). Ils sont enregistrés automatiquement sur le PC, dans le sous-dossier `.derushage` de l'intervention.
   Sur les pistes, les numéros trop proches pour être touchés un par un forment un groupe (« 3-6 ») : le toucher zoome jusqu'à les séparer, ou propose la liste s'ils tombent presque au même instant. Toucher le numéro d'un passage court zoome aussi dessus, pour en glisser les bords à l'aise après la fiche ; « - » ramène au zoom d'avant.
   Les périodes où aucune piste n'a d'image pendant plus de 20 s (vidéos de téléphone espacées, changement de batterie) sont repliées en une bande hachurée étroite qui indique la durée sautée (« 1 h 12 ») ; les heures affichées restent les vraies, et la lecture passe directement au fichier suivant, sur une autre piste s'il le faut. Le bouton « Replier les temps morts », sous les noms de pistes, revient à l'échelle réelle ; le choix est gardé sur l'appareil.
   La fiche d'un marqueur a un champ facultatif « Ce qu'on voit » (une phrase sur le contenu du plan), aussi modifiable sur la carte du plan dans Compilation : il sert à la liste des plans.
4. L'icône d'appareil photo enregistre l'image en pleine résolution dans le sous-dossier `Photos`.
5. La fiche Markdown est enregistrée automatiquement dans le dossier de l'intervention, quelques secondes après chaque modification (l'heure du dernier enregistrement s'affiche à côté du nom de l'intervention) ; étape Compilation ou Export, « Créer la vidéo compilée » envoie le montage au PC, qui dépose la vidéo dans le dossier de l'intervention.
6. Après 20 minutes sans activité, le PC se remet en veille.

## 7. Mise à jour

Le code vit sur GitHub (https://github.com/julok35/esam-rush). Pour installer la dernière version sur le PC : clic droit sur `mettre-a-jour.ps1`, « Exécuter avec PowerShell ». Le script récupère les fichiers, redémarre le serveur et affiche la version. Un calcul en cours est interrompu : lancez la mise à jour quand rien ne tourne. Vos réglages (`config.json`) ne sont jamais touchés.

Le mode navigateur (https://julok35.github.io/esam-rush/) se met à jour tout seul, une à deux minutes après chaque envoi sur GitHub.

## Ce que le programme écrit dans chaque dossier d'intervention

| Élément | Contenu |
|---|---|
| `proxies/` | Copies 540p, vignettes et métadonnées |
| `.derushage/etat.json` | Marqueurs en cours (sauvegarde automatique) |
| `ESAM_Derushage_<date>_<mission>.md` | Fiche de dérushage, une seule par intervention |
| `ESAM_Plans_<date>_<mission>.md` | Liste des plans pour bâtir un storyboard (étape Export), sans commentaires internes sauf demande |
| `Photos/` | Photos pleine résolution |
| `ESAM_Compilation_<date>_<mission>.mp4` | Vidéo compilée, avec un chapitre par passage |
| `ESAM_Compilation_<date>_<mission>.commentaires-ESAM.srt` | Commentaires internes signés, en sous-titres à part (jamais incrustés dans la vidéo) |
| `ESAM_Extraits_<date>_<mission>.mp4` | Extraits bruts (habillage « Aucun ») : les passages sans carton, sans heure et sans logo |
| `ESAM_Extraits_<date>_<mission>_01_<passage>.mp4`... | Les mêmes extraits, en un fichier par passage |
| `.derushage/etat-compil.json` | Marqueurs posés sur une vidéo compilée rouverte pour en extraire des morceaux (à part de ceux des rushs) |
| `ESAM_Reel_<date>_<mission>.mp4` | Réel vertical 1080 x 1920 (étape Réseaux) |
| `ESAM_Story_<date>_<mission>_1sur2.mp4`... | Story découpée en morceaux de 60 s maximum |
| `ESAM_LinkedIn_<date>_<mission>.mp4`, `..._carre.mp4` | Vidéo LinkedIn 1080 x 1350 (4:5) ou 1080 x 1080 (carré) |
| `.derushage/musique.mp3` | Musique choisie pour le réel |
| `ESAM_Compilation_<date>_<mission>_chapitres.txt` | Liste des chapitres au format YouTube (à coller dans la description) |

## Vérifier la version

Le badge en haut à droite de l'appli indique la version :
- « v0.9 PC » sur fond bleu : l'appli passe par le programme du PC, et les deux sont à jour. Les calculs se font sur le PC.
- « v0.9 PC » sur fond jaune : l'appli et le programme du PC n'ont pas la même version. Lancez `mettre-a-jour.ps1`.
- « v0.9 » sans « PC » : mode navigateur, les calculs se font dans l'appareil qui affiche la page. C'est le cas de https://julok35.github.io/esam-rush/ et de toute ouverture sans passer par le PC.

Le journal `derushage.log` indique aussi la version au démarrage du programme.

## En cas de problème

- L'appli affiche « PC injoignable » : le PC dort ou Tailscale est déconnecté.
- Une préparation ou une vidéo échoue : le message reste affiché dans l'appli et dans la liste des interventions, le détail est dans `derushage.log`.
- Si la copie finale vers le Drive échoue, la vidéo est conservée sur le PC dans le dossier de travail ; le message indique son emplacement.
- Un calcul coupé par une mise en veille ou un redémarrage est signalé « interrompu » : relancez-le.
- Rien ne se passe après un réveil : vérifiez dans le Planificateur de tâches que « ESAM Derushage » est en cours d'exécution.

## Commentaires internes

Dans l'étape Compilation, chaque plan a un champ « Commentaire interne ». Le champ « Auteur » se remplit une fois et signe tous les commentaires. À la compilation, ces commentaires partent dans un fichier de sous-titres `.commentaires-ESAM.srt` posé à côté de la vidéo, affiché pendant le passage concerné.

- VLC l'affiche automatiquement (même dossier, nom commençant comme celui de la vidéo).
- Dans Google Drive : ouvrir la vidéo, menu des trois points, « Gérer les sous-titres », ajouter le fichier `.srt`. Seuls ceux qui regardent la vidéo dans le Drive les voient.
- Le fichier MP4 lui-même ne contient pas les commentaires : il peut être publié tel quel.

## Retoucher un passage : flous, flèches, cercles, vitesse, couleurs

Le bouton « Retoucher » d'un passage (étape Compilation, liste des passages de « Créer la vidéo compilée », réglages d'un passage dans l'étape Réseaux) ouvre l'image du passage en grand. Les retouches appartiennent au passage : elles sont appliquées dans toutes les vidéos qui en sont tirées (vidéo compilée, extraits, réel, story, vidéo LinkedIn) et enregistrées avec les marqueurs.

- **Flou** (visage, plaque d'immatriculation, lieu) : « + Flou » pose une zone au centre de l'image. Glissez-la sur ce qu'il faut cacher et tirez son coin (rond bleu) pour régler sa hauteur et sa largeur. Forme ovale (visage) ou rectangle (plaque) ; rendu flou doux ou pixelisé ; bords fondus dans les deux cas.
- **Suivi en mouvement** : « Suivre automatiquement » lance la lecture et la zone suit toute seule son sujet, image après image, jusqu'à la fin du passage. Si le sujet est masqué ou sort de l'image, le suivi s'arrête et le dit : replacez la zone et relancez, le suivi repart de cet instant. On peut aussi suivre à la main : pendant la lecture, gardez le doigt (ou la souris) sur la zone ; à l'arrêt, chaque déplacement pose un point de suivi à l'instant affiché. « Supprimer le point ici » et « Rendre fixe » corrigent une trajectoire. Relisez toujours le passage avant de publier.
- **Flèche et cercle** : tracés « au crayon », comme dans l'appli photo. La pointe de la flèche vise son sujet, le cercle l'entoure ; ils se suivent comme un flou (automatiquement ou à la main). Couleur, taille, orientation, largeur du cercle, et moment d'apparition et de disparition (« Apparaît ici », « Disparaît ici »).
- **Vitesse** : placez la lecture là où la vitesse doit changer, puis choisissez x0,25 ou x0,5 (ralenti), Normale, ou x2 à x8 (accéléré). Le choix vaut jusqu'au changement suivant ; fait au début du passage, il vaut pour tout le passage. Les tronçons modifiés sont hachurés en jaune sur la barre, et la durée du passage dans la vidéo est indiquée. Dans le réel, l'accéléré du réel multiplie ces vitesses.
- **Couleurs** (bloc « Couleurs », replié sous les réglages ; son résumé dit ce qui est changé) : luminosité, contraste, saturation et température (vers le froid ou vers le chaud), de -100 à +100, avec l'aperçu en direct sur l'image. « Automatique » mesure cinq images du passage et étire les niveaux (luminosité et contraste seulement) ; « Neige / contre-jour » relève les ombres sans brûler la neige et réchauffe un peu ; « Voir l'original » compare avec l'image d'origine ; « Remettre à zéro » rend l'image inchangée ; « Appliquer à tous les passages » recopie le réglage de cette caméra dans les autres passages (annulable par le message qui s'affiche). Le réglage vaut pour une caméra : thermique et grand angle se règlent séparément (« Caméra retouchée »).
- Les flous, les formes et les couleurs sont posés sur l'image d'une caméra : si le passage est compilé avec une autre caméra, refaites-les sur celle-ci (« Caméra retouchée »).

Un passage marqué sensible (visage, plaque) sans flou est rappelé en jaune avant de créer une vidéo ; le rappel n'empêche pas le calcul.

## Extraire des morceaux d'une vidéo compilée

Pour reprendre quelques moments sans reparcourir tous les rushs, repartez de la vidéo compilée :

- **Mode PC** : dans la liste des interventions, « Préparer la vidéo compilée pour en extraire des morceaux » (une fois), puis « Extraire des morceaux de la vidéo compilée ». Les marqueurs posés sur la vidéo compilée sont enregistrés à part : ceux des rushs et la fiche de l'intervention ne changent pas.
- **Mode navigateur** : « Choisir les vidéos », puis le fichier `ESAM_Compilation_...mp4`.

Marquez les morceaux à garder (Début, Fin), retouchez-les au besoin, puis « Créer les extraits » dans l'étape Compilation (ou « Extraits bruts » dans l'étape Export). L'habillage est alors d'office sur « Aucun : extraits bruts » : ni carton de transition, ni heure incrustée, ni logo. La sortie est une seule vidéo (`ESAM_Extraits_...mp4`) ou un fichier par passage. Le même réglage « Habillage » existe à partir des rushs, pour sortir des passages bruts sans passer par une vidéo compilée.

## Réel, story et vidéo LinkedIn (étape Réseaux)

L'étape Réseaux monte une vidéo courte à partir des passages marqués. « Format de la vidéo », en tête du montage, choisit sa forme :

- **Réel 9:16** (1080 x 1920) : réel ou story pour Instagram et Facebook ;
- **LinkedIn 4:5** (1080 x 1350) : la plus grande place dans le fil LinkedIn sur téléphone ;
- **LinkedIn carré 1:1** (1080 x 1080) : s'affiche en entier sur téléphone comme sur ordinateur.

Le cadre bleu du cadrage et l'aperçu prennent la forme choisie ; le montage, le cadrage, les retouches et l'habillage sont les mêmes pour les trois formats, on peut donc fabriquer le réel puis la vidéo LinkedIn sans rien refaire. Après un changement de format, vérifiez dans l'aperçu la place du titre et du logo. Une vidéo produite par l'outil n'a pas de sous-titres : ne joignez jamais le fichier `.commentaires-ESAM.srt` à un post, il contient les commentaires internes.

Sur téléphone, l'étape se parcourt par trois volets, sans autre choix à faire avant l'image : **Montage**, **Passage** (l'image du passage en cadrage) et **Habillage** (le titre, puis l'aperçu du réel complet avec tout ce qui est posé dessus). Sur PC, tout est sur un écran : l'image à gauche, avec « Cadrage » ou « Aperçu du réel » au-dessus, le montage et l'habillage à droite ; en aperçu, les réglages des éléments se placent à droite de l'image verticale.

1. **Montage** : « Passages à ajouter » liste les marqueurs qui ne sont pas encore dans le réel ; touchez-en un pour l'ajouter, ou « Tout ajouter » (annulable). Chaque passage ajouté reprend le passage du marqueur (6 s autour d'un repère), dans l'ordre chronologique. « Ordre et retrait » fait apparaître sur chaque ligne les flèches, qui changent l'ordre, le bouton « Dupliquer » et la croix, qui retire du réel. **Dupliquer** un plan (aussi en bas des réglages du passage) pose juste après une copie indépendante du même passage, avec sa propre plage, son cadrage, sa vitesse et son texte : par exemple une vue d'ensemble puis un gros plan du même moment. Les retouches (flous, flèches, ralentis) restent celles du passage, communes aux copies. Supprimer le marqueur retire tous ses plans du réel, et « Annuler » les remet. « Photos à ajouter » propose les photos JPEG, en une bande à faire défiler : en mode PC, celles du dossier de l'intervention et de son sous-dossier `Photos` ; en mode navigateur, celles choisies avec les vidéos, trouvées dans le dossier des rushs ou ajoutées par « Choisir des photos JPEG ». Une photo dure 2 à 8 s (4 s par défaut), avec un zoom lent qu'on peut couper, et se cadre comme un passage.
2. **Passage** (cadrage) : touchez un passage, ou « Cadrer » dans le message qui suit un ajout. Les flèches de part et d'autre du nom du passage passent au précédent ou au suivant, sans revenir au montage. L'image entière s'affiche avec le cadre au format en bleu. Glissez le cadre, de côté comme de haut en bas : à l'arrêt, il est posé pour tout le passage ; pendant la lecture, gardez le doigt sur l'image et suivez l'animal, le cadre enregistre votre mouvement et le lisse. **Taille du cadre** : le rond bleu au coin du cadre, le curseur « Taille du cadre », la molette ou le pincement à deux doigts l'agrandissent ou le réduisent, du zoom x4 jusqu'à « Image entière » : toute l'image est visible et le reste du format est rempli par la même image floutée et assombrie, comme le font les réseaux (utile pour une vidéo de téléphone en portrait dans un format 4:5 ou carré). « Plein cadre » revient au plus grand cadre qui tient dans l'image. Une taille différente posée à un autre instant du passage fait un zoom progressif. Les points de cadrage apparaissent en noir sur la barre. « Début ici » et « Fin ici » raccourcissent ou allongent le passage pour le réel sans toucher au marqueur. Choisissez aussi la caméra (quand plusieurs ont de l'image), la vitesse dans le réel (accéléré x2 à x8, signalé à l'image) et un texte court, affiché tout le passage ou 3, 5 ou 8 s (un texte plus long que le passage continue sur les suivants).
   **Retouches** : « Retoucher », à côté de « Début ici » et « Fin ici », ouvre les retouches du passage (voir plus haut) : flous qui suivent un visage ou une plaque, flèches et cercles qui suivent l'animal, ralentis et accélérés. Elles sont appliquées quel que soit le cadrage et valent aussi pour la vidéo compilée. Sur une photo, « + Flou (visage, plaque) » pose directement une zone floutée (petite, moyenne ou grande).
3. **Habillage** : titre d'accroche (affiché 3, 5 ou 8 s, ou tout le réel) ; l'aperçu le montre pendant qu'on le tape. Repliés sous « Logo, carton de fin, musique », avec leur état en résumé : logo ESAM (cartouche avec le nom, logo seul cerclé de blanc, ou aucun), carton de fin ESAM (logo, texte, site), musique (envoyée sur le PC en mode PC, avec le moment où elle démarre, fondu de fin automatique).
4. **Aperçu du réel** (volet Habillage sur téléphone) : lecture du montage complet au format choisi, sur une version allégée des vidéos, avec textes et musique. La liste « Sur l'image », sous l'aperçu, donne tout ce qui est posé sur la vidéo (titre, logo, textes des passages, éléments ajoutés) : touchez-en un, dans la liste ou sur l'image, pour l'amener à l'écran et le sélectionner ; « Terminé », à côté de son nom, le relâche. Glissez-le pour le déplacer ; tirez le rond bleu, la molette ou le curseur « Taille » pour changer sa taille ; choisissez sa couleur (blanc, jaune, bleu, rouge, noir) et, pour un texte, avec ou sans bandeau. « Remettre à sa place » revient à la position d'origine (celle du gabarit s'il y en a un). Les boutons « Placer, taille et couleur » (Habillage, texte d'un passage) y mènent aussi.
   **Grille et aimant** : le bouton « Grille », posé sur l'aperçu (et retenu d'une fois sur l'autre), montre les tiers, le centre et, en rouge, les marges où les réseaux posent la légende, le nom du compte et les boutons (plus larges en 9:16). Pendant un glissement, l'élément s'aimante au centre, aux tiers, aux marges et aux bords et centres des autres éléments ; un trait rouge montre l'accroche. Alt ou Maj (ou un second doigt) déplace sans aimant. La grille et les traits ne sont jamais dans la vidéo.
   **Même place sur tous les plans** : les textes des passages partagent une seule place, une taille et une couleur ; déplacer le texte d'un passage déplace celui de tous. « Place propre à ce passage » le détache. **Gabarit** (sous la liste « Sur l'image ») : « Enregistrer comme gabarit » garde, pour le format en cours (9:16, 4:5 ou carré), les places, tailles et couleurs du titre, du logo et des textes de passage, dans ce navigateur et pour toutes les interventions ; un nouveau réel le reçoit d'office, et « Appliquer le gabarit » le remet sur un réel existant (annulable).
   **Textes libres et formes** : « + Texte », « + Flèche », « + Cercle », « + Cadre » ajoutent un élément au moment affiché dans l'aperçu. Réglez sa place, sa taille, sa couleur, son orientation (formes), son début (« Commencer à ») et sa durée (2 à 8 s ou jusqu'à la fin). Les éléments suivent le temps du réel : si vous changez le montage, revérifiez leur moment.
5. **Créer le réel** ou **Créer la story** (en 9:16), **Créer la vidéo LinkedIn** (en 4:5 ou 1:1) : le PC calcule à partir des rushs d'origine. Un passage marqué sensible (visage, plaque, animal blessé, lieu) porte une pastille jaune dans le montage ; s'il n'a aucun flou, un rappel s'affiche au-dessus des boutons. Le rappel n'empêche pas de créer la vidéo. La story est découpée en morceaux de 60 s maximum, de préférence entre deux passages (le bouton devient alors « Créer 3 stories », par exemple).

Par défaut, les textes et le logo sont placés à l'écart du bas de l'image et du bord droit, où Instagram affiche la légende et ses boutons. Le réglage du réel est enregistré avec la fiche. Musique : uniquement une musique libre de droits ou dont l'ESAM a les droits ; sinon, publiez sans musique et ajoutez-la dans Instagram ou Facebook.

En mode navigateur, le son est encodé en AAC sur la plupart des ordinateurs et téléphones ; si le navigateur ne propose que l'Opus, l'appli le signale, et le mode PC reste la voie sûre.

## Export : vidéos, liste des plans, fiche

L'étape Export réunit une carte par sortie, avec sa durée et son état :

- **Vidéo compilée** et **Extraits bruts** : ouvrent le même calcul que le bouton de l'étape Compilation (habillage avec cartons, heure et logo, ou aucun) ;
- **Réseaux sociaux** : « Créer le réel », « Créer la story » ou « Créer la vidéo LinkedIn », selon le format choisi dans l'étape Réseaux, qui s'affiche derrière le calcul ;
- **Liste des plans** : un texte Markdown pensé pour être collé dans une conversation avec Claude afin de bâtir un storyboard. En tête, l'intervention, la date et la durée totale ; puis, pour chaque plan, son heure de début et de fin, sa durée, la caméra compilée, son nom, ses thèmes, son intérêt, sa sensibilité, « Ce qu'on voit » et le texte du carton ; enfin l'ordre du montage réseaux s'il existe (plans, plages, vitesses, textes). « Copier » le met dans le presse-papiers ; « Télécharger .md » le télécharge et, en mode PC ou avec le dossier des rushs ouvert, l'enregistre aussi dans le dossier de l'intervention (`ESAM_Plans_<date>_<mission>.md`). La liste peut sortir de l'ESAM : les commentaires internes n'y figurent que si « Inclure les commentaires internes » est coché ;
- **Fiche de dérushage** : la fiche complète, commentaires internes compris, à garder à l'ESAM.

## Choisir la caméra de chaque passage

La vidéo compilée prend, pour chaque passage, une seule caméra. Elle se choisit en un toucher, comme le nom du passage :
- dans la colonne Marqueurs, sous le nom ;
- dans l'étape Compilation, à côté du nom ;
- pendant la lecture, dans le bandeau sous les boutons Début, Fin, Repère : quand la piste affichée n'est pas celle retenue, le bouton « Compiler en <caméra> » la retient pour ce passage.

Le bandeau indique toujours la caméra réellement compilée (« compilée en zoom »). Si la caméra choisie n'a pas d'image sur le passage, la première caméra disponible est prise à la place. La piste affichée pendant la lecture reste libre et ne change rien à la compilation.

## Limites connues

- Les chapitres inscrits dans la vidéo sont lus par VLC, QuickTime et la plupart des lecteurs, mais pas par l'aperçu de Google Drive, dont le panneau « Chapitres » est généré par Gemini. Ils ne sont produits qu'en mode PC.

- L'heure n'est pas incrustée sur la vidéo compilée par le PC (elle figure sur les cartons).
- Le suivi automatique d'un flou ou d'une forme retrouve un motif d'une image à la suivante : il décroche si le sujet est masqué, change brusquement d'aspect ou sort de l'image, et une zone uniforme (neige, ciel) ne se suit pas. Il ne reconnaît pas les visages : c'est à vous de poser la zone et de relire le passage avant publication.
- Un ralenti répète les images des rushs (30 images par seconde) : à x0,25 le mouvement est saccadé.
- Le son n'est pas conservé dans la vidéo compilée.
- La lecture à x16 dépend du débit montant de la connexion de la maison ; si l'image saccade, préférez x8 (appui long ou clic droit sur x16 pour choisir la vitesse).

## Changelog

| Version | Date | Changement |
|---|---|---|
| 0.21 | 2026-11-24 | Suite de l'allègement. Pistes : les numéros de marqueurs trop proches se regroupent (« 3-6 »), un toucher zoome jusqu'à les séparer et « - » ramène au zoom d'avant ; bords des passages toujours attrapables, même sur un vol de 3 h ; plus de rangée « Pistes » (zoom dans le coin) ; marqueur sensible jaune et carré. Planche : piste et intervalle sur une rangée, heure et « + Repère » posés sur la vignette, trois fois plus de vignettes à l'écran sur téléphone. Fiche de marqueur : sensibilité, caméra et intérêt en vue, le reste replié avec son état affiché ; elle s'enregistre en se fermant (Terminé, Échap ou appui à côté) et « Annuler » dans le message la remet comme avant ; un marqueur sans nom n'est plus renommé « Sans titre ». Réel : une seule rangée de volets sur téléphone (Passage pour cadrer, Habillage pour le titre et l'aperçu), « Tout ajouter » les passages, passage suivant d'un toucher pendant le cadrage, flèches et croix rangées sous « Ordre et retrait », logo, carton de fin et musique repliés. |
| 0.20 | 2026-11-24 | Interface allégée, moins de gestes. Visionner : après Début et Fin ou Repère, le bandeau propose les noms courants, un toucher nomme le marqueur sans ouvrir de fiche ni arrêter la lecture ; sur téléphone, le nom de l'intervention tient sur une ligne et laisse la place à l'image et aux pistes. Sommaire : une carte compacte par marqueur (deux fois plus de marqueurs à l'écran sur téléphone, trois fois plus sur PC), commentaire interne sur une ligne qui grandit, « Créer la vidéo compilée » en tête. Vidéo compilée : format, marge et heure incrustée repliés sous « Réglages », le dialogue tient sur un écran. Réel : « Début ici », « Fin ici » et « Retoucher » sur une rangée, plus de boutons inactifs. Même mot partout pour ouvrir la fiche d'un marqueur (« Modifier ») ; bouton « Changer d'intervention » retiré (le retour est en haut à gauche). |
| 0.19 | 2026-11-24 | Une piste par appareil : les vidéos de téléphone sont rangées d'après la marque et le modèle lus dans le fichier (« iPhone 15 Pro », « Google Pixel 7 »...) ; une vidéo repassée par une messagerie, qui les a perdus, reste sur « Autre caméra ». Une vidéo compilée rouverte avec d'autres vidéos garde sa propre piste « Vidéo montée » au lieu d'être recouverte. Les passages déjà marqués suivent leur vidéo sur sa nouvelle piste. |
| 0.18 | 2026-11-24 | Onglet Réel : format « LinkedIn 4:5 » ou « LinkedIn carré 1:1 » en plus du réel 9:16, avec le même montage, cadrage et habillage ; bouton « Créer la vidéo LinkedIn ». |
| 0.17 | 2026-11-23 | Retouches d'un passage (bouton « Retoucher ») : flous ovales ou rectangles, doux ou pixelisés, qui suivent un visage ou une plaque (suivi automatique ou au doigt) ; flèches et cercles « au crayon » qui suivent l'animal ; ralenti et accéléré à partir d'un instant. Elles valent pour la vidéo compilée, les extraits et le réel. Extraits bruts : habillage « Aucun » (ni carton, ni heure, ni logo), en une vidéo ou un fichier par passage, choisi d'office quand on repart d'une vidéo compilée ; en mode PC, la vidéo compilée d'une intervention se rouvre depuis la liste pour en extraire des morceaux. Les messages s'affichent aussi par-dessus un dialogue ouvert. |
| 0.16 | 2026-11-22 | Lecteur : l'image ne reste plus figée sur une vignette après un glissement sur la règle ou sur le bord d'un passage (l'aperçu se referme toujours, et il occupe la même taille que la vidéo) ; après « Voir » un passage, un saut plus loin ne met plus la lecture en pause ; après une coupure de connexion, « Lire » reprend la vidéo. Pistes : « Écran » passe en première ligne (la caméra choisie par défaut pour la vidéo compilée et le réel ne change pas). |
| 0.15 | 2026-11-22 | Ergonomie revue de bout en bout. Sécurité : supprimer un marqueur s'annule (le passage revient aussi dans le réel) ; un passage sensible est rappelé en jaune avant de créer un réel ou une vidéo ; avertissement si l'on ferme l'onglet pendant un calcul dans le navigateur. Téléphone : fiche de marqueur plus courte avec Enregistrer toujours visible, boutons et pistes qui ne bougent plus pendant la lecture, paysage utilisable, cibles de 44 px, plus de zoom automatique à la saisie. Réel : volets Montage, Passage, Habillage, « Cadrer » après un ajout, titre qui ne recouvre plus le cartouche ESAM, nom du fichier produit en fin de calcul. Sommaire remis d'aplomb et en deux colonnes sur PC ; retour à la liste des interventions par le logo ; aide dans l'appli (bouton Aide) ; filtre dans la liste des interventions. Clavier, focus et contrastes lisibles au soleil ; thème automatique, clair ou sombre (Plus d'options). Vocabulaire unifié : intervention, passage, repère. |
| 0.14 | 2026-10-27 | Dossier de travail : « Ouvrir le dossier des rushs » importe toutes les vidéos et photos du dossier et de ses sous-dossiers (sauf `proxies`) et reprend la fiche qui s'y trouve ; sur ordinateur (Chrome, Edge), la fiche et les vidéos produites y sont enregistrées et le dernier dossier se rouvre d'un clic (« Reprendre ») ; sur téléphone, le dossier est importé avec les noms d'origine, mais le travail reste gardé dans le navigateur |
| 0.13 | 2026-10-27 | Téléphone : vidéos choisies dans la galerie (noms remplacés par des numéros) réparties sur des pistes distinctes au lieu d'une seule, thermique reconnue à son format d'image, message invitant à passer par l'application Fichiers pour garder les noms DJI ; le bouton « Choisir les vidéos » ouvre de préférence le gestionnaire de fichiers ; vignettes de la piste affichée calculées en premier |
| 0.12 | 2026-10-20 | Appli utilisable sans Internet (bibliothèques et polices embarquées) ; ouverture d'une longue intervention en mode PC bien plus rapide et plus légère en mémoire ; pincement à deux doigts pour zoomer la timeline ; sur téléphone, messages affichés sous l'en-tête, onglet Réel en trois volets (Montage, Passage, Habillage), chronologie RETEX repliée tant qu'aucun décollage n'est marqué, un seul bouton « Voir » par passage ; nombre de passages du réel sur l'onglet ; documentation technique dans `docs/ARCHITECTURE.md` |
| 0.11 | 2026-10-20 | Réel : flou doux aux bords fondus à la place des pixels ; liste « Sur l'image » pour choisir et déplacer chaque texte ; textes libres, flèches, cercles et cadres à placer ; taille et couleur des titres et textes, texte avec ou sans bandeau |
| 0.10 | 2026-10-20 | Réel : logo ESAM plus visible (cartouche avec le nom ou logo cerclé de blanc) ; titre, logo et textes déplaçables et agrandissables dans l'aperçu ; durée du titre et des textes réglable ; photos JPEG dans le montage (zoom lent) ; zones de flou qui suivent l'action |
| 0.9 | 2026-10-20 | Onglet Réel : montage vertical 1080 x 1920 pour réel et story, cadre qui suit l'action, accéléré, titre d'accroche, texte par passage, carton de fin ESAM, musique ; story découpée en morceaux de 60 s ; onglets lisibles sur petit téléphone |
| 0.8.1 | 2026-10-15 | Code publié sur GitHub ; mode navigateur sur GitHub Pages ; `app.html` renommé `index.html` ; réglages modèles dans `config.exemple.json` ; script `mettre-a-jour.ps1` ; correction d'un conflit d'écriture de l'historique des calculs quand deux calculs se terminent en même temps |
| 0.8 | 2026-10-15 | Caméra de chaque passage choisie directement dans la colonne Marqueurs et le Sommaire ; bouton « Utiliser <caméra> » dans le bandeau « Dans la plage » ; caméra réellement compilée affichée dans le bandeau |
| 0.7 | 2026-10-11 | Petit logo ESAM en bas à droite de toutes les images ; heure incrustée sans le nom de la caméra ; commentaires internes par passage, signés, en fichier de sous-titres à part ; « Note pour la com » renommée « Texte du carton » |
| 0.6 | 2026-10-11 | Fiche enregistrée automatiquement à chaque modification : dans le dossier de l'intervention en mode PC, dans le dossier des rushs en mode navigateur (bouton « Ouvrir le dossier des rushs », Chrome ou Edge) ; une seule version de fiche par séance de travail ; téléchargement direct au lieu du copier-coller ailleurs |
| 0.5 | 2026-10-11 | Reprendre une fiche remplace les marqueurs au lieu de les cumuler (annulable) ; bandeau « Dans la plage » sous la vidéo avec Début ici, Fin ici, Prolonger ; bords des plages ajustables en glissant sur les pistes ; marge de compilation à 0 s par défaut (0, 5 ou 10 s, appliquée aux plages) ; durée de la vidéo compilée affichée sous la mission et sur le bouton de compilation |
| 0.4 | 2026-10-09 | Chapitres dans la vidéo compilée (un par passage, titre et heure) et fichier de chapitres au format YouTube ; titre de la vidéo dans ses métadonnées |
| 0.3 | 2026-10-09 | Version affichée dans l'appli (badge v0.3, mode PC ou navigateur, alerte si versions différentes) ; mode navigateur : vidéo écrite par morceaux au lieu d'un bloc mémoire unique qui échouait à 100 %, erreur détaillée affichée durablement |
| 0.2 | 2026-10-08 | Fiabilisation de la vidéo compilée : copie vers le Drive sans attributs, contrôle de l'espace disque et de la vidéo assemblée, erreurs affichées durablement, historique des calculs conservé après redémarrage, réglage `dossier_travail` |
| 0.1 | 2026-10-08 | Première version : serveur local, proxies, fiche, photo, vidéo compilée, veille |
