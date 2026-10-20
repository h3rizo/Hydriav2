# Bien-etre Hydria

## Decision d'architecture

### Recommandation retenue

Construire **Bien-etre** comme une **application separee** de Hydria, avec :

- un **backend Django/DRF dedie**
- un **frontend Nuxt dedie**
- une **base PostgreSQL dediee**
- un **deploiement VPS dedie sous `bienetre.hydria.mg`**

Cette option est la moins risquee pour Hydria.

### Option retenue

**Option A - Projet independant complet**

Structure cible recommandee sur le serveur :

```text
/home/soakoja/
  hydria/
    backend/
    frontend/
  bienetre/
    backend/
    frontend/
    .env
    backups/
```

### Option non retenue

**Option B - Nouvelle app Django dans le backend Hydria existant**

Cette option est deconseillee parce que le backend Hydria actuel est deja un monolithe important avec :

- beaucoup d'apps metier
- routage multi-sous-domaines dans un meme projet
- middleware specifiques Hydria
- configuration unique `settings.py`
- dette technique et risque de regression plus eleves

Ajouter Bien-etre dans ce backend couplerait inutilement :

- les deploiements
- les migrations
- les variables d'environnement
- les risques de panne
- les politiques de securite

## Analyse de l'existant Hydria

### Backend actuel

Hydria est aujourd'hui un **projet Django monolithique modulaire** :

- framework : Django 5.1/5.2 + Django REST Framework
- base : PostgreSQL via `DATABASE_URL`
- nombreuses apps metier dans `backend/apps/`
- sous-domaines deja geres dans `backend/hydria/settings.py`
- middleware personnalises et routage oriente Hydria
- deployment actuel via Gunicorn + Nginx sur VPS

Points constates :

- le projet principal concentre deja la logique eau, comptabilite, paie, planning, logistique, recrutement, social, etc.
- `INSTALLED_APPS` est deja charge
- la configuration est centralisee
- les sous-domaines existants restent rattaches au meme backend

Conclusion :

Le backend Hydria est un bon produit operationnel, mais **ce n'est pas un bon point d'ancrage pour une nouvelle plateforme de bien-etre autonome**.

### Frontend actuel

Le depot contient aussi un frontend Nuxt distinct :

- Nuxt 3
- Tailwind CSS
- DaisyUI
- Pinia
- Chart.js
- PWA deja exploree

Conclusion :

Le choix technologique cible demande dans le besoin est **coherent avec l'existant frontend**. Il faut cependant un **frontend Nuxt dedie Bien-etre**, sans partager l'application Nuxt Hydria existante.

## Pourquoi un projet independant est le bon choix

### Avantages

- deploiement independant
- migrations independantes
- incidents isoles
- performances isolees
- securite mieux cloisonnee
- evolution fonctionnelle autonome
- possibilite de changer de roadmap sans impacter Hydria
- meilleure lisibilite produit

### Risques evites

- regression sur Hydria production
- conflits de dependances
- explosion de complexite dans les `settings`
- pollution des routes et permissions Hydria
- confusion entre donnees d'infrastructure eau et donnees personnelles de bien-etre

## Architecture cible

### Backend Bien-etre

Stack :

- Django
- Django REST Framework
- PostgreSQL
- Gunicorn
- Whitenoise si necessaire

Applications Django recommandees :

- `apps.accounts`
- `apps.profiles`
- `apps.nutrition`
- `apps.recipes`
- `apps.meal_plans`
- `apps.shopping`
- `apps.fitness`
- `apps.progress`
- `apps.core`

### Frontend Bien-etre

Stack :

- Nuxt 3
- Tailwind CSS
- DaisyUI
- Pinia
- Chart.js
- PWA optionnelle en phase 2

Pages cible :

- `/`
- `/profil`
- `/ingredients`
- `/recettes`
- `/recettes/[id]`
- `/calendrier`
- `/courses`
- `/exercices`
- `/entrainements`
- `/progression`

### Base de donnees

Base dediee recommande e.g. :

- nom : `bienetre`
- utilisateur DB dedie : `bienetre_user`

Il faut **eviter de reutiliser la base Hydria**.

### Separation reseau et runtime

Services systemd recommandes :

- `bienetre-gunicorn.service`
- `bienetre-nuxt.service`

Ports internes exemple :

