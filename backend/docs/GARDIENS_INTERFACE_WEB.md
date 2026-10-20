# Interface Web de Gestion des Gardiens - Documentation

## 📋 Vue d'ensemble

Interface web complète pour la gestion des rotations et des congés spéciaux des gardiens, avec calcul automatique des heures supplémentaires.

### Fonctionnalités implémentées
1. **Visualisation des rotations** : Tableau avec filtres par gardien et dates
2. **Génération rotations** : Création automatique du pattern Jour → Nuit → Congé
3. **Gestion des congés** : Création de congés avec extension automatique des shifts
4. **Suivi heures supplémentaires** : Calcul et affichage détaillé par type

---

## 🎯 Accès à l'interface

### URL
```
http://localhost:8000/employes/gardiens/
```

### Navigation
**Menu mobile et desktop** :
- Plannings → Suivi & Contrôle → **Gestion des Gardiens** (icône bouclier bleu)

**Position dans le menu** :
- Après "Réparations & Réhabilitations"
- Avant "Positions GPS Employés"

---

## 🔧 Architecture technique

### Fichiers créés/modifiés

**1. Template** : `backend/templates/planning/gestion_gardiens.html` (~600 lignes)
- Interface à deux onglets (Rotations / Heures Supplémentaires)
- Modals pour génération rotations et création congés
- Tableaux avec badges et filtres
- JavaScript pour appels API et gestion UI

**2. Vue** : `backend/apps/employees/views_gardiens.py` (fonction `gestion_gardiens()`)
```python
def gestion_gardiens(request):
    """Page web de gestion des gardiens"""
    context = {
        'gardiens': [
            {'id': '64a11eeb-0dfc-4d6b-92ea-73175edc3642', 'nom': 'RAOUL'},
            {'id': 'cde49c47-0e00-4ba1-8631-a0b0ed150849', 'nom': 'RENE'},
            {'id': 'b866a66c-93fb-42b4-81ef-08caaa25c272', 'nom': 'VELONASY'},
        ]
    }
    return render(request, 'planning/gestion_gardiens.html', context)
```

**3. URL** : `backend/apps/employees/urls.py` (ligne 259)
```python
path('gardiens/', views_gardiens.gestion_gardiens, name='gestion_gardiens'),
```

**4. Menu** : `backend/templates/base.html` (lignes 238, 584)
- Menu mobile : ligne 238
- Menu desktop : ligne 584

---

## 📊 Interface utilisateur

### Onglet 1 : Rotations

#### Filtres
- **Gardien** : Dropdown avec les 3 gardiens (Tous / RAOUL / RENE / VELONASY)
- **Date début** : Input date
- **Date fin** : Input date
- Bouton **Filtrer** pour appliquer les filtres

#### Actions
- **Générer Rotations** : Ouvre modal pour créer rotations standard
- **Créer Congé** : Ouvre modal pour créer un congé avec extension automatique

#### Tableau des rotations
Colonnes :
- Date (format DD/MM/YYYY)
- Gardien (nom)
- Type de shift (Jour / Nuit / Congé / Étendu)
- Heures (format "HH:MM - HH:MM")
- Heures travaillées (ex: 10.0h)
- Badges spéciaux :
  - 🔴 **Dimanche** (badge rouge)
  - 🟡 **Jour férié** (badge jaune)
  - 🔵 **Extension** (badge bleu, indique remplacement)

### Onglet 2 : Heures Supplémentaires

#### Filtres
- **Gardien** : Dropdown avec les 3 gardiens
- **Mois** : 1-12
- **Année** : Input number

#### Cartes statistiques (4 cartes)
1. **Heures normales** : Total heures dans la limite mensuelle
2. **Heures supplémentaires** : Total au-delà de la limite
3. **Heures dimanche** : Total travaillées les dimanches
4. **Heures jours fériés** : Total travaillées les jours fériés

#### Tableau détaillé
Affiche la répartition complète des heures par type avec icônes et couleurs.

---

## 🔄 Workflows

### 1. Générer rotations standard

**Étapes** :
1. Clic sur bouton **"Générer Rotations"**
2. Modal s'ouvre avec formulaire :
   - Date de début (obligatoire)
   - Nombre de jours (par défaut : 30, max : 90)
