# Bien-être Hydria — Audit préalable Android et plan d'implémentation

Date de l'audit : 30 août 2026  
Périmètre : `bienetre/backend`, `bienetre/frontend`, préparation d'une application Android native  
Statut : audit terminé, aucune implémentation Android ou mutation Django réalisée

## 1. Résumé exécutif

Le backend Django contient déjà l'essentiel de la logique métier de Bien-être Hydria : profils et métriques, repas, recettes, génération des menus, courses, progression corporelle, programme sportif, séance du jour, foyer, repas partagés et coaching.

Il n'existe actuellement aucun projet Android dans `bienetre`. Le frontend de référence est une SPA Nuxt 3 comportant les parcours Accueil, Repas, Sport, Courses, Profil, Coach, Coaché et Administration.

La création de l'application Android ne doit pas commencer par la reproduction des écrans : plusieurs prérequis backend doivent être traités en premier.

Priorités bloquantes avant connexion de l'application mobile :

1. ajouter une API versionnée et documentée par OpenAPI ;
2. ajouter JWT accès court + refresh rotatif/révocable sans supprimer les sessions Web ;
3. protéger réellement les photos corporelles, actuellement servies par une URL `/media/` publique ;
4. corriger les permissions de modification des repas partagés ;
5. corriger le cycle d'acceptation d'une proposition de coaching ;
6. persister les séries et l'état de récupération pour reprendre une séance après fermeture ;
7. ajouter les métadonnées de synchronisation nécessaires au mode hors connexion des courses ;
8. stabiliser les contrats d'erreur, les rôles/capacités et les calculs agrégés exposés au mobile.

## 2. État technique vérifié

| Élément | Constat |
|---|---|
| Backend | Django 5.2.6, DRF 3.15.1, PostgreSQL en production, SQLite local |
| Authentification actuelle | `SessionAuthentication` + `BasicAuthentication`, cookies et CSRF |
| Auth mobile | Absente : aucun JWT, refresh, blacklist ou endpoint de révocation |
| Contrat API | Aucun OpenAPI/Swagger, aucune dépendance de schéma |
| API versionnée | Non, routes sous `/api/` |
| Frontend | Nuxt 3.14, SPA, appels avec `credentials: include` et `X-CSRFToken` |
| Android | Aucun `settings.gradle`, `build.gradle`, Manifest ou module Android |
| Outillage local | Android Studio installé, JDK embarqué 25.0.2, SDK 34 et 37 disponibles |
| Gradle | Pas de Gradle global ; le projet devra utiliser Gradle Wrapper |
| Tests backend | 2 tests seulement, tous deux sur l'inscription |
| Tests frontend | Aucun test applicatif trouvé |
| Vérification Django | `python manage.py check` : 0 erreur |
| Tests Django | `python manage.py test` : 2/2 réussis |
| Git | Le dossier `.git` local ne contient que `info` ; commits logiques impossibles tant que les métadonnées Git ne sont pas restaurées |

## 3. Authentification et permissions actuelles

### 3.1 Fonctionnement Web

- `POST /api/auth/login/` et `POST /api/auth/register/` sont exemptés de CSRF et ouvrent une session Django.
- Nuxt envoie le cookie de session avec `credentials: include`.
- Pour les mutations suivantes, Nuxt lit `csrftoken` et envoie `X-CSRFToken`.
- `GET /api/auth/me/` retourne l'utilisateur courant.
- `POST /api/auth/logout/` ferme la session, mais est également exempté de CSRF et accepte une requête non authentifiée.
- DRF autorise aussi Basic Auth globalement.

### 3.2 Rôles réellement disponibles

Il n'existe pas de champ de rôle unique.

- administrateur : `is_staff` ou `is_superuser` ;
- coach visible : `WellbeingProfile.is_listed_as_coach` ;
- coach actif : au moins une `CoachRelationship` acceptée où l'utilisateur est `coach` ;
- coaché actif : au moins une relation acceptée où l'utilisateur est `coache` ;
- utilisateur : tout compte authentifié.

Le mobile doit recevoir des capacités explicites, par exemple `can_access_coach_space`, `has_active_coach`, `is_admin`, plutôt que recalculer ces règles.

### 3.3 Cible mobile recommandée

Conserver les endpoints et `SessionAuthentication` Web existants. Ajouter sous `/api/v1/mobile/auth/` :

