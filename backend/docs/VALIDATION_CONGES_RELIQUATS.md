# Validation des Congés et Recalcul des Reliquats

## Date de réalisation
8 décembre 2025

## Contexte

Après la migration des congés depuis Planning vers DemandeConge, il restait deux actions à effectuer :
1. **Valider les congés passés** (dates de validation manquantes)
2. **Recalculer les reliquats** pour tous les employés

## Scripts créés

### 1. Script de validation : `valider_conges_passes.py`

**Emplacement :** `backend/apps/employees/management/commands/valider_conges_passes.py`

**Fonctionnalités :**
- Valide automatiquement les congés dont `date_fin < aujourd'hui`
- Renseigne les dates de validation (chef, directeur, inscription planning)
- Recalcule les soldes de congés mois par mois pour chaque employé
- Crée les entrées dans la table `SoldeConge` (12 mois par employé par année)

**Utilisation :**

```bash
# Mode simulation (voir ce qui serait fait)
python manage.py valider_conges_passes --dry-run

# Mode réel (appliquer les changements)
python manage.py valider_conges_passes

# Pour un employé spécifique
python manage.py valider_conges_passes --employe "CHRISTIAN"

# Pour une année spécifique
python manage.py valider_conges_passes --annee 2025
```

## Résultats de l'exécution (8 décembre 2025)

### Statistiques globales

- **220 congés validés** (dates de validation renseignées)
- **396 soldes recalculés** (33 mois × 12 employés environ)
- **32 employés** avec soldes calculés

### Calcul des soldes

**Formule :**
```
Solde fin mois = Solde début mois + Acquisition (2.5j) - Consommation (congés pris)
```

**Acquisition automatique :**
- **2.5 jours par mois** travaillé
- **30 jours par an** (2.5 × 12)

**Permissions :**
- **10 jours par an** (réinitialisés chaque janvier)

### Situation des soldes (Décembre 2025)

#### Employés en déficit (ont pris plus que leur droit)

| Employé | Solde | Détails |
|---------|-------|---------|
| CHRISTIAN | -9 jours | 30 jours acquis - 39 jours pris |
| PEROLIN | -4 jours | 30 jours acquis - 34 jours pris |
| ALAIN | -3 jours | 30 jours acquis - 33 jours pris |

#### Employés avec le plus de solde

| Employé | Solde |
|---------|-------|
| ROGER | 29 jours |
| NOELA | 28 jours |
| SANDRO | 28 jours |
| MARIO | 27 jours |
| SYRESSI | 20 jours |
| FIFALIANA | 12 jours |

#### Nouveaux employés (1 mois d'ancienneté)

Solde : **2.5 jours** (1 mois × 2.5)
- HERIZO, RHOMER, RENE, MARIE JEANNE, RAOUL, BENEDICTINE, LANJA, GINOT, VELONASY, FLEURICE, HAJA, VICTORIEN FRF, ANGELYS, FELIX, CHÈQUE

## Modifications de l'API

### Fichier : `apps/employees/views_conges.py`

**Fonction modifiée :** `api_demandes_conges_list()`

**Ajouts :**
- Calcul des soldes actuels par employé (une seule fois par employé)
- Nouveaux champs dans la réponse JSON :
  - `reliquat_conge_actuel` : Solde de congés actuel (depuis SoldeConge)
  - `reliquat_permission_actuel` : Solde de permissions actuel (calculé)

**Code ajouté :**
```python
# Calculer les soldes actuels une seule fois par employé
soldes_employes = {}

for demande in queryset_demandes:
    employe_id = str(demande.employe.id)

    # Calculer le solde actuel si pas déjà fait pour cet employé
    if employe_id not in soldes_employes:
        soldes_employes[employe_id] = {
            'conges': float(calculer_solde_conge_actuel(demande.employe)),
            'permissions': calculer_solde_permission_actuel(demande.employe)
        }

    # Ajouter les soldes actuels dans la réponse
    'reliquat_conge_actuel': soldes_employes[employe_id]['conges'],
    'reliquat_permission_actuel': soldes_employes[employe_id]['permissions'],
```

## Modifications du Frontend

### Fichier : `static/js/demandes_conges.js`

**Ligne modifiée :** Ligne 111

**Avant :**
```javascript
<td class="text-sm">Congés: ${demande.reliquat_conge_avant}<br>Permissions: ${demande.reliquat_permission_avant}</td>
```

**Après :**
```javascript
<td class="text-sm">Congés: ${demande.reliquat_conge_actuel || 0}<br>Permissions: ${demande.reliquat_permission_actuel || 0}</td>
```

**Changement :** Affichage des **soldes actuels** au lieu des soldes **avant la demande**

