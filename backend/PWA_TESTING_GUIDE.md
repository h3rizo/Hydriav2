# Guide de Test PWA - Hydria

## 🎯 Objectif

Ce guide vous permet de tester toutes les fonctionnalités PWA de l'application Hydria, notamment le mode hors ligne et la synchronisation automatique.

## 📋 Prérequis

- ✅ Application Django démarrée : `python manage.py runserver`
- ✅ Navigateur compatible : Chrome, Edge, ou Firefox
- ✅ DevTools du navigateur activés (F12)

## 🧪 Tests à effectuer

### 1. Vérification de l'enregistrement du Service Worker

**Étapes :**
1. Ouvrir l'application dans Chrome : http://localhost:8000/
2. Appuyer sur F12 pour ouvrir DevTools
3. Aller dans l'onglet "Application" (ou "Application" en anglais)
4. Dans le menu de gauche, cliquer sur "Service Workers"

**Résultat attendu :**
- ✅ Un Service Worker doit être listé avec le statut "activated and is running"
- ✅ Source : `/static/sw.js`
- ✅ Scope : `/`

**Captures d'écran :**
```
Service Workers
  ☑ activated and is running
  Source: /static/sw.js
  Scope: /
```

### 2. Vérification du Manifest

**Étapes :**
1. Dans DevTools, toujours dans "Application"
2. Cliquer sur "Manifest" dans le menu de gauche

**Résultat attendu :**
- ✅ Nom : "Hydria - Gestion Eau Madagascar"
- ✅ Nom court : "Hydria"
- ✅ Start URL : "/"
- ✅ Theme color : "#3b82f6"
- ✅ Icons : 8 icônes de 72x72 à 512x512

### 3. Vérification du Cache

**Étapes :**
1. Dans DevTools → Application → Storage → Cache Storage
2. Vérifier les caches créés

**Résultat attendu :**
- ✅ Cache `hydria-v1.0.0-static` contenant :
  - `/`
  - `/static/css/hydria.css`
  - `/static/js/theme-switcher.js`
  - `/offline/`

### 4. Test du bouton d'installation

**Étapes :**
1. Chercher le bouton "Installer l'app" dans la navbar (en haut à droite)
2. Si le bouton n'apparaît pas :
   - Dans DevTools → Application → Manifest
   - Cliquer sur "Install" pour simuler le prompt d'installation
3. Cliquer sur "Installer l'app"