| Endpoint cible | Méthode | Entrée | Sortie |
|---|---|---|---|
| `token/` | POST | `username`, `password`, métadonnées appareil minimales | access token court, refresh token, utilisateur et capacités |
| `token/refresh/` | POST | refresh token | nouvel access et refresh rotatif |
| `token/revoke/` | POST | refresh token | révocation serveur, 204 |
| `session/` | GET | Bearer access | utilisateur courant et capacités |
| `devices/` | POST/DELETE | jeton FCM, plateforme, identifiant d'installation | enregistrement/révocation du terminal |

Paramètres recommandés : access 5 à 15 minutes, refresh rotatif, blacklist après rotation et déconnexion, limitation de débit sur login/refresh. Les secrets ne doivent jamais apparaître dans les logs.

Android stockera le refresh token dans un stockage chiffré adossé à Android Keystore. DataStore restera réservé aux préférences non sensibles. Un `Authenticator` OkHttp sérialisera les refresh concurrents ; un second 401 déclenchera l'état « session expirée ».

## 4. Inventaire des endpoints existants

Base actuelle : `/api`. Sauf mention contraire, les endpoints DRF exigent un utilisateur authentifié par session ou Basic Auth.

Convention des ViewSets `ModelViewSet` :

- collection : `GET` liste, `POST` création ;
- détail `/{id}/` : `GET`, `PUT`, `PATCH`, `DELETE` ;
- succès usuels : 200, 201, 204 ;
- validation DRF : 400 par dictionnaire de champs ;
- non authentifié : 401 ou 403 selon l'authenticator utilisé ;
- absence : 404 avec `detail`.

### 4.1 Core et comptes

| Route | Méthode | Permission | Entrée / paramètres | Réponse principale |
|---|---|---|---|---|
| `/health/` | GET | publique | aucune | `{status, application}` |
| `/login-page-visuals/` | GET | publique | aucune | URLs/images de la page de connexion |
| `/login-page-visuals/` | PATCH multipart/JSON | admin contrôlé dans la vue | images `meal_image`, `performance_image`, `follow_image` | visuels mis à jour |
| `/auth/login/` | POST JSON | publique, CSRF exempt | `username`, `password` | `{user:{id,username,email,is_authenticated,is_staff,is_superuser}}` |
| `/auth/register/` | POST JSON | publique, CSRF exempt | `username`, `email`, `password`, `password_confirm` | même utilisateur, 201, profil créé et session ouverte |
| `/auth/logout/` | POST | publique, CSRF exempt | aucune | `{success:true}` |
| `/auth/me/` | GET | session requise manuellement | aucune | `{user:...}` |
| `/auth/profile/me/` | GET | session requise manuellement | aucune | `{id,username,email}` |
| `/auth/admin/users/` | GET | staff | aucune | `{results:[users]}` |
| `/auth/admin/users/` | POST | staff | `username`, `email?`, `password`, `is_staff?`, `is_superuser?`, `is_active?` | utilisateur créé |
| `/auth/profiles/search/` | GET | authentifié | `q` | jusqu'à 20 profils avec email et nom |
| `/auth/ingredients/` | GET | authentifié | aucune | catalogue compact `{id,name,category,icon,default_unit,kcal_per_100g}` |
| `/auth/ingredients/` | POST | staff | `name`, `default_unit?`, `kcal_per_100g?` | ingrédient compact créé |

### 4.2 Profil, métriques et dashboard

| Route | Méthode | Permission | Entrée / paramètres | Réponse principale |
|---|---|---|---|---|
| `/profiles/` + `/{id}/` | CRUD standard | propriétaire via queryset | modèle profil | profil |
| `/profiles/me/` | GET/PATCH | authentifié | champs profil ; PATCH accepte aussi `objectif_date_debut`, `objectif_note` | profil courant |
| `/profiles/metrics/` | GET | authentifié | aucune | BMR, TDEE, calories, protéines, glucides, lipides, niveau calculé, champs manquants |
| `/profiles/dashboard/` | GET | authentifié | aucune | date, profil, métriques, repas, sport, progression, courses, suggestions |
| `/profiles/objective-history/` | GET | authentifié | aucune | historique des objectifs |
| `/profiles/objective-history/` | POST | authentifié | `objectif`, `date_debut`, `note?` | entrée créée et objectif courant mis à jour |

