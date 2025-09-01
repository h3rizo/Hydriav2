# Application Soakoja

Application web de gestion d'eau potable pour Soakoja Madagascar.

## Installation

1. **Installer Node.js** (version 16 ou supérieure)
   - Télécharger depuis https://nodejs.org/

2. **Cloner ou télécharger le projet**
   
3. **Installation des dépendances**
   ```bash
   npm install
   ```

4. **Démarrer l'application**
   ```bash
   npm start
   ```

5. **Ouvrir dans le navigateur**
   - http://localhost:3000

## Comptes de test

- **Administrateur**: admin / admin123 (niveau 4)
- **Caissière**: marie / marie123 (niveau 2) 
- **Agent terrain**: jean / jean123 (niveau 1)

## Structure

- `server.js` - Serveur principal
- `views/` - Templates EJS
- `public/` - Fichiers statiques (CSS, JS)
- `database/` - Base de données SQLite

## Fonctionnalités

- ✅ Authentification multi-niveaux
- ✅ Gestion des plannings d'activités
- ✅ Suivi des ouvrages d'eau
- ✅ Gestion des points d'eau
- ✅ Cartes sociales (tarifs préférentiels)
- ✅ Interface responsive
- 🔄 Intégration DiameX (en cours)

## Développement

Pour le mode développement avec rechargement automatique:
```bash
npm run dev
```

## Déploiement sur Render

L'application est configurée pour être déployée facilement sur Render:

1. **Préparation au déploiement**
   ```bash
   node prepare-render-deploy.js
   ```

2. **Connecter GitHub à Render**
   - Créez un compte sur [Render](https://render.com)
   - Connectez votre dépôt GitHub
   - Render détectera automatiquement le fichier `render.yaml`

3. **Configuration des variables d'environnement**
   - Configurez les variables Supabase dans Render

Pour des instructions détaillées, consultez le guide complet dans `documentation/render_deployment_guide.md`
