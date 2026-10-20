# Android — Phase 2 (MVP utilisateur)

Date de vérification : 31 août 2026.

## Direction visuelle

L’interface Android reprend l’identité observée dans le frontend Nuxt et dans
`frontend/assets/images/wellness/hero-dashboard.png`, sans copier la grille Web :

- fond vert nuit avec halos émeraude/bleu ;
- accent principal orange `#FF8A1E` ;
- cartes translucides aux contours discrets ;
- grands indicateurs nutritionnels et typographie sans-serif dense ;
- couleurs fonctionnelles émeraude, or, violet, bleu et rose ;
- navigation inférieure flottante adaptée aux zones sûres Android ;
- thèmes système, sombre et clair persistés dans DataStore.

Les valeurs sont exclusivement issues de Django. La carte Hydratation est
volontairement absente tant qu’aucun module backend ne la fournit.

## Fonctionnalités livrées dans ce jalon

| Fonction | Écran Android | Endpoint | Statut | Vérification |
|---|---|---|---|---|
| Dashboard | Accueil | `GET /api/v1/profiles/dashboard/` | Terminé | DTO + ViewModel + Compose |
| Profil | Profil | `GET/PATCH /api/v1/profiles/me/` | Partiel | DTO + validation + ViewModel |
| Métriques | Profil | `GET /api/v1/profiles/metrics/` | Terminé | DTO + affichage incomplet |
| Plan semaine | Repas | `GET /api/v1/meal-plans/` | Terminé | DTO + ViewModel |
| Génération | Repas | `POST /api/v1/meal-plans/generate/` | Terminé | test génération/rechargement |
| Mutation repas | Repas | `PATCH/DELETE /api/v1/meal-plans/{id}/` | Terminé | test statut serveur |
| Ajout manuel | Repas | `POST /api/v1/meal-plans/` | Terminé | validation par compilation |
| Détail recette | Dialogue recette | `GET /api/v1/nutrition/recipes/` | Terminé en lecture | mapping ingrédients/macros |
| Recette personnelle | — | `POST /api/v1/nutrition/recipes/` | À faire | Phase 3 |
| Courses par vendeur | Courses | `GET /api/v1/shopping/lists/` | Terminé connecté | DTO + ViewModel + Compose |
| Génération courses | Courses | `POST /api/v1/shopping/lists/generate/` | Terminé | validation période + tests |
| Coche/date/prix | Courses | `PATCH /api/v1/shopping/items/{id}/…` | Terminé connecté | calculs + mutation serveur |
| Article bien-être | Courses | `POST /api/v1/shopping/lists/{id}/manual-items/` | Terminé | validation client/serveur |
| Courses hors connexion | Courses | contrat batch absent | À faire | Phase 3 Room/WorkManager |
| Cycle sportif | Sport / Programme | `GET cycle`, `POST generate` | Terminé connecté | DTO + ViewModel + Compose |
| Séance du jour | Sport / Séance | `GET today`, `GET today-session` | Terminé connecté | reprise depuis `started_at` serveur |
| Exécution séance | Sport / Séance | `POST start/end/complete/postpone` | Terminé connecté | validations + tests ViewModel |
| Historique sportif | Sport / Séance | `GET workout-sessions` | Terminé en lecture | affichage des dernières entrées |
| Édition/réordonnancement | Sport / Programme | CRUD item + reorder | À faire | Phase 3 |
| Repos système | Sport / Séance | notification/vibration locale | À faire | minuterie visuelle livrée, reprise après mort du processus à faire |
| Mesures corporelles | Profil / Progression | `GET/POST /api/v1/progress/body-measurements/` | Terminé connecté | validation + rechargement serveur |
| Évolution corporelle | Profil / Progression | données des mesures | Terminé | indicateurs, delta et courbe du poids |
| Photos de progression | Profil / Progression | `/api/v1/progress/photos/` | Terminé en Phase 3 | Photo Picker, appareil photo, multipart privé |

### Écarts explicites du profil

La ville est affichée mais son sélecteur de métadonnées n’est pas encore
branché. La date de début et la note d’objectif ne sont pas exposées par le
contrat `profiles/me` actuellement consommé ; elles ne sont donc pas simulées.

## Architecture ajoutée

- `core:model` : modèles dashboard, profil, repas, recettes, fitness et progression ;
- `core:network` : DTO distincts, API Retrofit et repositories ;
- `core:preferences` : préférence de thème DataStore ;
- `core:designsystem` : tokens et composants visuels Bien-être ;
- `feature:dashboard`, `feature:profile`, `feature:meals`, `feature:shopping`, `feature:fitness`, `feature:progress` : écrans et ViewModels ;
- Coil 3.6 pour les images distantes avec cache mémoire/disque standard.

## États et sécurité

- chargement, vide, erreur réseau et session expirée sont distingués ;
- les réponses `401` ferment la session, les `403` ont un message dédié ;
- aucun jeton, mot de passe, photo ou donnée corporelle n’est journalisé ;
- toute mutation Repas est confirmée par la représentation retournée par Django ;
- une erreur réseau ne présente jamais une mutation locale comme synchronisée.

## Vérifications exécutées

```text
:app:assembleDebug                              OK
:core:network:testDebugUnitTest                OK
:feature:dashboard:testDebugUnitTest           OK
:feature:profile:testDebugUnitTest             OK
:feature:meals:testDebugUnitTest               OK
:feature:fitness:testDebugUnitTest             OK
:feature:progress:testDebugUnitTest            OK
:app:assembleDebugAndroidTest                  OK
:app:lintDebug                                 OK
```

Les tests Compose couvrent le dashboard réel sans hydratation inventée,
l’erreur récupérable, le profil/métriques, les courses vides, le programme
sportif vide et l’absence réelle de mesures corporelles. L’APK de tests instrumentés est
compilé ; son exécution sur un appareil reste une opération séparée.

## Limite de déploiement

Le backend Android v1 existe localement mais n’a pas été déployé dans ce jalon.
L’APK ne peut donc pas être validé de bout en bout contre la production tant
que ces routes ne sont pas présentes sur `bienetre.hydria.mg`.
