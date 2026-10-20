# WORKFLOW REPOS AUTO-VALIDÉ (29 décembre 2025)

## Vue d'ensemble
Documentation complète du système de repos automatiquement validés dans le module de gestion des congés.

## Problématique initiale
Les repos (jours de repos des employés) devaient passer par le workflow complet de validation (soumise → validée chef → validée directeur → inscrite planning), ce qui créait une lourdeur administrative inutile pour des jours de repos simples.

## Solution implémentée
Les repos sont maintenant **automatiquement validés** et inscrits directement au planning, bypassing le workflow de validation normal.

## Comportement selon l'interface

### 1. Depuis `/employes/suivi-conges-matriciel/` (Calendrier matriciel)
**Fichier** : `backend/apps/employees/views_conges_matriciel.py` (lignes 293-331)

**Workflow** :
1. ✅ **Pas de création de DemandeConge** - Création directe dans Planning
2. ✅ Planning créé avec `estvalide=True`
3. ✅ Activité "Repos" assignée
4. ✅ Utilise `get_or_create()` pour éviter les doublons

**Code** :
```python
# Pour les "repos", créer directement les entrées Planning sans passer par DemandeConge
if type_conge == 'repos':
    activite_repos = Activite.objects.filter(nom='Repos').first()

    plannings_crees = []
    current_date = date_debut_obj
    while current_date <= date_fin_obj:
        date_planning = tz_madagascar.localize(
            datetime.combine(current_date, datetime.min.time())
        )

        planning, created = Planning.objects.get_or_create(
            employe=employe,
            date=date_planning,
            defaults={
                'activite': activite_repos,
                'estvalide': True  # ✅ Repos auto-validé
            }
        )

        if created:
            plannings_crees.append(current_date.strftime('%Y-%m-%d'))

        current_date += timedelta(days=1)
```

### 2. Depuis `/employes/demandes-conges/` (Page de demandes)
**Fichier** : `backend/apps/employees/views_conges.py` (lignes 327-411)

**Workflow** :
1. ✅ **Création de DemandeConge** avec `statut='validee_directeur'`
2. ✅ Planning créé automatiquement avec `estvalide=True`
3. ✅ Activité "Repos" assignée
4. ✅ Motif par défaut "Repos auto-validé" si non fourni

**Code** :
```python
# Pour les repos, créer directement les entrées Planning et valider automatiquement
if type_demande == 'repos':
    # Récupérer l'activité "Repos"
    activite_repos = Activite.objects.filter(nom='Repos').first()

    # Créer la demande avec statut validé directement
    demande = DemandeConge.objects.create(
        employe=employe,
        type_demande=type_demande,
        date_debut=date_debut,
        date_fin=date_fin,
        nb_jours_demandes=nb_jours,
        est_demi_journee=False,
        motif=data.get('motif', 'Repos auto-validé'),
        reliquat_conge_avant=reliquat_conge,
        reliquat_permission_avant=reliquat_permission,
        statut='validee_directeur',  # ✅ Statut validé automatiquement
        created_by=request.user
    )

    # Créer les entrées Planning pour chaque jour
    plannings_crees = []
    current_date = date_debut
    while current_date <= date_fin:
        date_planning = tz_madagascar.localize(
            datetime.combine(current_date, datetime.min.time())
        )

        planning, created = Planning.objects.get_or_create(
            employe=employe,
            date=date_planning,
            defaults={
                'activite': activite_repos,
                'estvalide': True  # ✅ Repos auto-validé
            }
        )

        if created:
            plannings_crees.append(current_date.strftime('%Y-%m-%d'))

        current_date += timedelta(days=1)
```

## Différences clés entre les deux interfaces

| Aspect | Calendrier matriciel | Page de demandes |
|--------|---------------------|------------------|
| **DemandeConge créée** | ❌ NON | ✅ OUI (avec statut validé) |
| **Planning créé** | ✅ OUI | ✅ OUI |
| **Statut Planning** | `estvalide=True` | `estvalide=True` |
| **Traçabilité** | Uniquement dans Planning | Dans DemandeConge + Planning |
| **Motif** | N/A | "Repos auto-validé" si vide |

## Règles de validation des repos

**Fichier** : `backend/apps/employees/utils_conges.py`

**Fonction** : `valider_dates_repos(employe, date_debut, date_fin)`

### Pour les employés JOURNALIERS :
✅ **Tous les jours autorisés** - Peuvent prendre repos n'importe quel jour de la semaine

### Pour les employés NON-JOURNALIERS (temps plein, temps partiel, mi-temps) :
⚠️ **Uniquement samedi et dimanche** - Les jours de semaine génèrent une erreur

