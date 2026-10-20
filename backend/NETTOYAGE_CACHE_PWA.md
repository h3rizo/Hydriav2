# Guide de Nettoyage Complet du Cache PWA

## Problème
Les anciennes icônes PWA restent affichées même après déploiement des nouvelles icônes, car le navigateur a mis en cache l'ancien manifest.json et les anciennes images.

## Solution : Nettoyage Complet en 3 Étapes

### Étape 1 : Désinstaller l'Application PWA

**Sur Windows :**
1. Ouvrir le menu Démarrer
2. Rechercher "Hydria"
3. Clic droit > Désinstaller
4. OU : Ouvrir l'application > Icône ⋮ (trois points) > Désinstaller

**Sur Android :**
1. Ouvrir les Paramètres
2. Applications
3. Rechercher "Hydria"
4. Désinstaller

**Sur iOS :**
1. Maintenir l'icône de l'app
2. Supprimer l'application

### Étape 2 : Vider Complètement le Cache du Navigateur

**Chrome/Edge (Recommandé) :**

1. **Ouvrir DevTools** : F12 ou Clic droit > Inspecter

2. **Onglet Application** :
   - Service Workers > Cliquer "Unregister" sur tous les Service Workers
   - Cache Storage > Cliquer droit sur chaque cache > Delete
   - Clear storage > Cocher "Service Workers", "Cache storage", "Application cache"
   - Cliquer "Clear site data"

3. **Onglet Network** :
   - Cliquer droit > Clear browser cache

4. **Vider le cache complet** :
   - Ctrl+Shift+Delete (ou Cmd+Shift+Delete sur Mac)
   - Période : "Tout" ou "Toutes les données"
   - Cocher :
     - ✅ Historique de navigation
     - ✅ Cookies et données de sites
     - ✅ Images et fichiers en cache
   - Cliquer "Effacer les données"

5. **Forcer le rechargement sans cache** :
   - Ctrl+Shift+R (ou Cmd+Shift+R sur Mac)
   - OU : Ctrl+F5

**Firefox :**

1. **Ouvrir DevTools** : F12

2. **Onglet Stockage** :
   - Service Workers > Désenregistrer
   - Cache > Tout supprimer
   - IndexedDB > Tout supprimer

3. **Vider le cache** :
   - Ctrl+Shift+Delete
   - Période : Tout
   - Cocher tout
   - Effacer maintenant

4. **Forcer rechargement** :
   - Ctrl+Shift+R

### Étape 3 : Réinstaller la PWA avec les Nouvelles Icônes

1. **Ouvrir l'application** : https://www.hydria.mg/

2. **Attendre le prompt d'installation** :
   - Chrome : Icône ⊕ dans la barre d'adresse
   - OU : Bouton "Installer l'app" dans la navbar