Champs profil : `date_naissance`, `sexe`, `taille_cm`, `poids_kg`, `activites_par_semaine`, `duree_moyenne_minutes`, `niveau_activite`, `objectif`, `fasting_mode`, `residence_city`, `is_listed_as_coach`, `coach_bio`, `coach_specialites`, `coach_availability`.

### 4.3 Foyer et repas partagés

| Route | Méthode | Permission | Entrée / paramètres | Réponse principale |
|---|---|---|---|---|
| `/auth/household-members/` | GET/POST | propriétaire | `name`, `relationship?`, `age?`, `sex?`, `linked_profile?` | membres du foyer |
| `/auth/household-members/{id}/` | GET/PUT/PATCH/DELETE | propriétaire | mêmes champs | membre |
| `/auth/meals/` | GET/POST | créateur ou participant visible en lecture | repas imbriqué | liste/repas créé |
| `/auth/meals/{id}/` | GET/PUT/PATCH/DELETE | actuellement créateur **ou participant** | repas imbriqué | repas mis à jour/supprimé |

Payload d'écriture d'un repas partagé :

```json
{
  "title": "Dîner familial",
  "eaten_at": "2026-08-30T19:00:00+03:00",
  "source_type": "home_cooked",
  "total_servings": 4,
  "notes": "",
  "shopping_done_by": 12,
  "cooked_by": 12,
  "ingredients": [{"ingredient": 4, "quantity": 500, "unit": "g"}],
  "participants": [{"profile": 12, "household_member": null, "servings_eaten": 1}]
}
```

Limites : `shopping_done_by` et `cooked_by` n'acceptent actuellement que l'utilisateur courant ; le total nutritionnel global n'est pas exposé ; tout participant lié peut actuellement modifier ou supprimer le repas.

### 4.4 Nutrition et recettes

| Route | Méthodes | Permission / filtres | Modèle de réponse |
|---|---|---|---|
| `/nutrition/cities/` + `/{id}/` | CRUD | lecture authentifiée, écriture staff | ville |
| `/nutrition/vendors/` + `/{id}/` | CRUD | lecture authentifiée, écriture staff ; filtre `city` | vendeur et ville |
| `/nutrition/ingredients/` + `/{id}/` | CRUD multipart/JSON | lecture authentifiée, écriture staff | nutrition/100 g, tags, image, préparation |
| `/nutrition/ingredients/export-excel/` | GET | authentifié | XLSX si `openpyxl`, sinon CSV |
| `/nutrition/ingredient-prices/` + `/{id}/` | CRUD | lecture authentifiée, écriture staff ; filtres `ingredient`, `vendor`, `city` | prix et unité tarifaire |
| `/nutrition/wellbeing-articles/` + `/{id}/` | CRUD | lecture authentifiée, écriture staff | article et `vendor_ids` |
| `/nutrition/wellbeing-article-prices/` + `/{id}/` | CRUD | lecture authentifiée, écriture staff ; filtres `article`, `vendor`, `city` | prix article |
| `/nutrition/recipes/` + `/{id}/` | CRUD multipart/JSON | authentifié ; non-staff : lecture publique + ses recettes, écriture seulement de ses recettes personnelles | recette, ingrédients, image, préparation, macros calculées |

Une création recette accepte `recipe_ingredients` ou `recipe_ingredients_json`, ainsi qu'une image multipart. Les macros sont calculées par Django à partir des ingrédients.

### 4.5 Plans de repas

| Route | Méthode | Permission | Entrée / paramètres | Réponse principale |
|---|---|---|---|---|
| `/meal-plans/` | GET/POST | propriétaire | GET `date_from?`, `date_to?`; POST `date`, `repas`, `recipe`, `nombre_portions`, `statut` | repas planifiés |
| `/meal-plans/{id}/` | GET/PUT/PATCH/DELETE | propriétaire | champs repas | repas |
| `/meal-plans/generate/` | POST | propriétaire | `date_debut`, `date_fin`, `replace_existing=true` | période, nombre, calories totales, IDs créés |

La génération tient déjà compte de `fasting_mode`. Elle échoue si les métriques du profil sont incomplètes.

### 4.6 Courses et préférences