3. Clic **"Générer"**
4. API POST `/api/gardiens/generer-rotations/`
5. Création automatique du pattern : Jour → Nuit → Congé (répète tous les 3 jours)
6. Message de confirmation avec nombre de rotations créées
7. Rechargement automatique du tableau

**API appelée** :
```javascript
POST /api/gardiens/generer-rotations/
Body: {
    "date_debut": "2025-12-30",
    "nb_jours": 30
}
```

### 2. Créer un congé avec extension automatique

**Étapes** :
1. Clic sur bouton **"Créer Congé"**
2. Modal s'ouvre avec :
   - ⚠️ **Alerte** : "Les 2 autres gardiens auront automatiquement des shifts étendus (8h-8h)"
   - Sélection gardien (dropdown)
   - Date début (obligatoire)
   - Date fin (obligatoire)
   - Motif (textarea, obligatoire)
3. Clic **"Créer"**
4. API POST `/api/gardiens/creer-conge/`
5. Système :
   - Supprime les rotations du gardien en congé
   - Crée entrées Planning avec activité "Congé"
   - Étend automatiquement les shifts des 2 autres gardiens (8h-8h = 24h)
   - Marque les shifts comme extensions (`est_extension=True`)
6. Message de confirmation avec détails
7. Rechargement du tableau

**API appelée** :
```javascript
POST /api/gardiens/creer-conge/
Body: {
    "employe_id": "uuid",
    "date_debut": "2025-12-30",
    "date_fin": "2026-01-02",
    "motif": "Congé annuel"
}
```

### 3. Consulter heures supplémentaires

**Étapes** :
1. Cliquer sur onglet **"Heures Supplémentaires"**
2. Sélectionner gardien, mois, année
3. Clic **"Charger"**
4. API GET `/api/gardiens/heures-supplementaires/`
5. Affichage :
   - 4 cartes statistiques avec totaux
   - Tableau détaillé avec répartition
6. Données mises à jour en temps réel

**API appelée** :
```javascript
GET /api/gardiens/heures-supplementaires/?employe_id=uuid&mois=12&annee=2025
```

---

## 🎨 Design et composants

### Badges de shift
- **Jour** : Badge bleu (`badge-info`)
- **Nuit** : Badge violet (`badge-secondary`)
- **Congé** : Badge jaune (`badge-warning`)
- **Étendu** : Badge vert (`badge-success`)

### Badges spéciaux
- **Dimanche** : Badge rouge (`badge-error`) avec icône calendrier
- **Jour férié** : Badge jaune (`badge-warning`) avec icône calendrier-étoile
- **Extension** : Badge bleu (`badge-info`) avec icône échange

### Cartes statistiques
- Layout : Grille 4 colonnes sur desktop, 2 colonnes sur mobile
- Icônes : Clock, plus-circle, calendar-day, calendar-star
- Couleurs DaisyUI : info, success, warning, error

---

## 📡 APIs REST utilisées

### 1. Générer rotations
```
POST /api/gardiens/generer-rotations/
Content-Type: application/json

Request:
{
    "date_debut": "2025-12-30",
    "nb_jours": 30
}

Response:
{
    "success": true,
    "message": "30 rotation(s) créée(s)",
    "rotations_creees": ["2025-12-30", "2025-12-31", ...],
    "total_genere": 90
}
```

### 2. Créer congé
```
POST /api/gardiens/creer-conge/
Content-Type: application/json

Request:
{
    "employe_id": "uuid",
    "date_debut": "2025-12-30",
    "date_fin": "2026-01-02",
    "motif": "Congé annuel"
}

Response:
{
    "success": true,
    "message": "Congé créé pour 4 jour(s). 8 shift(s) étendu(s).",
    "jours_traites": ["2025-12-30", "2025-12-31", ...],
    "shifts_etendus": [...]
}
```

