---
titre: Dérushage drone ESAM - installation sur le PC de traitement
statut: brouillon
version: 0.12
date_maj: 2026-10-20
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
3. « Ouvrir » charge l'intervention. Début, Fin et Repère posent les marqueurs ; ils sont enregistrés automatiquement sur le PC, dans le sous-dossier `.derushage` de l'intervention.
4. L'icône d'appareil photo enregistre l'image en pleine résolution dans le sous-dossier `Photos`.
5. La fiche Markdown est enregistrée automatiquement dans le dossier de l'intervention, quelques secondes après chaque modification (l'heure du dernier enregistrement s'affiche sous le nom de la mission) ; onglet Sommaire, « Créer la vidéo compilée » envoie le montage au PC, qui dépose la vidéo dans le dossier de l'intervention.
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
| `Photos/` | Photos pleine résolution |
| `ESAM_Compilation_<date>_<mission>.mp4` | Vidéo compilée, avec un chapitre par passage |
| `ESAM_Compilation_<date>_<mission>.commentaires-ESAM.srt` | Commentaires internes signés, en sous-titres à part (jamais incrustés dans la vidéo) |
| `ESAM_Reel_<date>_<mission>.mp4` | Réel vertical 1080 x 1920 (onglet Réel) |
| `ESAM_Story_<date>_<mission>_1sur2.mp4`... | Story découpée en morceaux de 60 s maximum |
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

Dans l'onglet Sommaire, chaque passage a un champ « Commentaire interne ESAM ». Le champ « Auteur de la vidéo compilée » se remplit une fois et signe tous les commentaires. À la compilation, ces commentaires partent dans un fichier de sous-titres `.commentaires-ESAM.srt` posé à côté de la vidéo, affiché pendant le passage concerné.

- VLC l'affiche automatiquement (même dossier, nom commençant comme celui de la vidéo).
- Dans Google Drive : ouvrir la vidéo, menu des trois points, « Gérer les sous-titres », ajouter le fichier `.srt`. Seuls ceux qui regardent la vidéo dans le Drive les voient.
- Le fichier MP4 lui-même ne contient pas les commentaires : il peut être publié tel quel.

## Réel et story (onglet Réel)

L'onglet Réel monte une vidéo verticale 1080 x 1920 pour Instagram et Facebook à partir des passages marqués.

1. **Montage** : « Ajouter des passages » liste les marqueurs. Chaque passage ajouté reprend la plage du marqueur (6 s autour d'un repère), dans l'ordre chronologique ; les flèches changent l'ordre, la croix le retire. « Ajouter des photos » propose les photos JPEG : en mode PC, celles du dossier de l'intervention et de son sous-dossier `Photos` ; en mode navigateur, celles choisies avec les vidéos, trouvées dans le dossier des rushs ou ajoutées par « Choisir des photos JPEG ». Une photo dure 2 à 8 s (4 s par défaut), avec un zoom lent qu'on peut couper, et se cadre comme un passage.
2. **Cadrage du passage** : touchez un passage. L'image entière s'affiche avec le cadre vertical en bleu. Glissez le cadre : à l'arrêt, il est posé pour tout le passage ; pendant la lecture, gardez le doigt sur l'image et suivez l'animal, le cadre enregistre votre mouvement et le lisse. Les points de cadrage apparaissent en noir sur la barre. « Début ici » et « Fin ici » raccourcissent ou allongent le passage pour le réel sans toucher au marqueur. Choisissez aussi la caméra, la vitesse (accéléré x2 à x8, signalé à l'image) et un texte court, affiché tout le passage ou 3, 5 ou 8 s (un texte plus long que le passage continue sur les suivants).
   **Flous** : « + Ajouter un flou » pose une zone floutée aux bords fondus (petite, moyenne ou grande) pour cacher un visage, une plaque ou un lieu. Choisissez « Flou 1 » (ou « Le cadre ») pour dire ce que le doigt ou la souris déplace. À l'arrêt, la zone est posée pour tout le passage ; pendant la lecture, gardez le doigt dessus et suivez : elle enregistre le mouvement (points jaunes sur la barre). Les flous sont appliqués dans la vidéo finale, quel que soit le cadrage.
3. **Habillage** : titre d'accroche (3, 5 ou 8 s, ou tout le réel), logo ESAM (cartouche avec le nom, logo seul cerclé de blanc, ou aucun), carton de fin ESAM (logo, texte, site), musique (envoyée sur le PC en mode PC, avec le moment où elle démarre, fondu de fin automatique).
4. **Aperçu du réel** : lecture du montage complet en vertical, sur les proxies, avec textes et musique. La liste « Sur l'image », sous l'aperçu, donne tout ce qui est posé sur la vidéo (titre, logo, textes des passages, éléments ajoutés) : touchez-en un, dans la liste ou sur l'image, pour l'amener à l'écran et le sélectionner. Glissez-le pour le déplacer ; tirez le rond jaune, la molette ou le curseur « Taille » pour changer sa taille ; choisissez sa couleur (blanc, jaune, bleu, rouge, noir) et, pour un texte, avec ou sans bandeau. « Remettre à sa place » revient à la position d'origine. Les boutons « Placer, taille et couleur » (Habillage, texte d'un passage) y mènent aussi.
   **Textes libres et formes** : « + Texte », « + Flèche », « + Cercle », « + Cadre » ajoutent un élément au moment affiché dans l'aperçu. Réglez sa place, sa taille, sa couleur, son orientation (formes), son début (« Commencer à ») et sa durée (2 à 8 s ou jusqu'à la fin). Les éléments suivent le temps du réel : si vous changez le montage, revérifiez leur moment.
5. **Créer le réel** ou **Créer la story** : le PC calcule à partir des rushs d'origine. La story est découpée en morceaux de 60 s maximum, de préférence entre deux passages.

Par défaut, les textes et le logo sont placés à l'écart du bas de l'image et du bord droit, où Instagram affiche la légende et ses boutons. Le réglage du réel est enregistré avec la fiche. Musique : uniquement une musique libre de droits ou dont l'ESAM a les droits ; sinon, publiez sans musique et ajoutez-la dans Instagram ou Facebook.

En mode navigateur, le son est encodé en AAC sur la plupart des ordinateurs et téléphones ; si le navigateur ne propose que l'Opus, l'appli le signale, et le mode PC reste la voie sûre.

## Choisir la caméra de chaque passage

La vidéo compilée prend, pour chaque passage, une seule caméra. Elle se choisit en un toucher, comme le nom du passage :
- dans la colonne Marqueurs, sous le nom ;
- dans le Sommaire, à côté du nom ;
- pendant la lecture, dans le bandeau « Dans la plage » : quand la piste affichée n'est pas celle retenue, le bouton « Utiliser <caméra> » la retient pour ce passage.

Le bandeau indique toujours la caméra réellement compilée (« compilée en zoom »). Si la caméra choisie n'a pas d'image sur la plage, la première caméra disponible est prise à la place. La piste affichée pendant la lecture reste libre et ne change rien à la compilation.

## Limites connues

- Les chapitres inscrits dans la vidéo sont lus par VLC, QuickTime et la plupart des lecteurs, mais pas par l'aperçu de Google Drive, dont le panneau « Chapitres » est généré par Gemini. Ils ne sont produits qu'en mode PC.

- L'heure n'est pas incrustée sur la vidéo compilée par le PC (elle figure sur les cartons).
- Le son n'est pas conservé dans la vidéo compilée.
- La lecture à x16 dépend du débit montant de la connexion de la maison ; si l'image saccade, préférez x8.

## Changelog

| Version | Date | Changement |
|---|---|---|
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