### Fichier : `templates/employees/demandes_conges_list.html`

**Version JS incrémentée :** `?v=6` → `?v=7` (force le rechargement du cache navigateur)

## Exemple de calcul : CHRISTIAN

### Données

- **Année :** 2025
- **Solde début année :** 0 jours (aucun report)
- **Acquisition :** 2.5 jours/mois × 12 = **30 jours**
- **Congés pris :** **39 jours** (18 demandes)

### Détail des congés

| Date début | Date fin | Jours | Mois |
|------------|----------|-------|------|
| 2025-01-02 | 2025-01-03 | 2 | Janvier |
| 2025-01-06 | 2025-01-10 | 5 | Janvier |
| 2025-01-13 | 2025-01-13 | 1 | Janvier |
| 2025-01-16 | 2025-01-17 | 2 | Janvier |
| 2025-01-20 | 2025-01-24 | 5 | Janvier |
| ... | ... | ... | ... |
| **Total** | | **39 jours** | |

### Calcul du solde

```
Solde final = 0 (début) + 30 (acquis) - 39 (pris) = -9 jours
```

### Soldes mensuels (extraits)

| Mois | Début | Acquisition | Consommation | Fin |
|------|-------|-------------|--------------|-----|
| Janvier | 0.00 | 2.50 | 15.00 | -12.50 |
| Février | -12.50 | 2.50 | 1.00 | -11.00 |
| Mars | -11.00 | 2.50 | 3.00 | -11.50 |
| Avril | -11.50 | 2.50 | 4.00 | -13.00 |
| ... | ... | ... | ... | ... |
| Décembre | -11.50 | 2.50 | 0.00 | **-9.00** |

## Vérification de la page /demandes-conges/

Après ces modifications, la page `/demandes-conges/` affiche maintenant :

✅ **Reliquats actuels corrects** dans la colonne "Congés/Permissions"
✅ **Données cohérentes** avec la table `SoldeConge`
✅ **Calcul dynamique** : solde mis à jour à chaque chargement
✅ **Performance optimisée** : calcul une seule fois par employé

### Exemple d'affichage

| Employé | Type | Période | Jours | Statut | **Congés/Permissions** |
|---------|------|---------|-------|--------|----------------------|
| ALAIN | Congé | 24/11/2025 → 24/11/2025 | 1 | Congé | **Congés: -3<br>Permissions: 10** |
| PEROLIN | Congé | 20/11/2025 → 21/11/2025 | 2 | Congé | **Congés: -4<br>Permissions: 10** |
| FIFALIANA | Congé | 26/12/2025 → 26/12/2025 | 1 | Congé | **Congés: 12<br>Permissions: 10** |

## Résumé des fichiers modifiés/créés

**Créés :**
1. `apps/employees/management/commands/valider_conges_passes.py` - Script de validation
2. `docs/VALIDATION_CONGES_RELIQUATS.md` - Documentation (ce fichier)

**Modifiés :**
1. `apps/employees/views_conges.py` (lignes 186-216) - API avec soldes actuels
2. `static/js/demandes_conges.js` (ligne 111) - Affichage soldes actuels
3. `templates/employees/demandes_conges_list.html` (ligne 258) - Version JS v7

## Commandes utiles

### Vérifier les soldes d'un employé

```python
from apps.employees.models import Employe
from apps.employees.models_conges import SoldeConge

employe = Employe.objects.get(surnom='CHRISTIAN')

# Soldes de l'année 2025
soldes = SoldeConge.objects.filter(employe=employe, annee=2025).order_by('mois')
for solde in soldes:
    print(f"Mois {solde.mois:02d}: {solde.solde_conges_fin:.2f} jours")
```

### Lister les employés en déficit

```python
from apps.employees.models_conges import SoldeConge

# Dernier solde de chaque employé
soldes_dec = SoldeConge.objects.filter(annee=2025, mois=12, solde_conges_fin__lt=0)

for solde in soldes_dec.order_by('solde_conges_fin'):
    print(f"{solde.employe.surnom}: {solde.solde_conges_fin:.2f} jours")
```

### Relancer le recalcul pour un employé

```bash
python manage.py valider_conges_passes --employe "CHRISTIAN"
```

## Prochaines étapes possibles

1. **Dashboard des soldes** : Page dédiée avec graphiques et filtres
2. **Alertes automatiques** : Email quand un employé est en déficit
3. **Export Excel** : Liste des soldes de tous les employés
4. **Historique détaillé** : Voir l'évolution mois par mois
5. **Validation des déficits** : Workflow pour régulariser les soldes négatifs

---

**Migration et validation des congés terminées avec succès ✓**
