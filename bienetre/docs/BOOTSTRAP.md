# Bootstrap Bien-etre

## Cible

Lancer un nouveau produit `bienetre.hydria.mg` sur le meme VPS que Hydria, mais avec une architecture isolee.

## Structure cible VPS

```text
/home/soakoja/bienetre/
  backend/
  frontend/
  .env.backend
  .env.frontend
  backups/
```

## Services cibles

- `bienetre-gunicorn.service`
- `bienetre-nuxt.service`

## Ports internes recommandes

- Django API : `127.0.0.1:8100`
- Nuxt SSR : `127.0.0.1:3100`

## Base PostgreSQL

- database : `bienetre`
- user : `bienetre_user`

## Sequence de bootstrap recommandee

1. Creer la base et l'utilisateur PostgreSQL.
2. Initialiser le backend Django.
3. Initialiser le frontend Nuxt.
4. Configurer les variables d'environnement.
5. Configurer Nginx pour `bienetre.hydria.mg`.
6. Configurer SSL.
7. Configurer sauvegardes et supervision.

## Priorite fonctionnelle

1. Authentification
2. Profil bien-etre
3. Ingredients
4. Recettes
5. Planification repas
6. Courses
7. Exercices
8. Programmes sportifs
9. Progression