- Django API : `127.0.0.1:8100`
- Nuxt SSR : `127.0.0.1:3100`

## Sous-domaine et exposition publique

### Domaine public

- `https://bienetre.hydria.mg`

### Nginx recommande

Schéma recommande :

- Nginx termine SSL
- Nginx reverse proxy vers Nuxt
- Nuxt appelle Django API via `/api/` ou domaine API interne

Exemple conceptuel :

```nginx
server {
    server_name bienetre.hydria.mg;

    listen 443 ssl http2;
    ssl_certificate /etc/letsencrypt/live/bienetre.hydria.mg/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bienetre.hydria.mg/privkey.pem;

    location /static/ {
        alias /home/soakoja/bienetre/backend/staticfiles/;
    }

    location /media/ {
        alias /home/soakoja/bienetre/backend/media/;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:3100;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### SSL

Utiliser Let's Encrypt avec certificat dedie :

- `bienetre.hydria.mg`

## Authentification

### Recommandation

Mettre en place une **authentification independante**, mais **federation-ready**.

### Choix pragmatique phase 1

- Django auth standard
- email + mot de passe
- modele utilisateur extensible ou profil separe

### Federation future

Prevoir compatibilite future avec :

- OIDC / OAuth2
- Google Sign-In
- eventuellement SSO commun Hydria

### Position recommandee

Ne pas essayer de partager des sessions entre Hydria et Bien-etre des la phase 1.

Motif :

- reduction du risque
- reduction du couplage
- meilleure securite

## Modeles metier a implementer

### Module 1 - Profil Bien-etre

`WellbeingProfile`

Champs :

- `user`
- `age`
- `sexe`
- `taille_cm`
- `poids_kg`
- `masse_graisseuse_pct`
- `masse_musculaire_pct`
- `niveau_activite`
- `objectif`
- `allergies`
- `intolerances`
- `preferences_alimentaires`
- `aliments_a_eviter`
- `date_creation`
- `date_modification`

### Module 2 - Base nutritionnelle

`Ingredient`

Champs :

- `nom`
- `categorie`
- `unite_base`
- `calories_100g`
- `proteines_100g`
- `glucides_100g`
- `lipides_100g`
- `fibres_100g`
- `sucre_100g`
- `sodium_100g`
- `calcium_100g`
- `fer_100g`

### Module 3 - Recettes

- `Recipe`
- `RecipeIngredient`

### Module 4 - Planification repas

- `MealPlan`

### Module 5 - Courses

- `ShoppingList`
- `ShoppingListItem`

### Module 6 - Objectifs nutritionnels

Objets ou services :

- calcul BMR
- calcul TDEE
- objectifs macro-nutritionnels

### Module 7 - Exercices

- `Exercise`

### Module 8 - Programmes sportifs

- `WorkoutPlan`
- `WorkoutPlanItem`
- `WorkoutSession`

### Module 9 - Progression

- `BodyMeasurement`

## API REST

Organisation recommandee :

- `/api/auth/`
- `/api/profile/`
- `/api/ingredients/`
- `/api/recipes/`
- `/api/meal-plans/`
- `/api/shopping-lists/`
- `/api/exercises/`
- `/api/workout-plans/`
- `/api/workout-sessions/`
- `/api/body-measurements/`
- `/api/dashboard/`

Regles :

- DRF ViewSets ou Generic Views
- permissions par utilisateur
- filtrage par proprietaire
- validation stricte

## Permissions

### Regles minimales

- chaque utilisateur voit uniquement ses donnees privees
- les ingredients, exercices et recettes de demo peuvent etre globaux en lecture
- les listes de courses, plans repas, sessions et mesures sont strictement personnelles

### Roles optionnels

- `admin`
- `staff_nutrition_content`
- `staff_fitness_content`
- `user`

## Position produit et securite

L'application doit etre presentee comme :

- outil de bien-etre
- suivi d'habitudes
- aide a l'organisation personnelle

L'application ne doit pas etre presentee comme :

- outil medical
- outil de diagnostic
- outil de prescription

Message obligatoire a afficher :

> Cette application fournit des informations generales de bien-etre et ne remplace pas un avis medical, nutritionnel ou sportif professionnel.

## Sauvegarde

### Sauvegardes minimales

- dump PostgreSQL quotidien
- retention locale
- copie distante si possible
- sauvegarde media
- sauvegarde `.env`

### Exemple de structure

```text
/home/soakoja/bienetre/backups/
  db/
  media/
  env/
