# Authentification API Hydria

## Vue d'ensemble

Cette API d'authentification permet au frontend Nuxt/Vue de partager la même authentification que le backend Django, avec compatibilité complète pour le fonctionnement hors ligne.

## Endpoints disponibles

### 1. Statut d'authentification
```
GET /api/auth/status/
```
**Réponse non authentifié :**
```json
{
  "is_authenticated": false,
  "csrf_token": "..."
}
```

**Réponse authentifié :**
```json
{
  "is_authenticated": true,
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@hydria.mg",
    "first_name": "Admin",
    "last_name": "Hydria",
    "is_staff": true,
    "is_active": true
  },
  "session_key": "...",
  "csrf_token": "..."
}
```

### 2. Connexion
```
POST /api/auth/login/
```
**Body :**
```json
{
  "username": "admin",
  "password": "motdepasse"
}
```

**Réponse succès :**
```json
{
  "success": true,
  "message": "Connexion réussie",
  "user": { ... },
  "session_key": "...",
  "csrf_token": "..."
}
```

### 3. Déconnexion
```
POST /api/auth/logout/
```
**Headers requis :** `X-CSRFToken`

### 4. Rafraîchissement de session
```
POST /api/auth/refresh/
```
**Headers requis :** `X-CSRFToken`

### 5. Token CSRF uniquement
```
GET /api/auth/csrf/
```

## Compatibilité hors ligne

### Fonctionnalités supportées

1. **Cache local** : L'état d'authentification est sauvegardé dans localStorage
2. **Validation hors ligne** : Le frontend peut valider l'authentification sans réseau
3. **Expiration intelligente** : Sessions valides 7 jours maximum
4. **Synchronisation automatique** : Mise à jour quand la connexion revient

### Architecture hors ligne

```javascript
// Exemple d'utilisation dans Nuxt 3
const { user, isAuthenticated, isOnline } = useAuth()

// Connexion avec fallback hors ligne
const result = await login(username, password)
if (result.offline) {
  // Authentification basée sur le cache local
}

// Détection automatique en/hors ligne
watch(isOnline, async (online) => {
  if (online) {
    await checkAuthStatus() // Re-valider avec le serveur
    await syncPendingActions() // Synchroniser les actions en attente
  }
})
```

### Gestion des actions différées

Les actions effectuées hors ligne sont mises en queue et synchronisées automatiquement :

```javascript
// Ajouter une action à synchroniser plus tard
addPendingAction({
  url: '/api/plannings/',
  method: 'POST',
  body: { ... },
  headers: { ... }
})
```

## Configuration CORS

L'API est configurée pour accepter les requêtes cross-origin depuis :
- `http://localhost:3000` (Nuxt dev)
- `http://127.0.0.1:3000`

### Headers autorisés
- `X-CSRFToken` (authentification)
- `Authorization` (si JWT ajouté plus tard)
- `Content-Type`

## Sécurité

### Session Django
- Sessions basées sur les cookies Django natifs
- Protection CSRF activée
- Expiration automatique

### CORS sécurisé
- Origines spécifiques autorisées uniquement
- Credentials (cookies) autorisés
- Headers limités aux besoins

## Intégration frontend

### 1. Composable Nuxt
```typescript
// composables/useAuth.ts
export const useAuth = () => {
  const user = ref(null)
  const isAuthenticated = ref(false)

  const login = async (username: string, password: string) => {
    const response = await $fetch('/api/auth/login/', {
      method: 'POST',
      body: { username, password }
    })
    // Gestion du cache local...
  }

  return { user, isAuthenticated, login }
}
```

### 2. Middleware d'authentification
```typescript
// middleware/auth.ts
export default defineNuxtRouteMiddleware((to, from) => {
  const { isAuthenticated, requireAuth } = useAuth()

  requireAuth()
})
```

### 3. Plugin d'initialisation
```typescript
// plugins/auth.client.ts
export default defineNuxtPlugin(async () => {
  const { loadAuthState, checkAuthStatus } = useAuth()

  // Charger le cache local
  loadAuthState()

  // Vérifier avec le serveur si en ligne
  if (navigator.onLine) {
    await checkAuthStatus()
  }
})
```

## Avantages de cette approche

### ✅ Cohérence
- Une seule source d'authentification
- Pas de double gestion des utilisateurs
- Sessions partagées

### ✅ Performance
- Cache local pour réponses instantanées
- Validation serveur uniquement si nécessaire
- Synchronisation intelligente

### ✅ Résilience
- Fonctionne complètement hors ligne
- Récupération automatique en ligne
- Pas de perte de données

### ✅ Sécurité
- Utilise l'authentification Django éprouvée
- Protection CSRF native
- Expiration de session standard

## Utilisation recommandée

1. **Initialisation** : Charger l'état au démarrage de l'app
2. **Connexion** : Utiliser l'endpoint login avec cache automatique
3. **Navigation** : Vérifier l'authentification via le middleware
4. **Hors ligne** : L'app continue de fonctionner normalement
5. **Retour en ligne** : Synchronisation automatique

Cette architecture garantit une expérience utilisateur fluide avec ou sans connexion internet.