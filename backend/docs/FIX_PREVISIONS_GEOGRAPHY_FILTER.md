# Correction Prévisions Budgétaires - Géographie et Filtres

**Date :** 10 décembre 2025
**Contexte :** Correction de deux bugs dans le système de prévisions budgétaires

## 🐛 Problèmes identifiés

### 1. Assignation géographique erronée des salaires et charges sociales

**Symptôme** : Les dépenses de type Salaires, IRSA, CNAPS, FMFP et Mutuelle étaient assignées à "District Fénérive Commune Ambahoaka" au lieu d'être sans district/commune.

**Cause** : Les fonctions `calculer_previsions_salaires()`, `calculer_previsions_irsa()` et `calculer_previsions_charges_sociales()` utilisaient une logique d'assignation géographique basée sur `employe.organisation`, qui n'a pas de sens pour ces types de dépenses.

**Impact** :
- Les salaires apparaissaient incorrectement dans les filtres géographiques
- Les rapports par district/commune incluaient des dépenses RH qui ne sont pas localisées
- Confusion dans l'analyse budgétaire par zone géographique

### 2. Filtre Type incomplet

**Symptôme** : Le filtre "Type" dans la page des prévisions (`/facturation/previsions/`) ne contenait pas les nouveaux types de prévisions.

**Types manquants** :
- Dépense Salaires (depense_salaires)
- Dépense IRSA (depense_irsa)
- Dépense CNAPS (depense_cnaps)
- Dépense FMFP (depense_fmfp)
- Dépense Mutuelle Santé (depense_mutuelle)

**Impact** :
- Impossible de filtrer uniquement les prévisions de salaires/charges sociales
- Perte de visibilité sur ces types de dépenses

## ✅ Corrections appliquées

### 1. Suppression de l'assignation géographique pour salaires/charges

**Fichier modifié** : `backend/apps/billing/services_previsions.py`

**Changements :**

#### Fonction `calculer_previsions_salaires()` (lignes 1086-1110)

**AVANT :**
```python
district_obj = None
commune_obj = None
ouvrage_obj = None

if hasattr(employe, 'organisation') and employe.organisation:
    from apps.billing.models import ModaliteGestion, PointEau

    modalite = ModaliteGestion.objects.filter(
        gestionnaire=employe.organisation,
        date_fin__isnull=True
    ).select_related('ouvrage').first()

    if modalite and modalite.ouvrage:
        ouvrage_obj = modalite.ouvrage
        point_eau = PointEau.objects.filter(ouvrage=ouvrage_obj).select_related(
            'parcelle__village__fokontany__commune__district'
        ).first()

        if point_eau and point_eau.parcelle:
            # ... assignation district/commune
```

**APRÈS :**
```python
# Les salaires ne sont PAS des dépenses géographiques
# Ils doivent rester SANS district/commune (NULL)
district_obj = None
commune_obj = None
ouvrage_obj = None
```

#### Fonction `calculer_previsions_irsa()` (lignes 1186-1210)

**Même correction appliquée** : Suppression du bloc `if hasattr(employe, 'organisation')...`

#### Fonction `calculer_previsions_charges_sociales()` (lignes 1266-1287, 1597-1618)

**Même correction appliquée** : Suppression du bloc d'assignation géographique (2 occurrences)

**Résultat :**
- `district=NULL`
- `commune=NULL`
- `ouvrage=NULL`

Pour toutes les prévisions de type :
- `depense_salaires`
- `depense_irsa`
- `depense_cnaps`
- `depense_fmfp`
- `depense_mutuelle`

### 2. Ajout des nouveaux types au filtre

**Fichier modifié** : `backend/templates/billing/previsions_budget.html` (lignes 85-107)

**AVANT :**
```html
<select id="filter-type" class="select select-bordered select-sm">
    <option value="all">Tous les types</option>
    <option value="recette_forfaitaire">Recettes forfaitaires</option>
    <option value="recette_volumetrique">Recettes volumétriques</option>
    <option value="recette_nouveaux_pe">Recettes nouveaux PE</option>
    <option value="depense_indemnites">Dépenses indemnités</option>
    <option value="depense_salaire">Dépenses salaires</option>
    <option value="depense_autre">Autres dépenses</option>
</select>
```

**APRÈS :**
```html
<select id="filter-type" class="select select-bordered select-sm">
    <option value="all">Tous les types</option>
    <optgroup label="Recettes">
        <option value="recette_forfaitaire">Recettes forfaitaires</option>
        <option value="recette_volumetrique">Recettes volumétriques</option>
        <option value="recette_nouveau_pe">Recettes nouveaux PE</option>
    </optgroup>
    <optgroup label="Dépenses">
        <option value="depense_bon_livraison">Bons de livraison</option>
        <option value="depense_avance">Avances</option>
        <option value="depense_indemnites">Indemnités</option>
        <option value="depense_salaires">Salaires</option>
        <option value="depense_irsa">IRSA</option>
        <option value="depense_cnaps">CNAPS</option>
        <option value="depense_fmfp">FMFP</option>
        <option value="depense_mutuelle">Mutuelle Santé</option>
        <option value="depense_autre">Autres dépenses</option>
    </optgroup>
</select>
```

