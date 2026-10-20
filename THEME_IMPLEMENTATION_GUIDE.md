# 🎨 Guide d'implémentation des thèmes Hydria

## ✅ **Implémentation terminée**

### **1. Configuration Tailwind/DaisyUI**
- ✅ Thème sombre personnalisé `hydriaDark` configuré
- ✅ Thème clair `winter` de DaisyUI intégré 
- ✅ Transition fluide entre les thèmes

### **2. Fichiers créés/modifiés**

#### **Frontend Nuxt 3 :**
```
frontend/
├── tailwind.config.js              ✅ Mis à jour avec les nouveaux thèmes
├── composables/useTheme.ts         ✅ Composable pour gestion du thème
├── components/ThemeToggle.vue       ✅ Composant de bascule de thème
├── plugins/theme.client.ts         ✅ Plugin d'initialisation
└── nuxt.config.ts                  ✅ Configuration thème par défaut
```

#### **Backend Django :**
```
backend/
├── templates/base.html              ✅ Bouton de thème + JavaScript
└── static/css/hydria-themes.css     ✅ Variables CSS personnalisées
```

## 🎯 **Comment utiliser les thèmes**

### **Classes à utiliser (TOUJOURS) :**

#### **Arrière-plans :**
```html
<!-- ✅ CORRECT : Classes sémantiques -->
<div class="bg-base-100">Fond principal</div>
<div class="bg-base-200">Fond secondaire</div>
<div class="bg-base-300">Bordures/séparateurs</div>

<!-- ❌ INCORRECT : Classes Tailwind directes -->
<div class="bg-gray-800">Ne pas utiliser</div>
<div class="bg-white">Ne pas utiliser</div>
```

#### **Textes :**
```html
<!-- ✅ CORRECT -->
<p class="text-base-content">Texte principal</p>
<p class="text-base-content/70">Texte secondaire</p>

<!-- ❌ INCORRECT -->
<p class="text-gray-900">Ne pas utiliser</p>
<p class="text-white">Ne pas utiliser</p>
```

#### **Boutons :**
```html
<!-- ✅ CORRECT -->
<button class="btn btn-primary">Action principale</button>
<button class="btn btn-secondary">Action secondaire</button>
<button class="btn btn-accent">Action accent</button>

<!-- ❌ INCORRECT -->
<button class="bg-blue-500 text-white">Ne pas utiliser</button>
```

#### **Cartes et conteneurs :**
```html
<!-- ✅ CORRECT -->
<div class="card bg-base-100 shadow-xl">
    <div class="card-body">
        <h2 class="card-title text-primary">Titre</h2>
        <p class="text-base-content">Contenu</p>
    </div>
</div>
```

## 📱 **Utilisation dans Nuxt 3**

### **Dans un composant Vue :**
```vue
<template>
  <div class="min-h-screen bg-base-200">
    <!-- Header avec bouton de thème -->
    <nav class="navbar bg-base-100 shadow-lg">
      <div class="navbar-start">
        <h1 class="text-xl font-bold text-base-content">Mon App</h1>
      </div>
      <div class="navbar-end">
        <ThemeToggle />
      </div>
    </nav>
    
    <!-- Contenu principal -->
    <main class="container mx-auto p-6">
      <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
          <h2 class="card-title text-primary">Exemple de carte</h2>
          <p class="text-base-content">
            Thème actuel : {{ themeDisplayName }}
          </p>
          <div class="card-actions justify-end">
            <button class="btn btn-primary" @click="toggleTheme">
              Changer le thème
            </button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
const { toggleTheme, themeDisplayName } = useTheme()
</script>
```

## 🌐 **Utilisation dans Django**

### **Template Django :**
```html
{% extends "base.html" %}

{% block content %}
<div class="container mx-auto p-6">
    <!-- Carte avec classes sémantiques -->
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title text-primary">Titre de la section</h2>
            <p class="text-base-content">
                Ce contenu s'adapte automatiquement au thème choisi.
            </p>
            
            <!-- Alertes thématiques -->
            <div class="alert alert-info mb-4">
                <svg class="stroke-current shrink-0 w-6 h-6" fill="none" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <span>Information importante</span>
            </div>
            
            <!-- Boutons thématiques -->
            <div class="flex gap-4">
                <button class="btn btn-primary">Action principale</button>
                <button class="btn btn-secondary">Action secondaire</button>
                <button class="btn btn-accent">Action accent</button>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

## 🎨 **Palettes de couleurs**

### **Thème sombre (hydriaDark) :**
```css
Primary: #3b82f6 (Bleu)
Secondary: #64748b (Slate)
Accent: #10b981 (Emerald)
Base-100: #1f2937 (Fond principal)
Base-200: #111827 (Fond secondaire)
Base-content: #f9fafb (Texte principal)
```

### **Thème clair (winter) :**
```css
Primary: DaisyUI winter primary
Secondary: DaisyUI winter secondary
Accent: DaisyUI winter accent
Base-100: #ffffff (Fond principal)
Base-200: #f2f2f2 (Fond secondaire)
Base-content: #1f2937 (Texte principal)
```

## 🔧 **Fonctionnalités implémentées**

### **✅ Persistance :**
- Le choix de thème est sauvegardé dans `localStorage`
- Clé utilisée : `hydria-theme`
- Aucun flash lors du chargement

### **✅ Animations :**
- Transitions fluides (0.3s) pour tous les changements
- Animation du bouton de bascule avec effet `swap-rotate`
- Hover effects sur les éléments interactifs

### **✅ Accessibilité :**
- Contrastes respectés selon les standards WCAG
- Navigation au clavier fonctionnelle
- Icônes descriptives pour les thèmes

### **✅ Responsive :**
- Fonctionne sur mobile, tablette et desktop
- Bouton de thème adaptatif selon la taille d'écran

## 🚀 **Test et validation**

Pour tester le système de thème :

1. **Lancez l'application :**
   ```bash
   # Backend Django
   cd backend && python manage.py runserver
   
   # Frontend Nuxt (si besoin)
   cd frontend && npm run dev
   ```

2. **Accédez à l'interface :**
   - Django : http://127.0.0.1:8000/
   - Nuxt : http://127.0.0.1:3000/

3. **Testez la bascule :**
   - Cliquez sur l'icône soleil/lune dans la navbar
   - Vérifiez que tous les éléments changent de thème
   - Rechargez la page → le thème doit persister
   - Fermez/rouvrez le navigateur → le thème doit persister

## ⚠️ **Important : Classes à éviter**

### **❌ N'UTILISEZ JAMAIS ces classes :**
```css
bg-gray-*
bg-white
bg-black
text-gray-*
text-white
text-black
border-gray-*
```

### **✅ Utilisez TOUJOURS ces classes :**
```css
bg-base-*
text-base-content
text-primary
text-secondary
border-base-*
btn-primary
btn-secondary
alert-info
alert-success
```

Cette approche garantit que tous les composants s'adaptent automatiquement aux changements de thème sans problème de cohérence ! 🎯