| Route | Méthode | Permission | Entrée / paramètres | Réponse principale |
|---|---|---|---|---|
| `/shopping/lists/` + `/{id}/` | CRUD | propriétaire | dates | liste avec articles |
| `/shopping/lists/generate/` | POST | propriétaire | `date_debut`, `date_fin`, `replace_existing=true` | liste consolidée |
| `/shopping/lists/{id}/manual-items/` | POST | propriétaire | `wellbeing_article`, `quantite_totale?`, `unite?` | liste mise à jour |
| `/shopping/lists/{id}/export-csv/` | GET | propriétaire | aucune | CSV |
| `/shopping/items/{id}/check/` | PATCH | propriétaire | `checked` | état et date d'achat |
| `/shopping/items/{id}/purchase-date/` | PATCH | propriétaire | `purchase_date` ISO ou null | bornes et date |
| `/shopping/items/{id}/price/` | PATCH | propriétaire | `prix`, `pricing_unit` | prix, vendeur, date |
| `/profiles/shopping-preferences/meta/` | GET | authentifié | aucune | villes et vendeurs |
| `/profiles/shopping-preferences/` | GET/POST | propriétaire | `ingredient`, `preferred_vendor?`, `is_disliked?`, `is_unavailable?`, `note?` | préférence |
| `/profiles/shopping-preferences/item/{id}/` | DELETE | propriétaire | aucune | 204 |
| `/profiles/wellbeing-articles/meta/` | GET | authentifié | aucune | articles et derniers prix |
| `/profiles/wellbeing-articles/preferences/` | GET/POST | propriétaire | `article`, `preferred_vendor?`, `is_unavailable?`, `note?` | préférence |
| `/profiles/wellbeing-articles/preferences/item/{id}/` | DELETE | propriétaire | aucune | 204 |

### 4.7 Sport et séances

| Route | Méthode | Permission | Entrée / paramètres | Réponse principale |
|---|---|---|---|---|
| `/fitness/exercises/` + `/{id}/` | CRUD | lecture authentifiée, écriture staff | exercice/image/préparation | exercice |
| `/fitness/workout-plans/` + `/{id}/` | CRUD | propriétaire | programme et items imbriqués | programme |
| `/fitness/workout-plans/generate/` | POST | propriétaire ; `user_id` staff seulement | `date_debut`, `frequence_semaine` 2..5, `duree_semaines` 1..12, `replace_active`, `user_id?` | programme généré |
| `/fitness/workout-plans/today/` | GET | propriétaire | aucune | date candidate, semaine, plan, items |
| `/fitness/workout-plans/cycle/` | GET | propriétaire | aucune | semaines et items |
| `/fitness/workout-plans/complete-item/` | POST | propriétaire | `workout_plan_item_id`, `date`, `day_session_id?`, séries, répétitions, poids, repos, durée, commentaire | session exercice créée |
| `/fitness/workout-plans/today-session/` | GET | propriétaire | aucune | session quotidienne persistée |
| `/fitness/workout-plans/start-session/` | POST | propriétaire | aucune | session démarrée ou session active existante |
| `/fitness/workout-plans/end-session/` | POST | propriétaire | aucune | session terminée |
| `/fitness/workout-plans/postpone-item/` | POST | propriétaire | `workout_plan_item_id`, `new_date` | item reporté |
| `/fitness/workout-plans/admin-adherence/` | GET | staff | `user_id` | plan, adhérence, analyse |
| `/fitness/workout-plans/{plan}/items/` | POST | propriétaire | item complet | item créé |
| `/fitness/workout-plans/{plan}/items/{item}/` | PATCH/DELETE | propriétaire | champs autorisés | item/204 |
| `/fitness/workout-plans/{plan}/reorder-items/` | POST | propriétaire | `ordered_item_ids` | items réordonnés |
| `/fitness/workout-sessions/` + `/{id}/` | CRUD | propriétaire via queryset | réalisation exercice | historique/session |

Le chrono global serveur est déjà fondé sur `started_at` et non sur un compteur en mémoire. En revanche, les séries cochées et le compte à rebours de repos sont gérés localement dans Nuxt et ne sont pas persistés.

### 4.8 Progression corporelle

| Route | Méthodes | Permission | Entrée / réponse |
|---|---|---|---|
| `/progress/body-measurements/` + `/{id}/` | CRUD | propriétaire | `date`, `poids?`, `masse_musculaire_kg?`, `masse_graisseuse_kg?` |
| `/progress/photos/` + `/{id}/` | CRUD multipart | propriétaire pour l'API | `date`, `note?`, `image`; réponse avec `image_url` |

### 4.9 Coaching

