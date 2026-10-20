# Stratégie de Migration Backend Django → Frontend Nuxt 3

## 📋 Vue d'ensemble

Ce document décrit la stratégie pour migrer toutes les pages du backend Django Templates vers le frontend Nuxt 3.

## 🎯 Objectifs

1. **Architecture moderne** : SPA (Single Page Application) avec Nuxt 3
2. **API REST** : Utilisation des APIs Django existantes
3. **Réutilisation** : Maximum de code backend (modèles, vues API)
4. **Performance** : SSR (Server-Side Rendering) optionnel, cache intelligent
5. **Mobile-first** : PWA avec fonctionnalités offline

## 🏗️ Architecture Cible

```
Frontend (Nuxt 3)              Backend (Django)
─────────────────              ────────────────
├── Pages (Vue)         →      ├── APIs (DRF)
├── Composables         ←      ├── Models
├── Components          ←      ├── Serializers
├── Stores (Pinia)      ←      └── Business Logic
└── Assets
```

## 📦 Stack Technique

### Frontend
- **Framework** : Nuxt 3 (Vue 3 + Composition API)
- **UI** : Tailwind CSS + DaisyUI
- **État** : Pinia
- **HTTP** : $fetch (Nuxt) avec CSRF handling
- **Icônes** : Font Awesome
- **Charts** : Chart.js
- **Maps** : Leaflet / MapboxGL
- **PWA** : @vite-pwa/nuxt

### Backend (conservé)
- **Framework** : Django 5.2 + DRF
- **Base de données** : PostgreSQL (Supabase)
- **Auth** : Django session + OAuth2

## 🔄 Processus de Migration par Page

### Étape 1 : Analyse
- [ ] Identifier les templates Django utilisés
- [ ] Lister les données affichées
- [ ] Identifier les APIs Django existantes
- [ ] Vérifier les permissions/autorisations

### Étape 2 : Préparation Backend
- [ ] Créer/Vérifier les serializers DRF
- [ ] Créer/Vérifier les viewsets API
- [ ] Ajouter les routes `/api/` si manquantes
- [ ] Tester les APIs avec curl/Postman

### Étape 3 : Création Frontend
- [ ] Créer la page dans `/pages/`
- [ ] Créer les composables nécessaires (`use*.ts`)
- [ ] Créer les composants réutilisables
- [ ] Implémenter la logique métier
- [ ] Gérer les états de chargement
- [ ] Gérer les erreurs

### Étape 4 : Styling
- [ ] Appliquer Tailwind CSS + DaisyUI
- [ ] Responsive design (mobile, tablet, desktop)
- [ ] Mode sombre/clair
- [ ] Animations

### Étape 5 : Tests
- [ ] Test fonctionnel (CRUD complet)
- [ ] Test responsive
- [ ] Test permissions
- [ ] Test erreurs réseau

### Étape 6 : Déploiement
- [ ] Build production
- [ ] Vérifier performance
- [ ] Mettre à jour routes Django (redirection)

## 📂 Structure des Dossiers Frontend

```
frontend/
├── pages/                      # Pages Nuxt (routes automatiques)
│   ├── index.vue              # Page d'accueil
│   ├── dashboard/             # Dashboard et sous-pages
│   ├── employees/             # 🆕 Module RH
│   │   ├── index.vue          # Liste employés
│   │   ├── fiches-poste.vue   # 🆕 Gestion fiches de poste
│   │   └── evaluations/       # 🆕 Module évaluations
│   │       ├── index.vue      # Liste évaluations
│   │       ├── creer.vue      # Créer évaluation
│   │       └── [id].vue       # Détail/Modifier évaluation
│   ├── billing/               # Facturation
│   ├── planning/              # Planning
│   ├── chantiers/             # Chantiers
│   └── accounting/            # Comptabilité
│
├── components/                 # Composants réutilisables
│   ├── ui/                    # Composants UI de base
│   │   ├── Modal.vue
│   │   ├── Table.vue
│   │   ├── Card.vue
│   │   └── Button.vue
│   ├── forms/                 # Composants formulaire
│   │   ├── Input.vue
│   │   ├── Select.vue
│   │   └── DatePicker.vue
│   └── employees/             # 🆕 Composants RH
│       ├── FichePosteCard.vue
│       ├── EvaluationCard.vue
│       └── NotationForm.vue
│
├── composables/               # Logique réutilisable
│   ├── useApi.ts             # ✅ Appels API avec CSRF
│   ├── useTimezone.ts        # ✅ Gestion timezone Madagascar
│   ├── useAuth.js            # ✅ Authentification
│   ├── useTheme.ts           # ✅ Mode dark/light
│   ├── useEmployees.ts       # 🆕 Logique employés
│   ├── useFichesPoste.ts     # 🆕 Logique fiches de poste
│   └── useEvaluations.ts     # 🆕 Logique évaluations
│
├── stores/                    # État global (Pinia)
│   ├── auth.ts               # État auth
│   ├── user.ts               # Utilisateur connecté
│   ├── employees.ts          # 🆕 État employés
│   └── evaluations.ts        # 🆕 État évaluations
│
├── layouts/                   # Layouts
│   └── default.vue           # Layout principal avec navbar
│
└── assets/                    # Assets statiques
    └── css/
        └── main.css          # Tailwind + custom CSS
```

