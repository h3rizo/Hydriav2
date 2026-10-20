# Serious Game Hydria

## Objectif
Module independant de mini-jeu 2D pour une premiere simulation jouable de gestion d'un service d'eau potable dans Hydria.

## Emplacement
- App Django: `backend/apps/serious_game/`
- Template d'integration: `backend/apps/serious_game/templates/serious_game/index.html`
- Frontend Phaser: `backend/apps/serious_game/static/serious_game/js/`
- Styles du module: `backend/apps/serious_game/static/serious_game/css/serious_game.css`

## Acces
- URL: `https://planning.hydria.mg/serious-game/` (raccourci `/academy/`) ; l'ancienne adresse `www.hydria.mg/serious-game/` redirige vers le sous-domaine planning (depuis le 2026-10-11)
- Nom de route: `serious_game:home` (URLConf `hydria/urls_planning.py`)
- Entrees UI: bouton "Academy" de la navbar planning, bouton "Hydria Academy" et section "Formation" du sidebar planning, banniere sur `planning.hydria.mg/accueil/`
- Les templates etendent `planning_shell_base_template` (shell planning sur le sous-domaine)

## Lancement
1. Demarrer Django comme d'habitude.
2. Ouvrir `http://127.0.0.1:8000/serious-game/` une fois connecte.
3. Le jeu charge Phaser via CDN et n'a pas besoin d'un build frontend separe.

## Gameplay V1
- Un personnage polyvalent controle au clavier.
- Une scene 2D avec plateformes, collisions et decor simple.
- Un ouvrage principal pouvant tomber en panne.
- Deux usagers a gerer.
- Reparation chronometree avec gain/perte de score.
- Paiements a collecter avant echeance, puis statuts impaye / coupe / remise en eau.
- HUD avec score, satisfaction, pannes, paiements et temps.
- Victoire: tenir jusqu'a la fin avec le score minimal.
- Echec: satisfaction trop basse ou score insuffisant en fin de mission.

## Extension
- Ajouter un role en creant une nouvelle entite ou capacite dans `static/serious_game/js/`.
- Ajouter de nouvelles scenes dans `static/serious_game/js/scenes/`.
- Faire evoluer les regles dans `static/serious_game/js/systems/GameState.js`.
- Remplacer les textures temporaires generees par Phaser par de vrais assets plus tard.
