# Mapping Final - Table TemporaireDiameX

## Structure des colonnes DiameX

| Colonne | Type | Description | Source / Règle de remplissage |
|---------|------|-------------|--------------------------------|
| **Journal** | VARCHAR | Code journal comptable | `"00PERS"` OU valeur du journal de la Base (table `base.journal`) |
| **DateM** | DATE | Mois du ticket | Mois extrait de `date_ticket` (format: YYYY-MM) |
| **Rec** | INTEGER | Numéro de reçu | `0` (sera défini dans prochain workflow) |
| **DateRec** | DATE | Date du ticket | `detail.planning.date` (date du planning) |
| **Description** | TEXT | Description formatée | **Voir règles ci-dessous** |
| **In** | DECIMAL | Entrée (recettes) | Montant si type='recette', sinon 0 |
| **Out** | DECIMAL | Sortie (dépenses) | Montant si type='avance', sinon 0 |
| **Cat** | VARCHAR | Catégorie comptable | **Voir règles ci-dessous** |
| **PERS** | VARCHAR | Surnom employé | `detail.planning.employe.surnom` |
| **Fournisseur** | VARCHAR | Fournisseur du ticket | `detail.fournisseur.nom_fournisseur` (si existe) |
| **ACTIV** | VARCHAR | Base DiameX | `detail.planning.ouvrage.base.base_diamex` |

---

## Règles de remplissage détaillées

### 1. Journal
```python
# Priorité 1: Valeur par défaut
journal = "00PERS"

# Priorité 2: Si la base de l'ouvrage a un journal défini
if detail.planning and detail.planning.ouvrage and detail.planning.ouvrage.base:
    if hasattr(detail.planning.ouvrage.base, 'journal') and detail.planning.ouvrage.base.journal:
        journal = detail.planning.ouvrage.base.journal
```

---

### 2. DateM (Mois du ticket)
```python
from datetime import datetime

# Extraire le mois au format YYYY-MM
date_ticket = detail.planning.date  # datetime aware
datem = date_ticket.strftime('%Y-%m')  # Ex: "2025-01"
```

---

### 3. Rec (Numéro de reçu)
```python
rec = 0  # Toujours 0 initialement, sera défini dans prochain workflow
```

---

### 4. DateRec (Date du ticket)
```python
import pytz

# Conversion timezone Madagascar
tz_madagascar = pytz.timezone('Indian/Antananarivo')
date_aware = detail.planning.date

if date_aware.tzinfo:
    date_madagascar = date_aware.astimezone(tz_madagascar)
else:
    date_madagascar = tz_madagascar.localize(date_aware)

date_rec = date_madagascar.date()  # Ex: 2025-01-15
```

---

### 5. Description (Formatage spécifique)

#### Cas 1: Paiement forfaitaire (type='recette')
```python
# Format: _Paiement forfaitaire_[Nom Ouvrage]_[Montant ticket]
nom_ouvrage = detail.planning.ouvrage.nom_ouvrage if detail.planning and detail.planning.ouvrage else "N/A"
montant = detail.montant

description = f"_Paiement forfaitaire_{nom_ouvrage}_{montant}"
# Exemple: "_Paiement forfaitaire_Ouvrage Ambohimanga_75000"
```

#### Cas 2: Avance (type='avance')
```python
# Format: [NIF ou ISI]_[PREST ou vide]_[Designation des 2 premières designations]_[Montant]

# 1. NIF ou ISI du fournisseur
nif_isi = ""
if detail.fournisseur:
    nif_isi = detail.fournisseur.nif or detail.fournisseur.isi or ""

# 2. PREST ou vide (selon colonne prestation dans table Fournisseur)
prest = ""
if detail.fournisseur and hasattr(detail.fournisseur, 'prestation') and detail.fournisseur.prestation:
    prest = "PREST"

# 3. Récupérer les 2 premières désignations du ticket (du même planning)
# On suppose que le ticket peut avoir plusieurs lignes de détail
designations_list = []
planning_details = PlanningDetail.objects.filter(
    planning=detail.planning,
    utilise=True
).select_related('designation')[:2]

for pd in planning_details:
    if pd.designation:
        designations_list.append(pd.designation.nom)

designations_str = "_".join(designations_list) if designations_list else detail.designation.nom

# 4. Montant
montant = detail.montant

# Assemblage final
parts = [nif_isi, prest, designations_str, str(montant)]
description = "_".join([p for p in parts if p])  # Enlever les parties vides

# Exemple: "123456789_PREST_Essence_Huile moteur_100000"
# Exemple: "987654321__Carburant_50000" (sans PREST)
```

