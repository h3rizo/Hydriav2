# Variables d'environnement

## Backend Django

Exemple :

```env
DEBUG=False
SECRET_KEY=change-me
ALLOWED_HOSTS=bienetre.hydria.mg,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://bienetre.hydria.mg
CORS_ALLOWED_ORIGINS=https://bienetre.hydria.mg
DATABASE_URL=postgresql://bienetre_user:password@127.0.0.1:5432/bienetre
DJANGO_SETTINGS_MODULE=bienetre.settings
```

## Frontend Nuxt

Exemple :

```env
NUXT_PUBLIC_SITE_URL=https://bienetre.hydria.mg
NUXT_PUBLIC_API_BASE=https://bienetre.hydria.mg/api
NUXT_PUBLIC_APP_NAME=Bien-etre Hydria
NODE_ENV=production
```

## Regles

- ne jamais reutiliser le `.env` Hydria
- ne jamais reutiliser `DATABASE_URL` Hydria
- separer les secrets backend et frontend
- versionner uniquement des exemples, jamais les secrets reels

