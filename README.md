# esam-rush : dérushage drone ESAM

Appli pour traiter rapidement un gros volume de rushs multipistes (drone).

Outil de l'ESAM (Equipe de Secours Animalier en Montagne) pour annoter les rushs filmés pendant un secours et préparer les images pour l'équipe communication : une piste par caméra (grand angle, zoom, thermique, téléphones) alignée sur une timeline commune, marqueurs de plages et de points, sommaire, chronologie RETEX, photos, vidéo compilée en résolution d'origine avec cartons, chapitres et logo, et réel ou story verticale pour les réseaux sociaux.

- **Mode navigateur** : https://julok35.github.io/esam-rush/ (vidéos choisies dans l'appareil, calculs faits par le navigateur, Chrome ou Edge recommandés).
- **Mode PC** : `server.py` tourne sur un PC Windows qui voit le Drive des rushs, fabrique les proxies et monte la vidéo avec ffmpeg ; le téléphone y accède par Tailscale. Installation et utilisation : [LISEZMOI.md](LISEZMOI.md).

## Contenu

| Fichier | Rôle |
|---|---|
| `index.html` | L'appli (un seul fichier, sans étape de construction) |
| `server.py` | Serveur du PC (Python, bibliothèque standard + ffmpeg) |
| `config.exemple.json` | Modèle des réglages du PC |
| `installer.ps1`, `mettre-a-jour.ps1` | Installation et mise à jour sur Windows |
| `tests/` | Faux rushs et test de bout en bout |
| `CLAUDE.md` | Consignes pour Claude Code |

Licence MIT, voir `LICENSE`.