**Résultat attendu :**
- ✅ Une fenêtre de confirmation s'ouvre
- ✅ Après installation, une icône Hydria apparaît sur le bureau/menu applications
- ✅ L'app s'ouvre dans une fenêtre séparée (sans barre d'adresse)

### 5. Test du mode hors ligne

**Étapes :**
1. Dans DevTools → Network
2. Cocher la case "Offline" (en haut de l'onglet Network)
3. Rafraîchir la page (F5)

**Résultat attendu :**
- ✅ La page continue de s'afficher normalement
- ✅ Le badge de connexion dans la navbar devient rouge "Hors ligne"
- ✅ Message toast : "📴 Mode hors ligne activé"

**Si la page ne charge pas :**
- Vérifier que le Service Worker est bien actif
- Vérifier que le cache static contient bien `/`
- Essayer de naviguer vers `/offline/` directement

### 6. Test de la page offline

**Étapes :**
1. En mode offline (case "Offline" cochée)
2. Naviguer vers une page non mise en cache : http://localhost:8000/une-page-inexistante/

**Résultat attendu :**
- ✅ La page `/offline/` s'affiche
- ✅ Message : "Vous êtes actuellement hors ligne"
- ✅ Liste des fonctionnalités disponibles hors ligne
- ✅ Boutons "Retour" et "Réessayer"

### 7. Test de l'indicateur de connexion

**Étapes :**
1. Mode online → Vérifier badge vert "En ligne"
2. Activer mode offline → Badge devient rouge "Hors ligne"
3. Désactiver mode offline → Badge redevient vert "En ligne"

**Résultat attendu :**
- ✅ Changement automatique du badge selon l'état de connexion
- ✅ Icône wifi change : fa-wifi (online) / fa-wifi-slash (offline)
- ✅ Notification toast lors du changement d'état

### 8. Test de l'IndexedDB

**Étapes :**
1. Dans DevTools → Application → Storage → IndexedDB
2. Développer "HydriaOfflineDB"

**Résultat attendu :**
- ✅ Base de données "HydriaOfflineDB" créée
- ✅ 5 object stores présents :
  - releves
  - plannings
  - paiements
  - reparations
  - sync_queue

### 9. Test de la synchronisation (simulation)

**Étapes :**
1. En mode online, ouvrir la console JavaScript (F12 → Console)
2. Exécuter :
```javascript
// Simuler ajout d'une donnée en attente de sync
offlineDB.addToSyncQueue(
    'releve',
    'create',
    { point_eau_id: '123', montant: 5000 },
    '/api/releves/create/'
).then(() => console.log('[OK] Donnée ajoutée à la file'));

// Vérifier la file
offlineDB.getPendingSync().then(items => {
    console.log(`[INFO] ${items.length} élément(s) en attente`);
});

// Simuler synchronisation
pwaManager.syncData();
```

**Résultat attendu :**
- ✅ Console affiche : `[OK] Donnée ajoutée à la file`
- ✅ Console affiche : `[INFO] 1 élément(s) en attente`
- ✅ Indicateur de sync apparaît brièvement (spinner)
- ✅ Requête fetch visible dans Network tab

**Note :** La synchronisation échouera car l'endpoint n'existe pas, mais le mécanisme est testé.

### 10. Test du rechargement après mise à jour

**Étapes :**
1. Modifier `backend/static/sw.js` :
   - Changer `CACHE_VERSION = 'hydria-v1.0.0'` en `CACHE_VERSION = 'hydria-v1.0.1'`
2. Rafraîchir la page
3. Dans DevTools → Application → Service Workers
4. Cliquer sur "Update" ou "skipWaiting" si proposé

**Résultat attendu :**
- ✅ Nouvelle version du Service Worker détectée
- ✅ Notification toast : "Une nouvelle version d'Hydria est disponible !"
- ✅ Bouton "Mettre à jour" dans la notification
- ✅ Clic sur "Mettre à jour" → Page se recharge
- ✅ Ancien cache supprimé (`hydria-v1.0.0-*`)
- ✅ Nouveau cache créé (`hydria-v1.0.1-*`)

## 📊 Checklist complète

- [ ] Service Worker enregistré et actif
- [ ] Manifest affiché correctement dans DevTools
- [ ] Cache static créé avec 4+ fichiers
- [ ] Bouton d'installation visible (ou simulable)
- [ ] Installation de l'app réussie
- [ ] Mode offline fonctionne (page reste accessible)
- [ ] Badge connexion change selon statut (vert/rouge)
- [ ] Page /offline/ s'affiche si route non cachée
- [ ] IndexedDB créée avec 5 stores
- [ ] Synchronisation simulée fonctionne
- [ ] Mise à jour du SW détectée et notifiée

## 🐛 Dépannage

### Service Worker ne s'enregistre pas

**Causes possibles :**
- URL incorrecte : Vérifier `/static/sw.js` accessible
- Erreur JavaScript : Ouvrir Console pour voir erreurs
- Navigateur non compatible : Utiliser Chrome/Edge

**Solution :**
```bash
# Vérifier que le fichier existe
ls backend/static/sw.js

# Vérifier qu'il est servi par Django
curl http://localhost:8000/static/sw.js
```

### Cache vide

**Cause :** Les fichiers statiques listés dans `STATIC_FILES` n'existent pas

**Solution :**
- Vérifier que `/static/css/hydria.css` existe
- Vérifier que `/static/js/theme-switcher.js` existe
- Vérifier que la route `/offline/` fonctionne

### Mode offline ne fonctionne pas

**Cause :** Page non mise en cache

**Solution :**
1. Charger la page en mode online d'abord
2. Vérifier dans DevTools → Application → Cache Storage que `/` est présent
3. Passer en mode offline
4. Rafraîchir

### IndexedDB non créée

**Cause :** Script `offline-db.js` non chargé ou erreur

**Solution :**
1. Vérifier Console pour erreurs JavaScript
2. Vérifier que `<script src="{% static 'js/offline-db.js' %}">` est dans base.html
3. Vérifier que le fichier existe : `backend/static/js/offline-db.js`

## 📱 Test sur mobile

**Android (Chrome) :**
1. Activer mode développeur sur le téléphone
2. Connecter en USB au PC
3. Dans Chrome desktop : chrome://inspect
4. Sélectionner votre appareil
5. Ouvrir l'application
6. Cliquer sur "Add to Home screen"

**iOS (Safari) :**
1. Ouvrir l'application dans Safari
2. Appuyer sur le bouton Partager
3. Sélectionner "Sur l'écran d'accueil"
4. Confirmer

**Test mode avion :**
1. Installer l'app
2. Activer mode avion
3. Ouvrir l'app depuis l'écran d'accueil
4. Vérifier qu'elle fonctionne

## ✅ Validation finale

Si tous les tests passent, la PWA est complètement fonctionnelle ! 🎉

L'application peut maintenant :
- ✅ Être installée comme une app native
- ✅ Fonctionner hors ligne
- ✅ Synchroniser automatiquement les données
- ✅ Mettre à jour son cache automatiquement
- ✅ Fournir un feedback visuel à l'utilisateur

## 📚 Ressources

- [Service Worker API (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)
- [Web App Manifest (MDN)](https://developer.mozilla.org/en-US/docs/Web/Manifest)
- [IndexedDB API (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API)
- [PWA Checklist (web.dev)](https://web.dev/pwa-checklist/)