3. **Vérifier la nouvelle icône** :
   - Dans le prompt d'installation, l'icône doit être le **vase** (pas l'ancien)
   - Si c'est toujours l'ancien, retourner à l'Étape 2

4. **Installer** : Cliquer "Installer" ou "Autoriser"

5. **Vérifier** :
   - L'icône sur le bureau/menu démarrer doit être le vase
   - Les raccourcis (Feed, Plannings, Compta) doivent avoir les couleurs appropriées

## Vérification du Service Worker

**DevTools > Application > Service Workers** :

✅ **Version correcte** : `hydria-v1.1.0`
✅ **Statut** : Activé et en cours d'exécution
✅ **Scope** : `/`

## Vérification du Cache

**DevTools > Application > Cache Storage** :

Vous devriez voir 3 caches :
- `hydria-v1.1.0-static` : Fichiers statiques (CSS, JS, pages)
- `hydria-v1.1.0-dynamic` : Contenu dynamique
- `hydria-v1.1.0-api` : Réponses API

**Cliquer sur `hydria-v1.1.0-static`** pour vérifier qu'il contient :
- `/`
- `/feed/`
- `/plannings/`
- `/comptabilite/`
- `/employes/`
- `/static/css/hydria.css`
- `/static/js/theme-switcher.js`
- `/static/js/offline-db.js`
- `/static/js/pwa-manager.js`
- `/static/images/icons/icon-192x192.png`
- `/static/images/icons/icon-512x512.png`
- `/offline/`

## Test de Fonctionnement Hors Ligne

1. **Ouvrir l'application** : https://www.hydria.mg/

2. **Ouvrir DevTools** : F12

3. **Activer mode hors ligne** :
   - Onglet Network
   - Dropdown : "No throttling" > Offline

4. **Tester la navigation** :
   - ✅ Page d'accueil doit s'afficher
   - ✅ Cliquer "Feed" : doit s'afficher (pas "Vous êtes hors connexion")
   - ✅ Cliquer "Plannings" : doit s'afficher
   - ✅ Cliquer "Comptabilité" : doit s'afficher
   - ✅ Cliquer "Employés" : doit s'afficher

5. **Indicateur de connexion** :
   - Badge "Hors ligne" (rouge) doit être visible dans la navbar

## Dépannage

### Problème : Les anciennes icônes persistent

**Solution** :
1. Supprimer TOUTES les installations PWA (Windows, Android, iOS)
2. Vider le cache du navigateur (Ctrl+Shift+Delete > Tout)
3. Fermer COMPLÈTEMENT le navigateur (pas juste l'onglet)
4. Rouvrir le navigateur
5. Aller sur https://www.hydria.mg/
6. Hard refresh : Ctrl+Shift+R
7. DevTools > Application > Clear storage > Clear site data
8. Rafraîchir : F5
9. Réinstaller la PWA

### Problème : Service Worker ne s'installe pas

**Solution** :
1. Vérifier que le site est en HTTPS (ou localhost)
2. DevTools > Console : Vérifier les erreurs
3. DevTools > Application > Service Workers > Cliquer "Update"
4. Si erreur "Failed to register", vérifier que sw.js est accessible : https://www.hydria.mg/static/sw.js

### Problème : Mode hors ligne ne fonctionne pas

**Solution** :
1. Vérifier que le Service Worker est bien version `hydria-v1.1.0`
2. DevTools > Application > Cache Storage : Vérifier que les pages sont en cache
3. Vérifier la console pour des erreurs réseau
4. Forcer la mise à jour du Service Worker : DevTools > Application > Service Workers > Cliquer "Update"

## Commandes DevTools Console (pour debug)

```javascript
// Vérifier version du Service Worker
navigator.serviceWorker.getRegistration().then(reg => console.log(reg.active.scriptURL));

// Lister tous les caches
caches.keys().then(names => console.log(names));

// Vérifier contenu d'un cache
caches.open('hydria-v1.1.0-static').then(cache => cache.keys()).then(keys => console.log(keys.map(k => k.url)));

// Forcer mise à jour du Service Worker
navigator.serviceWorker.getRegistration().then(reg => reg.update());

// Désinscrire le Service Worker
navigator.serviceWorker.getRegistration().then(reg => reg.unregister());
```

## Ordre Recommandé de Nettoyage Complet

1. ✅ Désinstaller PWA (si installée)
2. ✅ DevTools > Application > Service Workers > Unregister
3. ✅ DevTools > Application > Cache Storage > Delete all
4. ✅ DevTools > Application > Clear storage > Clear site data
5. ✅ Ctrl+Shift+Delete > Tout > Effacer
6. ✅ Fermer le navigateur complètement
7. ✅ Rouvrir le navigateur
8. ✅ Aller sur https://www.hydria.mg/
9. ✅ Ctrl+Shift+R (hard refresh)
10. ✅ Attendre que le nouveau Service Worker s'installe
11. ✅ Réinstaller la PWA

## Résultat Attendu

Après ce nettoyage complet, vous devriez voir :

✅ **Nouvelle icône vase** dans le prompt d'installation
✅ **Service Worker v1.1.0** actif
✅ **Cache étendu** avec toutes les pages principales
✅ **Fonctionnement hors ligne** complet (pas de message "Vous êtes hors connexion")
✅ **Badge "Hors ligne"** visible quand déconnecté
✅ **Application installée** avec la nouvelle icône sur le bureau/menu

---

**Date de dernière mise à jour** : 11 janvier 2026
**Version Service Worker** : v1.1.0
**Version icônes** : Vase (icons8-vase-94.png)