### 3. Lister rotations
```
GET /api/gardiens/rotations/?employe_id=uuid&date_debut=2025-12-01&date_fin=2025-12-31

Response:
{
    "success": true,
    "rotations": [
        {
            "id": "uuid",
            "employe_id": "uuid",
            "employe_nom": "RAOUL",
            "date": "2025-12-30",
            "shift_type": "jour",
            "shift_type_display": "Jour (8h-18h)",
            "heure_debut": "08:00",
            "heure_fin": "18:00",
            "heures_travaillees": 10.0,
            "est_dimanche": false,
            "est_jour_ferie": false,
            "est_extension": false,
            "remplace_employe_nom": null
        }
    ],
    "count": 30
}
```

### 4. Heures supplémentaires
```
GET /api/gardiens/heures-supplementaires/?employe_id=uuid&mois=12&annee=2025

Response:
{
    "success": true,
    "heures_supplementaires": {
        "employe_id": "uuid",
        "employe_nom": "RAOUL",
        "mois": 12,
        "annee": 2025,
        "heures_normales": 200.0,
        "heures_supplementaires": 43.0,
        "heures_dimanche": 14.0,
        "heures_jours_feries": 10.0,
        "heures_extensions": 24.0
    }
}
```

---

## 🔒 Sécurité

### CSRF Protection
Toutes les requêtes POST incluent le token CSRF via :
```javascript
headers: {
    'X-CSRFToken': getCookie('csrftoken')
}
```

### Fonction helper
```javascript
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
```

---

## ✅ Tests de validation

### Checklist
- [x] Page accessible via URL directe
- [x] Menu mobile affiche le lien avec icône
- [x] Menu desktop affiche le lien avec icône
- [x] Onglets Rotations/Heures fonctionnent
- [x] Filtres de rotations fonctionnent
- [x] Bouton "Générer Rotations" ouvre modal
- [x] Formulaire génération envoie requête API
- [x] Bouton "Créer Congé" ouvre modal
- [x] Formulaire congé envoie requête API
- [x] Tableau rotations se charge au démarrage
- [x] Badges s'affichent correctement
- [x] Filtres heures supplémentaires fonctionnent
- [x] Cartes statistiques se mettent à jour
- [x] Django check : 0 erreurs

---

## 🚀 Utilisation en production

### Prérequis
- Django serveur en cours d'exécution
- Base de données PostgreSQL configurée
- Les 3 gardiens créés avec leurs UUIDs

### Démarrage
```bash
cd backend
python manage.py runserver
```

### Accès
1. Ouvrir navigateur : http://localhost:8000
2. Se connecter avec compte admin/employé
3. Menu Plannings → Suivi & Contrôle → Gestion des Gardiens

---

## 📝 Notes importantes

### IDs des gardiens (hardcodés)
```python
GARDIENS_IDS = [
    '64a11eeb-0dfc-4d6b-92ea-73175edc3642',  # RAOUL
    'cde49c47-0e00-4ba1-8631-a0b0ed150849',  # RENE
    'b866a66c-93fb-42b4-81ef-08caaa25c272',  # VELONASY
]
```

### Pattern de rotation
- **Jour** : 8h-18h (10 heures)
- **Nuit** : 18h-8h lendemain (14 heures)
- **Congé** : Pas de shift
- **Répétition** : Cycle de 3 jours (Jour → Nuit → Congé)

### Calcul heures supplémentaires
- **Limite mensuelle** : 243 heures (variable)
- **Heures normales** : Jusqu'à la limite
- **Heures supplémentaires** : Au-delà de la limite
- **Majoration dimanche** : Comptabilisées séparément
- **Majoration jours fériés** : Comptabilisées séparément
- **Extensions** : Shifts de 24h pour remplacement

---

## 🔄 Améliorations futures possibles

1. **Export Excel** : Générer fichier Excel des rotations
2. **Calendrier visuel** : Vue calendrier avec drag & drop
3. **Notifications** : Alerter les gardiens de leurs shifts
4. **Historique** : Suivi des modifications de rotations
5. **Validation** : Workflow de validation des congés
6. **Import** : Import massif de rotations depuis Excel
7. **Statistiques** : Dashboard avec graphiques d'analyse

---

✅ **Interface web de gestion des gardiens complète et opérationnelle**

**Accessible via** : Plannings > Suivi & Contrôle > Gestion des Gardiens
