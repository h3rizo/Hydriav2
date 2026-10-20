# Règles de validation DiameX - Module Caissière

## Vue d'ensemble

Ce document explique les règles métier appliquées lors de la validation des retours de tickets par la caissière, avant export vers DiameX.

## Différenciation des types de transactions

### Types d'avances (Designation.type_avance_caissiere)

1. **Bon de livraison** (`bon_livraison`)
   - → Type DiameX : `'depense'`
   - → Impact stock : OUI (mise à jour automatique)
   - → Compte : Selon le compte lié à la désignation

2. **Avance** (`avance`)
   - → Type DiameX : `'avance'`
   - → Impact stock : NON
   - → Compte : Toujours `'00PERS'` (compte de tiers)
   - → Remboursable

3. **Facture/Dépense** (`facture`)
   - → Type DiameX : `'depense'`
   - → Impact stock : NON
   - → Compte : Selon le compte lié à la désignation
   - → Achat définitif (non remboursable)

4. **Recette** (`recette`)
   - → Type DiameX : `'recette'`
   - → Impact stock : NON
   - → Compte : Selon le compte lié à la désignation

## Règles de validation des champs

### 1. Fournisseur (Detail)

**Configuration** : Champ `Compte.fournisseur_obligatoire` (oui/non)

**Règles** :
- Si `compte.fournisseur_obligatoire = True` :
  - ✅ Fournisseur **DOIT** être renseigné
  - ❌ Erreur si fournisseur manquant
  - → `DiameXTemporaire.fournisseur` = ForeignKey vers Fournisseur

- Si `compte.fournisseur_obligatoire = False` :
  - ✅ Fournisseur **DOIT** rester vide/NULL
  - → `DiameXTemporaire.fournisseur` = NULL

**Exemple** :
```python
Compte "601011" (Matériaux) : fournisseur_obligatoire = True
→ Fournisseur requis, sinon erreur

Compte "00PERS" (Avances) : fournisseur_obligatoire = False
→ Fournisseur DOIT être NULL
```

### 2. Programme (ACTIV/Volet)

**Configuration** : Champ `Compte.prog_obligatoire` (oui/non)

**Règles** :
- Si `compte.compte` commence par `"00PERS"` :
  - ✅ ACTIV **DOIT** rester vide/NULL
  - → `DiameXTemporaire.prog` = NULL

- Sinon (autres comptes) :
  - ✅ ACTIV = Valeur du champ `Base.volet` de l'employé
  - Source : `planning_detail.planning.employe.base.volet`
  - Si `compte.prog_obligatoire = True` et employé sans base :
    - ❌ Erreur si volet manquant

**Exemple** :
```python
Compte "00PERS" :
→ ACTIV = NULL (toujours)

Compte "601011" (Matériaux) :
→ ACTIV = employe.base.volet (ex: "EP" ou "AEP")
→ Si prog_obligatoire=True et pas de base : ERREUR
```

## Configuration dans l'admin Django

### Accès
**Administration > Organisation > Comptes**

### Colonnes affichées
- Nom compte
- Code compte
- Organisation
- Achat (oui/non)
- **Fournisseur obligatoire** (oui/non)
- **Programme obligatoire** (oui/non)
- À recouper Hydria/DiameX

### Fieldsets
Section **"Règles DiameX"** :
- Fournisseur obligatoire (checkbox)
- Programme (ACTIV) obligatoire (checkbox)

### Quels comptes configurer ?

**Fournisseur obligatoire = True** :
- Tous les comptes d'achats de matériaux/fournitures/équipements
- Exemples : 601011, 602XXX, 605XXX, 606XXX
- Critère : Comptes où on doit tracer le fournisseur

**Fournisseur obligatoire = False** :
- Comptes de tiers (00PERS, 00BOOK, 00FND1)
- Salaires (641XXX)
- Charges salariales (646XXX)

**Programme obligatoire = True** :
- Comptes où il est critique de tracer le programme/volet
- Dépend des besoins de reporting DiameX

## Workflow de validation

1. **Scan/Saisie du ticket** par la caissière
2. **Récupération des données** depuis PlanningDetail
3. **Détermination du compte** :
   - Via `planning_detail.compte`
   - Ou compte par défaut selon type
4. **Validation conditionnelle** :
   - Vérification `compte.fournisseur_obligatoire`
   - Vérification `compte.prog_obligatoire`
   - Calcul de `final_fournisseur_value`
   - Calcul de `final_prog_value`
5. **Si erreurs** : Retour JSON avec liste des champs manquants
6. **Si OK** : Création ligne `DiameXTemporaire` avec valeurs validées
7. **Marquage retour** : `planning_detail.retour = True`

## Fichiers concernés

- **Modèle** : `backend/apps/organization/models.py` (Compte)
- **Migration** : `organization.0009_compte_fournisseur_obligatoire_and_more.py`
- **Admin** : `backend/apps/organization/admin.py` (CompteAdmin)
- **Validation** : `backend/apps/billing/views_caissiere.py` (valider_retour, lignes 483-522)
- **Création** : `backend/apps/billing/views_caissiere.py` (DiameXTemporaire.create, lignes 535-555)

## Messages d'erreur

### Fournisseur manquant
```
Fournisseur obligatoire pour le compte 601011
```

### Programme manquant
```
Programme (ACTIV/Volet) obligatoire pour le compte 601011 mais employé sans base
```

## Tests recommandés

1. **Compte avec fournisseur obligatoire** :
   - Retourner ticket sans fournisseur → Erreur attendue
   - Retourner ticket avec fournisseur → Succès

2. **Compte sans fournisseur obligatoire** :
   - Vérifier que `DiameXTemporaire.fournisseur = NULL`
   - Même si fournisseur renseigné dans PlanningDetail

3. **Compte 00PERS** :
   - Vérifier que `DiameXTemporaire.prog = NULL`

4. **Autre compte avec employé ayant une base** :
   - Vérifier que `DiameXTemporaire.prog = Base.volet`

5. **Autre compte avec employé SANS base** :
   - Si `prog_obligatoire=True` → Erreur attendue
   - Si `prog_obligatoire=False` → Succès avec prog=NULL

## Historique des modifications

- **30 octobre 2025** : Implémentation initiale règles conditionnelles
  - Ajout champs `fournisseur_obligatoire` et `prog_obligatoire`
  - Validation conditionnelle dans `valider_retour()`
  - Utilisation de `final_fournisseur_value` et `final_prog_value`