#### Cas 3: Bon de livraison (type='livraison')
```python
# Format similaire à avance ?
# À CONFIRMER avec l'utilisateur

# Proposition:
nif_isi = detail.fournisseur.nif or detail.fournisseur.isi or "" if detail.fournisseur else ""
prest = "PREST" if detail.fournisseur and detail.fournisseur.prestation else ""
designation_str = detail.designation.nom if detail.designation else ""
montant = detail.montant

parts = [nif_isi, prest, designation_str, str(montant)]
description = "_".join([p for p in parts if p])
```

---

### 6. In (Entrée - Recettes)
```python
# Montant positif si type='recette' (Paiement forfaitaire)
# Zéro sinon

if type_ticket == 'recette':
    in_amount = detail.montant
else:
    in_amount = 0
```

---

### 7. Out (Sortie - Dépenses)
```python
# Montant positif si type='avance'
# Zéro sinon

if type_ticket == 'avance':
    out_amount = detail.montant
else:
    out_amount = 0
```

**Note**: Pour les bons de livraison, faut-il mettre le montant dans `Out` aussi ?
- ✅ À CONFIRMER avec l'utilisateur

---

### 8. Cat (Catégorie comptable / Code compte)

#### Cas 1: Paiement forfaitaire
```python
cat = "748 411"  # Compte fixe pour paiements forfaitaires
```

#### Cas 2: Avance ou Livraison
```python
# Utiliser le compte défini dans PlanningDetail (2e étape workflow)
# C'est le champ 'compte' du PlanningDetail

if detail.compte:
    cat = detail.compte  # Code du compte qui sera recopié dans Access
else:
    cat = ""  # Ou valeur par défaut à définir
```

**Question**: Le champ `compte` existe-t-il dans PlanningDetail ?
- À vérifier dans le modèle Django

---

### 9. PERS (Surnom employé)
```python
# Surnom de l'employé depuis le planning
if detail.planning and detail.planning.employe:
    pers = detail.planning.employe.surnom
else:
    pers = ""
```

**Note**: Doit être sur la liste des surnoms définis dans la table Employés

---

### 10. Fournisseur
```python
# Nom du fournisseur depuis le ticket de caisse
if detail.fournisseur:
    fournisseur = detail.fournisseur.nom_fournisseur
else:
    fournisseur = ""
```

---

### 11. ACTIV (Base DiameX)
```python
# Base DiameX de l'ouvrage
if detail.planning and detail.planning.ouvrage and detail.planning.ouvrage.base:
    if hasattr(detail.planning.ouvrage.base, 'base_diamex'):
        activ = detail.planning.ouvrage.base.base_diamex
    else:
        activ = ""
else:
    activ = ""
```

---

## Exemple complet: Paiement forfaitaire

```python
# Ticket: Paiement forfaitaire - 75000 Ar - Ouvrage Ambohimanga - Point d'eau #1

ligne_diamex = {
    'journal': '00PERS',  # Ou journal de la base
    'datem': '2025-01',
    'rec': 0,
    'date_rec': date(2025, 1, 15),
    'description': '_Paiement forfaitaire_Ambohimanga_75000',
    'in': 75000.00,
    'out': 0,
    'cat': '748 411',
    'pers': 'Victorien',
    'fournisseur': '',
    'activ': 'BASE001'  # base_diamex de l'ouvrage
}
```

---

## Exemple complet: Avance (Essence)

```python
# Ticket: Avance essence - 100000 Ar - Fournisseur Total (NIF: 123456789, prestation: True)
# Designations dans le ticket: "Essence", "Huile moteur"

ligne_diamex = {
    'journal': '00PERS',
    'datem': '2025-01',
    'rec': 0,
    'date_rec': date(2025, 1, 20),
    'description': '123456789_PREST_Essence_Huile moteur_100000',
    'in': 0,
    'out': 100000.00,
    'cat': '605100',  # Code compte depuis PlanningDetail.compte
    'pers': 'Jean',
    'fournisseur': 'Total',
    'activ': 'BASE002'
}
```

---

## Exemple complet: Bon de livraison