```

### Procedure recommandee

- cron quotidien pour `pg_dump`
- archive media hebdomadaire
- rotation automatique

## Variables d'environnement

### Backend

Exemple :

```env
DEBUG=False
SECRET_KEY=...
ALLOWED_HOSTS=bienetre.hydria.mg,localhost,127.0.0.1
DATABASE_URL=postgres://bienetre_user:...@localhost:5432/bienetre
CSRF_TRUSTED_ORIGINS=https://bienetre.hydria.mg
CORS_ALLOWED_ORIGINS=https://bienetre.hydria.mg
DJANGO_SETTINGS_MODULE=bienetre.settings
```

### Frontend

Exemple :

```env
NUXT_PUBLIC_APP_NAME=Bien-etre Hydria
NUXT_PUBLIC_SITE_URL=https://bienetre.hydria.mg
NUXT_PUBLIC_API_BASE=https://bienetre.hydria.mg/api
```

## Procedure de deploiement

### Backend

1. Creer repertoire projet
2. Creer venv dedie
3. Installer dependances
4. Configurer `.env`
5. Executer migrations
6. Collecter les statiques
7. Demarrer `bienetre-gunicorn`

### Frontend

1. Installer dependances Node
2. Configurer `.env`
3. `npm run build`
4. demarrer `node .output/server/index.mjs` via `systemd`

### Infrastructure

1. configurer Nginx
2. ouvrir le DNS `bienetre.hydria.mg`
3. generer SSL
4. tester reverse proxy
5. tester endpoints `/` et `/api/health/`

## Plan de developpement recommande

### Phase 0 - Architecture et cadrage

Livrables :

- note d'architecture
- arborescence cible
- strategie auth
- strategie deploiement
- modele de donnees version 1

### Phase 1 - Socle technique

Livrables :

- nouveau projet Django Bien-etre
- nouveau projet Nuxt Bien-etre
- pipeline local dev
- auth de base
- layout UI
- page dashboard vide

### Phase 2 - Donnees coeur

Livrables :

- modeles `WellbeingProfile`, `Ingredient`, `Recipe`, `RecipeIngredient`
- migrations
- admin Django
- import nutritionnel massif
- seeds demo ingredients/recipes

### Phase 3 - Planification repas et courses

Livrables :

- `MealPlan`
- vues semaine/mois
- generation liste de courses
- checklist mobile

### Phase 4 - Exercice et progression

Livrables :

- `Exercise`
- `WorkoutPlan`
- `WorkoutPlanItem`
- `WorkoutSession`
- `BodyMeasurement`
- graphiques progression

### Phase 5 - Intelligence metier bien-etre

Livrables :

- calcul BMR/TDEE
- objectifs nutritionnels
- tableau de bord nutritionnel
- suggestions non medicales

### Phase 6 - Production

Livrables :

- Nginx
- SSL
- backup
- supervision
- documentation utilisateur
- guide de deploiement

## Ordre de priorite recommande

1. Architecture separee
2. Auth
3. Profil
4. Ingredients
5. Recettes
6. Meal planning
7. Shopping list
8. Exercices
9. Progression
10. Suggestions et raffinements UX

## Proposition de structure locale dans ce depot

Si on veut travailler dans le meme depot sans coupler les runtimes :

```text
/bienetre/
  /backend/
  /frontend/
  /docs/
```

Important :

- code separe
- requirements separes
- package.json separe
- `.env` separe
- migrations separees
- services systemd separes

Cette approche garde la collaboration pratique dans un seul workspace, tout en preservant l'independance applicative.

## Decision finale

La meilleure solution pour `bienetre.hydria.mg` est :

- **projet Bien-etre distinct**
- **backend Django/DRF dedie**
- **frontend Nuxt dedie**
- **base PostgreSQL dediee**
- **deploiement VPS dedie**
- **authentification independante, federation-ready**

Ce choix minimise les risques pour Hydria et maximise la capacite d'evolution future.

## Prochaine etape recommandee

Demarrer par :

1. creation de l'arborescence `bienetre/backend` et `bienetre/frontend`
2. generation du projet Django Bien-etre
3. generation du projet Nuxt Bien-etre
4. implementation des modules 1 a 3
5. seeds de demonstration