## 🔐 Gestion CSRF Token (Django)

Le composable `useApi.ts` gère automatiquement les CSRF tokens :

```typescript
// Exemple d'utilisation
const { data, error } = await useApi('/api/fiches-poste/', {
  method: 'POST',
  body: { tache: 'Ma tâche', description: '...' }
})
```

## 🌍 Gestion Timezone Madagascar

Le composable `useTimezone.ts` gère automatiquement les conversions :

```typescript
// Exemple d'utilisation
const { formatDate, parseDate } = useTimezone()

// Convertir date Django → Display
const dateDisplay = formatDate('2025-01-01T21:00:00Z') // "2025-01-02" (Madagascar)

// Parser date input → Django format
const dateUtc = parseDate('2025-01-02') // "2025-01-01T21:00:00Z"
```

## 📋 Ordre de Migration Suggéré

### Phase 1 : Module RH (Priorité 1) 🆕
1. **Fiches de poste** (`/employees/fiches-poste`)
   - Composable `useFichesPoste.ts`
   - Composants `FichePosteCard.vue`, `FichePosteModal.vue`
   - APIs : GET/POST/PUT/DELETE `/api/fiches-poste/`

2. **Évaluations** (`/employees/evaluations/`)
   - Composable `useEvaluations.ts`
   - Composants `EvaluationCard.vue`, `NotationForm.vue`, `HistoriqueModal.vue`
   - APIs : `/api/evaluations/list/`, `/api/evaluations/create/`, etc.

### Phase 2 : Facturation (Priorité 2)
3. **Relevés** (`/billing/releves`)
4. **Workflow facturation** (`/billing/workflow-facturation`)
5. **Paiements forfaitaires** (`/billing/paiements-forfaitaires`)

### Phase 3 : Planning (Priorité 3)
6. **Calendrier** (`/planning/calendar`)
7. **Livraisons** (`/planning/livraisons`)
8. **Avances** (`/planning/avances`)

### Phase 4 : Comptabilité (Priorité 4)
9. **Vérification** (`/accounting/verification`)
10. **Recoupements** (`/accounting/recoupement/`)
11. **Import DiameX** (`/accounting/import`)

## 🎨 Conventions de Code

### Nommage
- **Fichiers** : kebab-case (`fiches-poste.vue`)
- **Composants** : PascalCase (`FichePosteCard.vue`)
- **Composables** : camelCase avec préfixe `use` (`useFichesPoste.ts`)
- **Variables** : camelCase
- **Constants** : SCREAMING_SNAKE_CASE

### Structure d'un composable

```typescript
// composables/useFichesPoste.ts
export const useFichesPoste = () => {
  const fiches = ref([])
  const loading = ref(false)
  const error = ref(null)

  const loadFiches = async (posteId: string) => {
    loading.value = true
    error.value = null
    try {
      const { data } = await useApi(`/api/fiches-poste/${posteId}/`)
      fiches.value = data.fiches
    } catch (e) {
      error.value = e
    } finally {
      loading.value = false
    }
  }

  return {
    fiches,
    loading,
    error,
    loadFiches
  }
}
```

### Structure d'une page

```vue
<template>
  <div class="container mx-auto px-4 py-8">
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-3xl font-bold">Titre</h1>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center">
      <span class="loading loading-spinner loading-lg"></span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="alert alert-error">
      {{ error }}
    </div>

    <!-- Content -->
    <div v-else>
      <!-- Contenu ici -->
    </div>
  </div>
</template>

<script setup lang="ts">
// Imports
// State
// Lifecycle
// Methods
</script>
```

## 🔧 Scripts Utiles

```bash
# Démarrer dev server
npm run dev

# Build production
npm run build

# Preview production
npm run preview

# Linter
npm run lint

# Tests (à configurer)
npm run test
```

## ✅ Checklist par Page Migrée

- [ ] Page créée dans `/pages/`
- [ ] APIs Django testées
- [ ] Composables créés
- [ ] Composants créés
- [ ] Styling Tailwind + DaisyUI appliqué
- [ ] Responsive design vérifié
- [ ] Gestion erreurs implémentée
- [ ] Loading states implémentés
- [ ] Permissions vérifiées
- [ ] Tests fonctionnels OK
- [ ] Documentation mise à jour (PAGES_TODO.md)
- [ ] Route Django redirigée (optionnel)

## 📝 Notes Importantes

1. **Backend conservé** : Django reste le backend API, on ne touche qu'aux templates
2. **APIs existantes** : Réutiliser au maximum les APIs Django déjà créées
3. **CSRF obligatoire** : Toujours utiliser `useApi.ts` pour les POST/PUT/DELETE
4. **Timezone Madagascar** : Toujours utiliser `useTimezone.ts` pour les dates
5. **DaisyUI** : Utiliser les composants DaisyUI au maximum (badges, cards, modals)
6. **Mobile-first** : Toujours tester responsive dès le début

## 🚀 Prochaines Étapes

1. ✅ Mettre à jour PAGES_TODO.md avec nouvelles pages RH
2. 🔄 Créer structure module RH (`/employees/`)
3. 🔄 Migrer Fiches de poste
4. 🔄 Migrer Évaluations
5. Continuer avec les autres modules selon priorités