```python
# Ticket: BL-2025-009 - Cadenas PM - 14000 Ar - Fournisseur QuincaMad (NIF: 987654321)

ligne_diamex = {
    'journal': '00PERS',
    'datem': '2025-01',
    'rec': 0,
    'date_rec': date(2025, 1, 10),
    'description': '987654321__Cadenas PM_14000',  # Pas de PREST
    'in': 0,
    'out': 14000.00,  # ⚠️ À CONFIRMER: Livraison = Out ou 0 ?
    'cat': '601200',  # Code compte depuis PlanningDetail.compte
    'pers': 'Marie',
    'fournisseur': 'QuincaMad',
    'activ': 'BASE001'
}
```

---

## Questions à clarifier

### 1. Modèle Django - Champs manquants ?
Le modèle `TemporaireDiameX` actuel a ces champs:
- ✅ `planning_detail` (ForeignKey)
- ✅ `numero_ticket` (CharField)
- ✅ `type_ticket` (CharField)
- ✅ `designation` (CharField)
- ✅ `quantite` (Decimal)
- ✅ `prix_unitaire` (Decimal)
- ✅ `montant` (Decimal)
- ✅ `employe` (ForeignKey)
- ✅ `ouvrage` (ForeignKey)
- ✅ `point_eau` (ForeignKey)
- ✅ `fournisseur` (ForeignKey)
- ✅ `equipement_constitutif` (ForeignKey)
- ✅ `statut` (CharField)
- ✅ `traite_par` (ForeignKey User)
- ✅ `date_ticket` (DateField)
- ✅ `date_traitement` (DateTime)
- ✅ `date_envoi_diamex` (DateTime)
- ✅ `erreur_message` (TextField)

**Champs DiameX à ajouter au modèle**:
- ❌ `journal` (CharField)
- ❌ `datem` (CharField - format YYYY-MM)
- ❌ `rec` (IntegerField)
- ❌ `date_rec` (DateField)
- ❌ `description` (TextField)
- ❌ `in_amount` (DecimalField) - Renommer pour éviter conflit avec mot-clé Python
- ❌ `out_amount` (DecimalField)
- ❌ `cat` (CharField) - Code compte comptable
- ❌ `pers` (CharField) - Surnom employé
- ❌ `fournisseur_nom` (CharField) - Nom fournisseur
- ❌ `activ` (CharField) - Base DiameX

**Action requise**: Modifier le modèle Django et créer migration

---

### 2. Champ `compte` dans PlanningDetail ?
```python
# Vérifier si ce champ existe:
PlanningDetail.compte  # Code compte comptable
```
Si absent, comment récupérer le code compte pour Cat ?

---

### 3. Récupération des "2 premières désignations"
Pour les avances, faut-il:
- Option A: Les 2 premières lignes du même planning avec `utilise=True` ?
- Option B: Les 2 premières lignes avec même `numero_bon_avance` ?
- Option C: Toutes les lignes liées au même ticket (comment identifier ?) ?

---

### 4. Bon de livraison - Colonne `Out`
Les bons de livraison doivent-ils avoir:
- Montant dans `Out` (comme avances) ?
- Ou montant = 0 (ce sont des entrées de stock, pas des dépenses directes) ?

---

### 5. Table `Base` et ses champs
Le modèle `Base` (ou `Organization.Ouvrage.base`) a-t-il ces champs ?
- `journal` (VARCHAR) - Code journal comptable
- `base_diamex` (VARCHAR) - Code base DiameX

Si absent, comment récupérer ces valeurs ?

---

## Prochaines étapes

1. ✅ **Valider ce mapping** avec l'utilisateur
2. ⏳ **Vérifier les modèles Django** existants:
   - PlanningDetail.compte ?
   - Base.journal et Base.base_diamex ?
   - Fournisseur.nif, .isi, .prestation ?
3. ⏳ **Modifier le modèle TemporaireDiameX** pour ajouter les champs DiameX
4. ⏳ **Créer la migration**
5. ⏳ **Implémenter la logique de remplissage** dans `api_valider_retour_ticket()`
6. ⏳ **Mettre à jour l'aperçu frontend** pour afficher les nouvelles colonnes
7. ⏳ **Tester avec les 3 types** de tickets

---

## Notes importantes

- ⚠️ **Format Description**: Utilise des underscores `_` comme séparateurs
- ⚠️ **Catégorie 748 411**: Espace dans le code compte ? Ou "748411" ?
- ⚠️ **In/Out mutuellement exclusifs**: Un ticket est soit recette (In>0, Out=0) soit avance (In=0, Out>0)
- ⚠️ **PERS doit exister**: Vérifier que le surnom est dans la liste autorisée
- ⚠️ **Rec=0 initial**: Sera mis à jour dans un workflow ultérieur (export DiameX ?)
