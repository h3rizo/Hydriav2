# Android — bilan de la Phase 1

## Périmètre livré

La fondation mobile couvre le contrat OpenAPI v1, l'authentification JWT mobile, la
conservation sécurisée de la session, la navigation protégée et un design system Compose
clair/sombre. L'écran après connexion affiche uniquement l'identité et les capacités
réelles renvoyées par Django ; il ne simule aucune donnée métier.

## Adaptations Django réalisées

- conservation des routes historiques `/api/` et ajout des routes versionnées `/api/v1/` ;
- ajout connexion, inscription, session, refresh rotatif et révocation sous
  `/api/v1/mobile/auth/` ;
- ajout des capacités `roles`, `is_admin`, `is_listed_as_coach`,
  `can_access_coach_space` et `has_active_coach` ;
- jeton d'accès de 10 minutes, refresh de 30 jours, rotation et blacklist ;
- schéma OpenAPI 3.1 généré dans `docs/openapi-v1.yml` ;
- documentation interactive réservée aux administrateurs ;
- authentification Web par session conservée ; Basic Auth désactivable et désactivée par
  défaut lorsque Django n'est pas en mode DEBUG.

Les corrections P0 associées protègent aussi les photos de progression, empêchent la
mutation d'un repas partagé par un simple participant, vérifient les appartenances lors
des créations de repas/séances et corrigent les calculs de portions du tableau de bord.

## Vérifications

- `python manage.py check` ;
- `python manage.py makemigrations --check --dry-run` ;
- tests Django des comptes, profils, progression, repas et fitness ;
- `gradlew assembleDebug` ;
- tests du dépôt Android, du mapping DTO et du renouvellement/échec du refresh ;
- `gradlew lintDebug` avant clôture de phase.

## Suite prévue

La Phase 2 ajoutera de vrais modules fonctionnels au fur et à mesure : tableau de bord,
profil, plans de repas, courses, programme sportif, séance active et mesures. Room,
DataStore, WorkManager, Coil et le cache hors connexion seront introduits là où ils ont
un consommateur réel. Les photos, le foyer et le coaching restent respectivement dans
les Phases 3 et 4 définies par l'audit.

## Déploiement

Aucun déploiement de production n'est inclus dans cette phase locale. Le backend doit
être validé et déployé avant que l'APK configuré avec l'URL de production puisse utiliser
les nouvelles routes. Un changement futur dans `bienetre/frontend/` devra être suivi de
`npm run build` sur le VPS avant le redémarrage de `bienetre-nuxt` et de Nginx.