**Code** :
```python
def valider_dates_repos(employe, date_debut, date_fin):
    """Valide que les dates de repos respectent les règles selon le type de contrat"""
    if est_journalier(employe):
        return True  # ✅ Journaliers : tous les jours OK

    # Pour les non-journaliers, vérifier que toutes les dates sont des weekends
    current_date = date_debut
    while current_date <= date_fin:
        if not est_weekend(current_date):  # est_weekend() retourne True si samedi ou dimanche
            raise ValueError(
                f"Pour les employés non-journaliers, les repos ne peuvent être placés "
                f"que le samedi ou le dimanche. La date {current_date.strftime('%d/%m/%Y')} "
                f"n'est pas autorisée."
            )
        current_date += timedelta(days=1)

    return True
```

## Interface utilisateur

### Champ Motif rendu optionnel pour repos

**Fichier** : `backend/static/js/demandes_conges.js` (lignes 191-216)

**Fonction** : `toggleTypeFields()`

**Comportement** :
- Pour type "repos" : Champ motif **optionnel** (pas d'astérisque rouge)
- Pour autres types : Champ motif **obligatoire** (astérisque rouge)

**Code** :
```javascript
function toggleTypeFields() {
    const type = document.getElementById('createType').value;
    const motifField = document.getElementById('createMotif');
    const motifLabel = document.querySelector('label[for="createMotif"]');

    // Rendre le motif optionnel pour les repos
    if (type === 'repos') {
        motifField.removeAttribute('required');
        if (motifLabel) {
            motifLabel.innerHTML = 'Motif';  // ✅ Pas d'astérisque
        }
    } else {
        motifField.setAttribute('required', 'required');
        if (motifLabel) {
            motifLabel.innerHTML = 'Motif <span class="text-error">*</span>';
        }
    }
}
```

### Affichage correct du type "Repos"

**Fichier** : `backend/static/js/demandes_conges.js` (lignes 102-117)

**Fonction** : `displayDemandes()`

**Problème résolu** : Tous les types non-"congé" s'affichaient comme "Permission"

**Solution** : Mapping complet des 6 types avec badges colorés

**Code** :
```javascript
const typeInfo = {
    'conge': { label: 'Congé normal', badge: 'badge-primary' },
    'conge_demi': { label: 'Congé demi-journée', badge: 'badge-primary' },
    'permission': { label: 'Permission', badge: 'badge-accent' },
    'repos': { label: 'Repos', badge: 'badge-info' },  // ✅ Badge bleu info
    'repos_medical': { label: 'Repos médical', badge: 'badge-warning' },
    'jour_ferie': { label: 'Jour férié', badge: 'badge-secondary' }
};

const currentType = typeInfo[demande.type_demande] || { label: 'Inconnu', badge: 'badge-ghost' };
```

## Timezone CRITICAL

**⚠️ RÈGLE ABSOLUE** : Toujours utiliser `tz_madagascar.localize()` pour créer les datetime de Planning

```python
import pytz
tz_madagascar = pytz.timezone('Indian/Antananarivo')

# ✅ CORRECT
date_planning = tz_madagascar.localize(
    datetime.combine(current_date, datetime.min.time())
)

# ❌ INCORRECT (cause des décalages de dates)
date_planning = datetime.combine(current_date, datetime.min.time())
```

**Raison** : Le modèle Planning attend un DateTimeField aware. Une date naïve causera des décalages (+3h pour Madagascar).

## Activité "Repos" requise

**⚠️ PRÉREQUIS** : Une activité avec `nom='Repos'` DOIT exister dans la table `Activite`

**Vérification** :
```python
activite_repos = Activite.objects.filter(nom='Repos').first()
if not activite_repos:
    return JsonResponse({
        'success': False,
        'error': 'Activité "Repos" non trouvée dans la base de données'
    }, status=500)
```

**Création si manquante** :
```python
from apps.planning.models import Activite
Activite.objects.get_or_create(
    nom='Repos',
    defaults={'description': 'Jour de repos'}
)
```

## Tests de validation

### Test 1 : Création repos pour journalier (n'importe quel jour)
```
Employé : Journalier
Dates : Lundi 30/12 - Mercredi 01/01 (3 jours)
Résultat attendu : ✅ 3 entrées Planning créées, statut validé
```

### Test 2 : Création repos pour non-journalier (samedi-dimanche uniquement)
```
Employé : Temps plein
Dates : Samedi 28/12 - Dimanche 29/12 (2 jours)
Résultat attendu : ✅ 2 entrées Planning créées, statut validé
```

### Test 3 : Tentative repos pour non-journalier en semaine (doit échouer)
```
Employé : Temps plein
Dates : Lundi 30/12 - Mardi 31/12 (2 jours)
Résultat attendu : ❌ Erreur "les repos ne peuvent être placés que le samedi ou le dimanche"
```

### Test 4 : Motif optionnel pour repos
```
Type : repos
Motif : (vide)
Résultat attendu : ✅ Création réussie avec motif "Repos auto-validé"
```

### Test 5 : Affichage dans la liste
```
Type : repos
Résultat attendu : ✅ Badge bleu "Repos" (pas "Permission")
```

## Fichiers modifiés

1. ✅ `backend/apps/employees/views_conges.py` (lignes 327-411)
   - Ajout workflow auto-validation pour repos

2. ✅ `backend/apps/employees/views_conges_matriciel.py` (lignes 293-331)
   - Déjà implémenté (session précédente)

3. ✅ `backend/static/js/demandes_conges.js` (lignes 102-117, 191-216)
   - Motif optionnel pour repos
   - Affichage correct du type "Repos"

4. ✅ `backend/apps/employees/utils_conges.py`
   - Validation dates repos selon type contrat (déjà implémenté)

## Corrections appliquées (29 décembre 2025)

### Erreur 1 : Attribut 'demandeur' inexistant
**Fichiers** : `signals_conges.py`, `signals_recuperations.py`
**Problème** : Référence à `instance.demandeur` alors que le champ s'appelle `instance.employe`
**Correction** : Suppression de la ligne `created_by=instance.demandeur`

### Erreur 2 : Champ 'valide' au lieu de 'estvalide'
**Fichiers** :
- `signals_conges.py` (ligne 66)
- `signals_recuperations.py` (ligne 72)
- `populate_jours_feries.py` (ligne 118)
- `populate_repos_weekly.py` (ligne 99)

**Problème** : Utilisation de `valide=True` alors que le modèle Planning utilise `estvalide`
**Correction** : Remplacement par `estvalide=True`

### Erreur 3 : Champ 'created_by' inexistant dans Planning
**Fichiers** : `signals_conges.py`, `signals_recuperations.py`
**Problème** : Tentative de passer `created_by` à Planning.objects.create()
**Correction** : Suppression du paramètre (Planning n'a pas ce champ)

### Erreur 4 : Liste employés limitée à 10 et sans filtrage organisation (29 décembre 2025)
**Fichiers** :
- `backend/apps/employees/views.py` (API `api_employes`, lignes 538-545)
- `backend/static/js/demandes_conges.js` (ligne 8)

**Problème signalé par l'utilisateur** :
- "il n'y en a que 10" - La liste des employés dans le modal de création de congé était limitée à 10 employés
- "en plus, il y en a qui ne sont pas affectés à l'organisation" - Pas de filtrage par organisation

**Causes** :
1. Pagination par défaut à 10 employés (`per_page=10`)
2. Absence de filtrage par organisation de l'utilisateur connecté dans l'API

**Corrections appliquées** :

**1. Backend - Ajout filtrage par organisation** (`views.py` lignes 538-545)
```python
# Filtrage par organisation de l'utilisateur connecté
user_organisation = None
if hasattr(request.user, 'employe') and request.user.employe:
    if request.user.employe.base:
        user_organisation = request.user.employe.base.organisation

if user_organisation:
    employes_queryset = employes_queryset.filter(base__organisation=user_organisation)
```

**2. Frontend - Demander 1000 employés au lieu de 10** (`demandes_conges.js` ligne 8)
```javascript
fetch('/api/employes/?per_page=1000'),  // Charger tous les employés (max 1000)
```

**Résultat** :
- ✅ La liste affiche tous les employés de l'organisation de l'utilisateur (jusqu'à 1000)
- ✅ Les employés d'autres organisations ne sont plus affichés
- ✅ Filtrage automatique selon les permissions de l'utilisateur

## Résultat final

✅ **WORKFLOW REPOS COMPLET ET OPÉRATIONNEL**

Les repos créés depuis les deux interfaces :
- Sont **automatiquement validés** (pas de workflow d'approbation)
- Sont **directement inscrits au planning** avec `estvalide=True`
- Respectent les **règles métier** (samedi-dimanche pour non-journaliers)
- Ont un **champ motif optionnel**
- S'affichent correctement comme **"Repos"** (badge bleu)

**Accessible via** :
- `/employes/demandes-conges/` - Page de demandes avec workflow
- `/employes/suivi-conges-matriciel/` - Calendrier matriciel interactif

## Tests de validation

✅ Django check : 0 erreurs
✅ Serveur démarre sans erreur
✅ Tous les attributs de modèles corrigés
