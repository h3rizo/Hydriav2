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
