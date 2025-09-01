# Guide de déploiement de Soakoja sur Render

Ce guide explique comment déployer l'application Soakoja sur la plateforme Render en utilisant GitHub comme source de code.

## Prérequis

1. Un compte GitHub avec le dépôt du projet Soakoja
2. Un compte Render (inscription gratuite sur [render.com](https://render.com))
3. Un projet Supabase configuré (pour la base de données)

## Étape 1 : Préparation du projet

Votre projet est déjà configuré avec le fichier `render.yaml` qui définit la configuration de déploiement. Assurez-vous que les fichiers suivants sont présents dans votre dépôt GitHub :

- `package.json` avec les scripts de démarrage
- `render.yaml` pour la configuration de Render
- `.env.example` comme modèle pour les variables d'environnement

## Étape 2 : Connecter GitHub à Render

1. Connectez-vous à votre compte Render
2. Cliquez sur "New" puis "Blueprint" dans le tableau de bord
3. Connectez votre compte GitHub si ce n'est pas déjà fait
4. Sélectionnez le dépôt `h3rizo/Hydriav2`
5. Render détectera automatiquement le fichier `render.yaml` et configurera le service

## Étape 3 : Configuration des variables d'environnement

Après avoir connecté votre dépôt, vous devrez configurer les variables d'environnement suivantes :

1. `SUPABASE_URL` : L'URL de votre projet Supabase
2. `SUPABASE_SERVICE_KEY` : La clé de service de votre projet Supabase

Pour obtenir ces informations :

1. Connectez-vous à votre compte Supabase
2. Sélectionnez votre projet
3. Allez dans "Settings" > "API"
4. Copiez l'URL du projet et la clé "service_role" (pas la clé anon/public)

## Étape 4 : Déploiement

1. Cliquez sur "Apply Blueprint" dans Render
2. Render va créer le service web et commencer le déploiement
3. Le déploiement initial peut prendre quelques minutes
4. Une fois terminé, vous recevrez une URL pour accéder à votre application (par exemple, `https://soakoja-app.onrender.com`)

## Étape 5 : Vérification du déploiement

1. Visitez l'URL fournie par Render
2. Connectez-vous avec les identifiants par défaut (admin/admin123)
3. Vérifiez que toutes les fonctionnalités fonctionnent correctement

## Mise à jour de l'application

Lorsque vous apportez des modifications à votre code et que vous les poussez sur GitHub :

1. Commit et push vos changements vers GitHub :
   ```bash
   git add .
   git commit -m "Description des modifications"
   git push origin main
   ```

2. Render détectera automatiquement les changements et déploiera la nouvelle version (si `autoDeploy` est activé dans le fichier render.yaml)

## Dépannage

### L'application ne démarre pas

1. Vérifiez les logs dans le tableau de bord Render
2. Assurez-vous que toutes les variables d'environnement sont correctement configurées
3. Vérifiez que le script de démarrage dans `package.json` est correct

### Problèmes de connexion à Supabase

1. Vérifiez que les variables `SUPABASE_URL` et `SUPABASE_SERVICE_KEY` sont correctes
2. Assurez-vous que votre projet Supabase est actif
3. Vérifiez les restrictions d'accès dans les paramètres de Supabase

## Ressources supplémentaires

- [Documentation Render](https://render.com/docs)
- [Documentation Supabase](https://supabase.io/docs)
- [Documentation GitHub](https://docs.github.com/fr)