| Route | Méthode | Permission / relation | Entrée / réponse |
|---|---|---|---|
| `/profiles/coach-directory/` | GET | authentifié | annuaire |
| `/profiles/coach-relationships/` | GET | authentifié | demandes, offres, coachs, coachés |
| même route | POST | authentifié | soit `coach_user_id`, soit `coache_user_id` |
| `/profiles/coach-relationships/{id}/accept/` | POST | actuellement uniquement `relationship.coach == user` | relation acceptée |
| `/profiles/coach-relationships/{id}/refuse/` | POST | actuellement uniquement coach | relation refusée |
| `/profiles/coach-relationships/{id}/remove/` | POST | l'une des parties | `{success:true}` |
| `/profiles/coach-dashboard/` | GET | coach avec relations acceptées | résumés des coachés |
| `/profiles/coach-coachee-detail/` | GET | coach autorisé | `coache_id`, `period_days` (7/30/90) ; mesures, adhérences, alertes, notes, messages, interventions |
| `/profiles/coach-notes/` | GET/POST | coach autorisé | `coache_id`, `note` |
| `/profiles/coach-messages/` | GET/POST | relation acceptée ou coaché destinataire | filtres `coache_id`, `coach_id`; POST type/titre/contenu/visibilité |
| même route | GET avec effet de bord | coaché | `mark_read_id` marque comme lu |
| `/profiles/coach-interventions/` | GET | coach autorisé ou coaché concerné | `coache_id` ou `coach_id` |
| `/profiles/copy-shared-plan/` | POST | relation acceptée | `source_user_id`, `copy_meals`, `copy_workouts` |
| `/profiles/coach-meal-plans/` | GET/POST/PATCH/DELETE | coach autorisé | `coache_id`, dates, payload repas, `meal_id` |
| `/profiles/coach-workout-items/` | POST/PATCH/DELETE | coach autorisé | `coache_id`, item ou `item_id` |
| `/profiles/coach-workout-reorder/` | POST | coach autorisé | `coache_id`, `ordered_item_ids` |
| `/profiles/coach-workout-presence/` | POST | coach autorisé | `coache_id`, `workout_plan_item_id`, `coach_present`, `details?` |
| `/profiles/coachee-space/` | GET | coaché | `period_days` ; coachs, messages, non-lus, interventions |

## 5. Parcours Nuxt observés

| Page Web | Parcours actuel | APIs principales |
|---|---|---|
| `/login` | connexion, inscription, visuels | auth, login visuals |
| `/dashboard` | objectifs/macros, repas, sport, courses, progression, conseil | profile dashboard |
| `/meal-plans` | génération, semaine, détail recette, portions/statut, suppression, manuel, recette personnelle, repas collectif | meal plans, recipes, shared meals |
| `/fitness` | génération, jour, cycle, analyse et historique | workout plans, exercises, sessions, profile dashboard |
| `/fitness/today` | chrono, séries cochées localement, repos, validation | today/start/end/complete-item |
| `/shopping` | génération, vendeur, coche, dates, prix, article manuel | shopping et préférences |
| `/profile` | profil, objectifs, métriques, mesures, photos, préférences, coaching | profiles, progress, nutrition, coaching |
| `/coach` | sélection coaché, 7/30/90 jours, alertes, notes, messages, repas et sport du coaché | coach endpoints |
| `/coachee` | messages, non-lus, interventions | coachee-space, coach-messages |
| `/admin-tools/*` | catalogues, prix, recettes, exercices, utilisateurs, visuels | endpoints staff |

Constat important : `useFitnessData.ts` contient une quantité significative de règles d'analyse et de recommandation côté Nuxt. Elles ne doivent pas être recopiées dans Android. Les analyses utiles doivent devenir des sorties Django stables.

## 6. Écarts et risques identifiés

### P0 — bloquants sécurité/intégrité

