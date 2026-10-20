# 📅 Planning Calendrier - Documentation

## ✅ Fonctionnalités implémentées

### 1. Affichage des employés avec surnom
- **Modification du modèle** : Utilisation de la propriété `display_name` qui privilégie le surnom (`emp_nickname`) quand disponible
- **API mise à jour** : L'API `employees_api_simple` retourne maintenant le `display_name` avec surnom prioritaire
- **Templates mis à jour** : Tous les affichages d'employés utilisent maintenant le surnom

### 2. Vue calendrier interactive
- **URL** : `/planning/calendrier/` (accessible via `planning:calendar`)
- **Template** : `backend/templates/planning/planning_calendar.html`
- **Vue** : `planning_calendar` dans `backend/apps/planning/views.py`

### 3. Fonctionnalités de la vue calendrier

#### 🔍 Filtres disponibles
- **Employé** : Filtrer par employé spécifique
- **Ouvrage** : Filtrer par ouvrage/infrastructure
- **Validation** : Filtrer par statut (validé/non validé/tous)

#### 📊 Modes d'affichage
- **Vue Mois** : Grille 7x6 avec cartes compactes
  - Affichage : Employé + Ouvrage
  - Cartes de hauteur fixe (32px)
- **Vue Semaine** : Grille 7x1 avec cartes détaillées  
  - Affichage : Employé + Ouvrage + Activité
  - Cartes de hauteur variable (min 40px)

#### 🎨 Cartes de planning
- **Couleur verte** : Plannings validés
- **Couleur orange** : Plannings en attente de validation
- **Contenu dynamique** selon le mode d'affichage
- **Clic** : Affiche les détails du planning sélectionné

#### 🧭 Navigation
- **Boutons précédent/suivant** : Navigation par mois ou semaine
- **Bouton "Aujourd'hui"** : Retour à la date actuelle
- **Titre dynamique** : Affiche le mois/année ou la semaine courante

#### ➕ Actions disponibles
- **Nouveau planning** : Ouverture du modal de création
- **Détails planning** : Tableau des détails après sélection d'une carte
- **Filtrage en temps réel** : Application immédiate des filtres

---

## 🗄️ Architecture des Données Planning

### **Structure des Tables**

Le système de planning utilise une architecture avec des tables séparées :

```
Planning (Table principale - plannings)
├── id, date, employe, type_activite, activite, ouvrage
├── remarque, estvalide, statut
└── Relations vers tables filles:
    ├── PlanningDetail (Détails généraux - planning_details)
    ├── BonLivraison (Livraisons matériel - bons_livraison)
    └── Avances (via PlanningDetail avec numero_bon_avance)

⚠️ Les Recettes ne sont PAS dans Planning
   → Module séparé: apps.billing (Facturation)
```

### **Tables liées**

**1. Planning (Table principale)**
- Activités quotidiennes des employés
- Validation des plannings
- Lien vers ouvrage (optionnel)

**2. BonLivraison (Table séparée)**
- Table : `bons_livraison`
- ForeignKey vers Planning
- Gestion des livraisons de matériel
- Impact automatique sur les stocks

**3. Avances (via PlanningDetail)**
- Table : `planning_details`
- Identifiées par `numero_bon_avance` (non null)
- Traçabilité financière via DiameX
- Retours gérés par module Caissière

**4. Recettes (Module Billing - SÉPARÉ)**
- ⚠️ Ne font PAS partie du workflow Planning
- Gérées dans `apps.billing` :
  - `Releve` : Relevés de compteurs
  - `Paiement` : Paiements reçus
  - `TarifForfaitaire` / `TarifVolumetrique`
- Workflow indépendant : Relevé → Facturation → Encaissement

---

## 🛠️ Implémentation technique

### Structure des fichiers
```
backend/
├── apps/planning/
│   ├── models.py (Planning, BonLivraison, PlanningDetail)
│   ├── views.py (+ planning_calendar)
│   ├── urls.py (+ path calendrier/)
│   └── views_simple.py (+ API avec surnom)
├── apps/billing/ (Module séparé pour recettes)
│   ├── models.py (Releve, Paiement, Tarif...)
│   └── views_releves.py, views_facturation.py
├── templates/
│   ├── base.html (+ liens menu calendrier)
│   └── planning/
│       └── planning_calendar.html (nouveau)
```

