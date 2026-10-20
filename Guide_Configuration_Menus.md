# Guide Configuration des Menus - Hydria Django

## 📋 Objectif
Ce guide explique comment configurer les liens des menus de navigation pour pointer vers les bonnes pages du projet Hydria.

## 🎯 Cas d'usage traité
**Problème** : Le sous-menu "Saisie planning" pointait vers le formulaire simple (`planning:create`) au lieu de la page dashboard avec tableau et détails.

**Solution** : Rediriger vers la page dashboard avec le formulaire tableau interactif.

---

## 🔍 Étapes de résolution

### 1. Localiser les pages existantes

```bash
# Rechercher tous les fichiers liés au planning
find . -name "*planning*" -type f

# Rechercher les templates HTML de planning
find . -name "*.html" -type f | grep -i planning
```

**Résultats trouvés :**
- `backend/templates/planning/planning_dashboard.html` ← **PAGE CIBLE** avec tableau et détails
- `backend/templates/planning/planning_form.html` ← Formulaire simple
- `backend/templates/planning/planning_list.html` ← Liste simple

### 2. Analyser le contenu des pages

La page `planning_dashboard.html` contient :
- ✅ **Formulaire de filtres** : Employé, mois, ouvrage, validation
- ✅ **Tableau principal** : Liste des plannings avec actions (voir, modifier, valider, supprimer)  
- ✅ **Section détails** : Tableau des détails qui s'affiche après sélection d'un planning
- ✅ **Modals** : Pour création/édition de plannings
- ✅ **JavaScript interactif** : Gestion des filtres, pagination, sélection

### 3. Identifier l'URL cible

Dans `backend/apps/planning/urls.py:8` :
```python
path('', views.planning_dashboard, name='dashboard'),
```

L'URL est donc : `{% url 'planning:dashboard' %}`

### 4. Localiser les menus de navigation

```bash
# Rechercher "Saisie planning" dans les templates
grep -r "Saisie planning" backend/templates/
```

**Fichier trouvé** : `backend/templates/base.html`

Le menu principal contient deux versions (mobile et desktop) :
- **Menu mobile** : ligne 42 (menu collapsible)
- **Menu desktop** : ligne 155 (dropdown hover)

### 5. Modifier les liens du menu

**AVANT** :
```html
<li><a href="{% url 'planning:create' %}"><i class="fas fa-edit mr-2"></i>Saisie planning</a></li>
```

**APRÈS** :
```html
<li><a href="{% url 'planning:dashboard' %}"><i class="fas fa-edit mr-2"></i>Saisie planning</a></li>
```

**Modifications effectuées :**
1. **Menu mobile** (`base.html:42`) : `planning:create` → `planning:dashboard`  
2. **Menu desktop** (`base.html:155`) : `planning:create` → `planning:dashboard`

---

## 📝 Procédure générale pour configurer un menu

### Étape 1 : Identifier la page cible
```bash
# Rechercher par nom de fichier
find . -name "*nom_page*" -type f

# Rechercher par contenu
grep -r "texte_recherché" backend/templates/
```

### Étape 2 : Vérifier l'URL dans urls.py
```python
# Dans le fichier urls.py de l'app concernée
urlpatterns = [
    path('chemin/', views.ma_vue, name='nom_url'),
]
```

### Étape 3 : Localiser les menus
```bash
grep -r "Texte du menu" backend/templates/
```

### Étape 4 : Modifier les liens
```html
<!-- AVANT -->
<a href="{% url 'ancienne:url' %}">Mon Menu</a>

<!-- APRÈS -->
<a href="{% url 'nouvelle:url' %}">Mon Menu</a>
```

### Étape 5 : Vérifier sur mobile et desktop
- Vérifier que les deux versions du menu sont mises à jour
- Tester sur différentes tailles d'écran

---

## 🎯 Structure des URLs du projet

### Planning
- `planning:dashboard` → Page avec tableau et détails interactifs ✅
- `planning:list` → Liste simple des plannings  
- `planning:create` → Formulaire de création simple

### Autres modules
- `core:dashboard` → Tableau de bord principal
- `billing:dashboard` → Facturation  
- `inventory:dashboard` → Stocks/Achats

---

## ⚠️ Points d'attention

### Cohérence des menus
- **Toujours modifier les deux versions** : mobile ET desktop
- **Utiliser les mêmes URLs** dans les deux menus
- **Tester la navigation** après modification

### Nommage des URLs
- Utiliser des noms explicites : `dashboard`, `list`, `create`, `detail`
- Respecter la convention : `app:nom_vue`

### Tests de validation
```bash
# Démarrer le serveur pour tester
cd backend
python manage.py runserver

# Vérifier les menus sur :
# - http://127.0.0.1:8000/ (version desktop)
# - Version mobile (F12 > mode responsive)
```

---

## 📂 Fichiers concernés

### Templates modifiés
- `backend/templates/base.html` : Menus de navigation principaux

### URLs de référence  
- `backend/apps/planning/urls.py` : Définition des URLs planning
- `backend/hydria/urls.py` : Inclusion des URLs des apps

### Pages cibles
- `backend/templates/planning/planning_dashboard.html` : Page avec tableau interactif

---

## 🚀 Résultat final

✅ Le menu "Plannings > Saisie planning" pointe maintenant vers la page avec :
- Formulaire de filtres (employé, mois, ouvrage, validation)
- Tableau des plannings avec actions  
- Section détails qui s'affiche après sélection
- Interface complète de gestion des plannings

L'utilisateur accède directement à l'interface avancée de gestion des plannings au lieu du formulaire simple.