1. **Photos corporelles publiques** : Nginx sert directement `/media/`; connaître l'URL suffit pour télécharger une photo sans authentification.
2. **Repas partagé modifiable par un participant** : le queryset du détail autorise tout participant à utiliser PATCH/PUT/DELETE.
3. **Acceptation coaching incorrecte** : une offre initiée par un coach devrait être acceptée par le coaché, mais l'action ne cherche que les relations où l'utilisateur courant est coach.
4. **Basic Auth global** : il permet l'envoi répétitif du mot de passe ; à désactiver en production après ajout du JWT.
5. **Exposition d'email** : recherche de profils et annuaire coach renvoient l'email à tout utilisateur authentifié sans nécessité métier.
6. **Références insuffisamment scellées** : une session sportive créée via le CRUD standard peut référencer un programme qui n'appartient pas à l'utilisateur ; un repas peut référencer par ID une recette personnelle non visible.
7. **Upload sans politique explicite** : pas de limite de taille/dimensions/type ni de suppression des métadonnées EXIF pour les photos sensibles.
8. **Configuration fail-open** : `SECRET_KEY=change-me-in-production` et `DEBUG=True` par défaut ; la production doit échouer si les secrets indispensables sont absents.

### P1 — contrat mobile et cohérence métier

1. aucun OpenAPI, versioning, pagination ou enveloppe d'erreur stable ;
2. aucun access/refresh token, blacklist, limitation de débit ou révocation d'appareil ;
3. pas d'endpoint de capacités/rôles ;
4. `mark_read_id` modifie un message via GET ; il faut une action PATCH/POST idempotente ;
5. pas de modèle de série sportive ni d'état de repos persistant ;
6. pas de `updated_at`, version ou identifiant de mutation sur les articles de courses pour synchroniser proprement hors connexion ;
7. pas de modèle de terminal FCM ni de service de notification ;
8. les analyses utilisateur dans Nuxt dupliquent une logique qui devrait être fournie par Django ;
9. le dashboard additionne les macros des recettes sans multiplier par `nombre_portions`, contrairement au service de génération ;
10. le “conseil du jour” est une phrase fixe, pas une recommandation calculée ;
11. certains usages emploient `date.today()` au lieu de `timezone.localdate()` ; risque de décalage autour de minuit ;
12. le total nutritionnel global d'un repas partagé et les totaux de panier/vendeur ne sont pas contractualisés par le serveur ;
13. la personne ayant cuisiné/fait les courses est limitée au compte courant ;
14. l'annuaire coach contient tous les utilisateurs actifs au lieu de filtrer clairement les profils visibles comme coachs ;
15. aucune hydratation n'existe : la carte Android doit être absente, jamais simulée.

### P2 — qualité et exploitation

1. seulement deux tests backend ; aucun test nutrition, sport, courses, photos ou coaching ;
2. pas de tests frontend de référence ;
3. pas d'idempotency key sur les créations générées/mutations critiques ;
4. pas de politique documentée de rétention/suppression des photos corporelles et jetons FCM ;
5. métadonnées Git incomplètes localement, empêchant les commits demandés.

## 7. Adaptations Django proposées

### Lot A — contrat et authentification

- installer `djangorestframework-simplejwt` avec rotation et blacklist ;
- installer `drf-spectacular`, publier `/api/v1/schema/` et une documentation en environnement non public ou protégée ;
- conserver les routes session Web actuelles ;
- créer `/api/v1/mobile/auth/*` ;
- ajouter `GET /api/v1/me/capabilities/` ;
- normaliser erreurs et codes 401/403 ;
- ajouter throttling login/refresh et audit sans données sensibles ;
- désactiver Basic Auth en production ;
- ajouter une stratégie de versioning sans casser `/api/`.

### Lot B — sécurité des données

- déplacer les photos de progression vers un stockage privé ;
- servir par vue authentifiée avec contrôle propriétaire, URL signée courte ou `X-Accel-Redirect` interne ;
- valider type MIME, signature de fichier, taille, dimensions ; réencoder l'image et supprimer EXIF ;
- réserver écriture/suppression des repas partagés au créateur, lecture aux participants ;
- minimiser les DTO publics coach/profil et retirer l'email ;
- verrouiller toutes les relations d'objet dans les serializers par utilisateur/coach autorisé ;
- corriger le destinataire habilité à accepter/refuser une relation.

### Lot C — capacités fonctionnelles mobiles

- ajouter `WorkoutSetProgress` ou équivalent, endpoints idempotents de validation/dévalidation de série ;
- persister `rest_started_at`, `rest_duration_seconds` et permettre la reprise ;
- ajouter `updated_at`/`version` sur `ShoppingListItem` et un endpoint de batch sync idempotent ;
- ajouter `DevicePushToken` avec révocation et préférences de confidentialité ;
- envoyer des notifications coach sans contenu sensible par défaut ;
- déplacer les analyses Nuxt nécessaires vers des services/endpoints Django ;
- exposer totaux nutritionnels partagés et totaux de courses par vendeur ;
- corriger les agrégats du dashboard pour les portions ;
- remplacer la suggestion fixe par une recommandation justifiée ou `null` ;
- utiliser `timezone.localdate()` ;
- ajouter pagination/filtrage aux catalogues et historiques.