**Améliorations :**
- Groupement visuel Recettes/Dépenses avec `<optgroup>`
- Tous les types de prévisions disponibles
- Correction du nom exact (ex: `recette_nouveau_pe` au lieu de `recette_nouveaux_pe`)

## 📊 Tests et validation

### Test 1 : Vérification géographie Salaires

```python
from apps.billing.models_previsions import PrevisionBudget

salaires = PrevisionBudget.objects.filter(type_prevision='depense_salaires').first()
print(f'District: {salaires.district}')  # None ✅
print(f'Commune: {salaires.commune}')    # None ✅
print(f'Ouvrage: {salaires.ouvrage}')    # None ✅
```

### Test 2 : Vérification géographie IRSA

```python
irsa = PrevisionBudget.objects.filter(type_prevision='depense_irsa').first()
print(f'District: {irsa.district}')  # None ✅
print(f'Commune: {irsa.commune}')    # None ✅
```

### Test 3 : Vérification géographie CNAPS/FMFP/Mutuelle

```python
cnaps = PrevisionBudget.objects.filter(type_prevision='depense_cnaps').first()
print(f'District: {cnaps.district}')  # None ✅
print(f'Commune: {cnaps.commune}')    # None ✅

fmfp = PrevisionBudget.objects.filter(type_prevision='depense_fmfp').first()
print(f'District: {fmfp.district}')  # None ✅

mutuelle = PrevisionBudget.objects.filter(type_prevision='depense_mutuelle').first()
print(f'District: {mutuelle.district}')  # None ✅
```

### Test 4 : Recalcul complet

```python
from apps.billing.services_previsions import recalculer_previsions_annee

result = recalculer_previsions_annee(2025)
print(f'Lignes créées: {result["creees"]}')  # 15,152 ✅
```

**Répartition par type (après correction) :**
```
- recette_forfaitaire: 2,388
- recette_volumetrique: 6,180
- recette_nouveaux_pe: 12
- depense_bon_livraison: 2,711
- depense_avance: 2,400
- depense_indemnites: 420
- depense_salaires: 324 ✅
- depense_irsa: 324 ✅
- depense_cnaps: 131 ✅
- depense_fmfp: 131 ✅
- depense_mutuelle: 131 ✅
```

## 📝 Fichiers modifiés

1. **`backend/apps/billing/services_previsions.py`**
   - Fonction `calculer_previsions_salaires()` : Suppression assignation géographique
   - Fonction `calculer_previsions_irsa()` : Suppression assignation géographique
   - Fonction `calculer_previsions_charges_sociales()` : Suppression assignation géographique (2 occurrences)

2. **`backend/templates/billing/previsions_budget.html`**
   - Filtre Type : Ajout de tous les types manquants avec groupement

3. **`backend/apps/billing/fix_geographic_assignments.py`** (script de correction)
   - Script Python pour automatiser la suppression des blocs d'assignation géographique

## ⚠️ Points d'attention

### 1. Les dépenses RH ne sont PAS géographiques

**Dépenses SANS géographie (district=NULL, commune=NULL) :**
- Salaires
- IRSA
- CNAPS
- FMFP
- Mutuelle Santé

**Dépenses AVEC géographie (district/commune selon ouvrage) :**
- Recettes forfaitaires
- Recettes volumétriques
- Recettes nouveaux PE
- Bons de livraison
- Avances
- Indemnités (géographie via plannings terrain)

### 2. Filtres géographiques

**Comportement après correction :**
- Filtrer par District : N'affiche PAS les salaires/charges sociales
- Filtrer par Commune : N'affiche PAS les salaires/charges sociales
- Filtrer par Ouvrage : N'affiche PAS les salaires/charges sociales

**Pour voir les salaires/charges :**
- Utiliser le filtre "Type" spécifiquement
- NE PAS appliquer de filtres géographiques
- OU créer un filtre dédié "Dépenses RH" dans l'interface

### 3. Recalcul nécessaire

**IMPORTANT** : Après cette correction, il faut **OBLIGATOIREMENT recalculer les prévisions** pour l'année en cours pour que les changements soient appliqués.

**Action utilisateur :**
1. Aller sur `/facturation/previsions/`
2. Clic sur bouton "Recalculer"
3. Attendre la fin du recalcul (15,000+ lignes)
4. Vérifier que les salaires/charges n'apparaissent plus dans les filtres géographiques

## ✅ Résultat final

**Problème 1 : Géographie** ✅ RÉSOLU
- Les salaires, IRSA et charges sociales ont maintenant `district=NULL` et `commune=NULL`
- Ils n'apparaissent plus dans les filtres géographiques
- La logique métier est respectée (RH = pas de localisation géographique)

**Problème 2 : Filtre Type** ✅ RÉSOLU
- Tous les types de prévisions sont disponibles dans le filtre
- Interface organisée avec groupement Recettes/Dépenses
- Possibilité de filtrer spécifiquement les salaires, IRSA, CNAPS, FMFP, Mutuelle

## 📅 Historique

- **10 décembre 2025** : Identification et correction des deux problèmes
- Tests complets validés
- Documentation créée