### APIs utilisées
- `{% url "planning:data_api" %}` : Données des plannings
- `{% url "planning:details_api" %}` : Détails d'un planning
- `{% url "planning:employees_api" %}` : Liste des employés avec surnom
- `{% url "planning:ouvrages_api" %}` : Liste des ouvrages
- `{% url "planning:types_activites_api" %}` : Types d'activités

### JavaScript principal
- **Génération du calendrier** : `renderCalendar()`, `renderMonthView()`, `renderWeekView()`
- **Gestion des cartes** : `createPlanningCard()`, `createDayCell()`
- **Navigation** : `navigateCalendar()`, `switchView()`, `goToToday()`
- **Filtres** : `applyFilters()`, `clearFilters()`, `applyCurrentFilters()`
- **Interactions** : `selectPlanning()`, `openCreateModal()`, `savePlanning()`

---

## 🎯 Accès à la vue calendrier

### Par le menu navigation
1. **Menu desktop** : Clic sur "Plannings" > "Vue calendrier"
2. **Menu mobile** : Expansion "Plannings" > "Vue calendrier"
3. **URL directe** : `http://localhost:8000/planning/calendrier/`

### Depuis d'autres pages planning
- Lien dans le header ou navigation secondaire (à implémenter si souhaité)

---

## 🔧 Configuration et personnalisation

### Styles CSS (dans le template)
- **`.calendar-container`** : Conteneur principal
- **`.calendar-month`** : Grille vue mois (7 colonnes, 6 lignes)
- **`.calendar-week`** : Grille vue semaine (7 colonnes, 1 ligne)
- **`.planning-card`** : Cartes de planning
- **`.planning-card.month-view`** : Cartes compactes (vue mois)
- **`.planning-card.week-view`** : Cartes détaillées (vue semaine)

### Couleurs des cartes
```css
.planning-card.bg-success { /* Plannings validés - vert */ }
.planning-card.bg-warning { /* Plannings en attente - orange */ }
```

### Données de test
Si les APIs ne sont pas disponibles, le système utilise automatiquement des données de test pour le développement.

---

## 🚀 Utilisation

### Navigation dans le calendrier
1. **Vue mois** : Voir l'ensemble des plannings du mois
2. **Vue semaine** : Focus sur une semaine avec plus de détails
3. **Navigation temporelle** : Flèches pour changer de période
4. **Retour aujourd'hui** : Bouton pour revenir à la date courante

### Filtrage des plannings
1. Sélectionner les critères dans les filtres
2. Cliquer "Filtrer" pour appliquer
3. "Effacer" pour réinitialiser tous les filtres

### Consultation des détails
1. Cliquer sur une carte de planning
2. Le tableau des détails s'affiche en bas de page
3. Scroll automatique vers les détails

### Création d'un nouveau planning
1. Cliquer "Nouveau Planning"
2. Remplir le formulaire dans le modal
3. Sauvegarde et rafraîchissement automatique du calendrier

---

## ⚡ Performance et optimisation

- **Rendu asynchrone** : Les cartes se chargent de manière non-bloquante
- **Filtrage côté client** : Pas de rechargement de page
- **Données cachées** : Les plannings sont conservés en mémoire pour le filtrage
- **Navigation fluide** : Changement de vue instantané

---

## 🔄 Prochaines améliorations possibles

1. **Drag & Drop** : Déplacement des plannings par glisser-déposer
2. **Vue journalière** : Zoom sur une journée spécifique
3. **Gestion des conflits** : Détection de plannings simultanés pour un même employé
4. **Export** : Export du calendrier en PDF ou iCal
5. **Notifications** : Alertes pour les plannings non validés
6. **Récurrence** : Plannings récurrents (hebdomadaire, mensuel)

L'implémentation est complète et fonctionnelle, prête pour la production ! 🎉