Migrations prévues : blacklist SimpleJWT, `DevicePushToken`, progression par série/repos, champs de version des courses, et éventuellement métadonnées privées des photos. Elles seront définies précisément dans le contrat Phase 1 avant création.

## 8. Architecture Android proposée

Projet Gradle Kotlin DSL multi-module, unidirectional data flow et MVVM/Clean pragmatique :

```text
android/
  app/
  core/common/
  core/model/
  core/network/
  core/database/
  core/datastore/
  core/security/
  core/designsystem/
  core/navigation/
  core/testing/
  feature/auth/
  feature/dashboard/
  feature/profile/
  feature/progress/
  feature/meals/
  feature/sharedmeals/
  feature/fitness/
  feature/shopping/
  feature/coaching/
```

Principes :

- DTO Kotlin Serialization distincts des modèles de domaine et entités Room ;
- repositories comme source unique pour les ViewModels ;
- Flow/StateFlow et états explicites `Loading`, `Success`, `Empty`, `Unauthorized`, `ValidationError`, `NetworkError`, `ServerError` ;
- Hilt, Retrofit/OkHttp, Room, WorkManager, Coil, Navigation Compose et Material 3 ;
- base URL par `debug`, `staging`, `release` via `BuildConfig`, aucun secret dans le dépôt ;
- refresh token chiffré par Android Keystore ;
- outbox Room pour les coches de courses, WorkManager contraint au réseau ;
- séance active reconstruite depuis les timestamps serveur et locaux persistés ;
- notifications locales pour le repos ; FCM uniquement après disponibilité backend ;
- logs HTTP désactivés en release et rédactés en debug ; aucun body d'auth, photo, mesure, note ou message.

Navigation : cinq destinations principales Accueil, Repas, Sport, Courses, Profil. Coach et Coaché seront des destinations conditionnelles exposées par les capacités serveur, sans surcharger la barre inférieure sur petit écran (accès depuis Profil ou une destination secondaire si nécessaire).

## 9. Plan d'implémentation avec portes de validation

### Phase 1 — Fondations

1. tests de caractérisation du backend actuel ;
2. OpenAPI versionné et exemples d'erreur ;
3. JWT mobile coexistante avec sessions Web, blacklist et capacités ;
4. correctifs P0 de permissions et photos privées ;
5. squelette Android multi-module, variantes d'environnement, CI locale ;
6. design system sombre/clair, navigation et écrans d'auth ;
7. réseau, stockage chiffré, Room/DataStore, gestion 401/403 ;
8. tests token/refresh/logout et compilation `assembleDebug`.

Porte de sortie : schéma OpenAPI validé, Web non régressé, authentification Android testée, aucun secret, build Android vert.

### Phase 2 — MVP utilisateur

- dashboard ;
- profil/métriques/objectifs ;
- repas/recettes personnelles ;
- courses en ligne ;
- programme et séance persistante ;
- mesures corporelles sans photos dans un premier incrément ;
- tests ViewModel/repository/Compose des parcours critiques.

### Phase 3 — avancé et hors connexion

- photos privées avec Photo Picker et caméra ;
- foyer/repas partagés ;
- préférences d'approvisionnement ;
- Room/outbox et synchronisation différée des courses ;
- notifications locales de récupération ;
- accessibilité, textes agrandis et optimisation images.

### Phase 4 — coaching

- relations corrigées ;
- espace coach et coaché ;
- messages, lecture, interventions, gestion repas/sport ;
- FCM avec notifications discrètes ;
- tests de permissions exhaustifs.

### Phase 5 — stabilisation et publication

- sécurité, performance, accessibilité, tests instrumentés ;
- sauvegarde/migrations, observabilité sans PII ;
- documentation environnements et exploitation ;
- signature, Play Integrity si justifié, Data Safety, politique de confidentialité, checklist Play Store.

## 10. Matrice Web → Android

