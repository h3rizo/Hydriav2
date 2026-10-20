# Bien-etre Hydria

Projet separe de Hydria pour l'application `bienetre.hydria.mg`.

## Objectif

Construire une plateforme dediee au bien-etre personnel :

- nutrition
- recettes
- planification des repas
- listes de courses
- objectifs corporels
- exercices
- programmes sportifs
- suivi de progression

## Principe d'isolation

Ce projet doit rester separe de Hydria :

- backend separe
- frontend separe
- base PostgreSQL separee
- `.env` separe
- deploiement VPS separe

## Arborescence

```text
bienetre/
  README.md
  backend/
  frontend/
  docs/
```

## Documents de reference

- architecture initiale : [backend/docs/BIENETRE_HYDRIA_ARCHITECTURE.md](C:/Users/Dir%20Soakoja/Documents/Formation%20appli%20web/hydria%20nuxt%20django/backend/docs/BIENETRE_HYDRIA_ARCHITECTURE.md)
- plan de bootstrap : [docs/BOOTSTRAP.md](C:/Users/Dir%20Soakoja/Documents/Formation%20appli%20web/hydria%20nuxt%20django/bienetre/docs/BOOTSTRAP.md)
- environnement : [docs/ENVIRONMENT.md](C:/Users/Dir%20Soakoja/Documents/Formation%20appli%20web/hydria%20nuxt%20django/bienetre/docs/ENVIRONMENT.md)

## Etapes suivantes recommandees

1. Initialiser `bienetre/backend` avec un projet Django dedie.
2. Initialiser `bienetre/frontend` avec un projet Nuxt dedie.
3. Creer la base PostgreSQL `bienetre`.
4. Mettre en place le schema d'authentification.
5. Implementer les modules 1 a 3 en premier.