| Fonction Web | Écran Android cible | Endpoint actuel | État backend | Phase Android | Tests requis / écart |
|---|---|---|---|---|---|
| Connexion/inscription | Auth | `/auth/*` | session seulement | 1 | JWT/refresh/session expirée |
| Navigation conditionnelle | App shell | coach relationships | disponible indirectement | 1 | ajouter capacités explicites |
| Dashboard | Accueil | `/profiles/dashboard/` | partiel | 2 | portions, suggestion, états vides |
| Profil | Profil > Informations | `/profiles/me/` | disponible | 2 | validation DTO/ViewModel |
| Métriques | Profil > Objectifs | `/profiles/metrics/` | disponible serveur | 2 | conversion et champs manquants |
| Historique objectifs | Profil > Objectifs | `/profiles/objective-history/` | disponible | 2 | création/liste |
| Mesures | Profil > Progression | `/progress/body-measurements/` | disponible | 2 | CRUD, graphique, confidentialité |
| Photos | Profil > Photos | `/progress/photos/` | API oui, stockage non privé | 3 | upload, permissions, reprise, sécurité |
| Plan repas | Repas | `/meal-plans/*` | disponible | 2 | génération, statut, portions, suppression |
| Recette personnelle | Repas > Recette | `/nutrition/recipes/` | disponible | 2/3 | multipart et ownership |
| Foyer | Repas > Foyer | `/auth/household-members/*` | disponible | 3 | CRUD et lien profil |
| Repas partagé | Repas > Collectif | `/auth/meals/*` | partiel | 3 | corriger ownership, totaux, personnes |
| Programme sportif | Sport > Programme | `/fitness/workout-plans/*` | disponible | 2 | génération/CRUD/report/réordre |
| Séance du jour | Sport > Séance | actions workout plan | partiel | 2 | ajouter séries/repos persistants et reprise |
| Historique sport | Sport > Historique | `/fitness/workout-sessions/` | disponible | 2 | filtres/pagination |
| Courses | Courses | `/shopping/*` | en ligne | 2 | génération/coche/prix/totaux |
| Courses hors ligne | Courses | aucun batch sync/version | manquant | 3 | Room outbox, conflits, WorkManager |
| Préférences vendeur | Profil > Approvisionnement | preferences endpoints | disponible | 3 | validation ville/vendeur |
| Annuaire coach | Profil > Coaching | coach directory | partiel | 4 | filtrage coach, retrait email |
| Relations coaching | Profil > Coaching | coach relationships | bug acceptation | 4 | matrice de permissions |
| Espace coach | Coach | coach dashboard/detail/actions | très avancé | 4 | 7/30/90, notes, mutations |
| Espace coaché | Coaché | coachee-space/messages | disponible | 4 | lecture via mutation dédiée |
| Notifications coach | système Android | aucun FCM | manquant | 4 | token, révocation, contenu discret |
| Hydratation | aucune | aucun modèle/endpoint | absent | hors périmètre | ne pas afficher de donnée fictive |
| Administration | future | endpoints staff | disponible Web | après V1 | architecture extensible seulement |

## 11. Blocages avant démarrage de la Phase 1

1. restaurer ou réinitialiser proprement les métadonnées Git si des commits sont exigés ;
2. valider le nom de package Android proposé, par exemple `mg.hydria.bienetre` ;
3. confirmer les environnements/API de staging et production ;
4. décider du stockage privé des photos : Nginx interne local ou stockage objet avec URLs signées ;
5. fournir un projet Firebase séparé pour Bien-être avant la Phase 4, jamais les secrets dans Git ;
6. définir la politique de rétention/suppression des photos, messages, tokens appareil et compte utilisateur ;
7. confirmer les versions Android minimales. Proposition : `minSdk 26`, `targetSdk` correspondant au SDK stable exigé au moment de publication.

Ces décisions n'empêchent pas de commencer les tests de caractérisation, OpenAPI, JWT et le squelette Android, sauf le nom de package qui doit être figé avant la création du projet.

## 12. Décision de démarrage recommandée

Commencer la Phase 1 par le backend et ses tests, dans cet ordre :

1. tests de permissions/ownership et correction des P0 ;
2. OpenAPI `/api/v1` ;
3. JWT mobile + capacités ;
4. contrat Android généralisé et figé ;
5. seulement ensuite création du projet Android et implémentation de l'authentification.

Cette séquence préserve l'application Web, évite de coder des DTO Android sur des réponses instables et empêche de bâtir le mobile sur des URLs de photos non privées.
