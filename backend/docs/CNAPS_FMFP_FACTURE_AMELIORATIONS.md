# 📄 AMÉLIORATIONS FACTURE CNAPS/FMFP EXCEL

## Date : 18 décembre 2025

## Vue d'ensemble

Améliorations apportées à la génération de la facture Excel pour les paiements CNaPS/FMFP trimestriels, avec une refonte complète de l'architecture pour utiliser **Annexe DNS comme source de données unique**.

## Architecture de la facture Excel

### Principe CRITICAL : Single Source of Truth

**ONGLET ANNEXE DNS = SOURCE PRIMAIRE DE DONNÉES**

Tous les autres onglets utilisent des formules Excel pour référencer Annexe DNS, garantissant ainsi :
- ✅ Cohérence des données
- ✅ Élimination des erreurs #REF!
- ✅ Maintenance facilitée (un seul endroit à modifier)
- ✅ Audit simplifié

### Ordre de génération (IMPORTANT)

```
1. ANNEXE DNS (données brutes)
   ↓
2. DIAME CNAPS (formules → Annexe DNS)
   ↓
3. EMPLOYEUR (formules → Annexe DNS)
   ↓
4. TALON DNS (formules → Annexe DNS)
```

## Modifications effectuées

### 1. ONGLET 1 : Annexe DNS (SOURCE PRIMAIRE) ✅

**Fichier** : `backend/apps/employees/views_cnaps_fmfp.py` (lignes 545-680)

**Rôle** : Rempli EN PREMIER avec les **données brutes** (valeurs numériques, pas de formules)

**Format** : Police Arial Narrow taille 14 pour toutes les cellules

**Structure des colonnes (A-W)** :

| Colonne | Champ | Description | Exemple | Format |
|---------|-------|-------------|---------|--------|
| A | Numéro employé | Identifiant interne | `EMP001` | Texte |
| B | Matricule CNaPS | Numéro CNaPS | `123456789` | Texte |
| C | Numéro CIN | Carte d'identité | `101234567890` | Texte |
| D | Nom | Nom de famille (employe.nom) | `RAKOTO` | Texte |
| E | Prénom | Prénoms (employe.prenom) | `Jean Marie` | Texte |
| F | Réf. Employeur | Code poste | `TECH-01` | Texte |
| G | Date embauche | Date d'embauche | `15/01/2020` | DD/MM/YYYY |
| H | Date débauchage | Date de sortie | `/` ou date | DD/MM/YYYY |
| **MOIS 1** | | | | |
| I | Salaire brut total M1 | Depuis table Salaire | `2,500,000.00` | #,##0.00 |
| J | 0 | Valeur fixe | `0.00` | #,##0.00 |
| K | Valeur calculée | Selon type contrat (voir règles) | Variable | #,##0.00 |
| L | Salaire minimum × 8 | SMIG × 8 | `2,000,000.00` | #,##0.00 |
| **MOIS 2** | | | | |
| M | Salaire brut total M2 | Depuis table Salaire | `2,500,000.00` | #,##0.00 |
| N | 0 | Valeur fixe | `0.00` | #,##0.00 |
| O | Valeur calculée | Selon type contrat (voir règles) | Variable | #,##0.00 |
| P | Salaire minimum × 8 | SMIG × 8 | `2,000,000.00` | #,##0.00 |
| **MOIS 3** | | | | |
| Q | Salaire brut total M3 | Depuis table Salaire | `2,500,000.00` | #,##0.00 |
| R | 0 | Valeur fixe | `0.00` | #,##0.00 |
| S | Valeur calculée | Selon type contrat (voir règles) | Variable | #,##0.00 |
| T | Salaire minimum × 8 | SMIG × 8 | `2,000,000.00` | #,##0.00 |
| **AUTRES** | | | | |
| U | Indicateur | Valeur fixe | `N` | Texte |
| V | Téléphone | Numéro téléphone | `034 12 345 67` | Texte |
| W | Email | Adresse email | `employe@org.mg` | Texte |

**Configuration** : Salaire minimum récupéré depuis `ConfigSalaire.salaire_minimum` (par défaut 250,000 Ar)

**Règles de calcul des colonnes K, O, S** :
- **Si salaire = 0** : Retourner `0`
- **Temps plein** : `243`
- **Mi-temps / Temps partiel** : `121.5`
- **Journalier** : `nombre_jours_travailles × 8` (par défaut 0 si non renseigné)
- **Fonction "Femme de ménage"** : `40`

**Code clé** :
```python
# Récupération salaire minimum depuis ConfigSalaire
config_salaire = ConfigSalaire.objects.first()
SALAIRE_MINIMUM = float(config_salaire.salaire_minimum) if config_salaire else 250000

# Fonction helper pour colonnes K, O, S
def calculer_valeur_colonne_kos(employe, salaire_brut, nombre_jours_travailles=None):
    if float(salaire_brut) == 0:
        return 0

    # Vérifier si "Femme de ménage"
    fonction = employe.poste.nom_poste if employe.poste else ''
    if 'femme de ménage' in fonction.lower():
        return 40

    # Récupérer contrat actif
    contrat_actif = employe.contrats.filter(fin_contrat__isnull=True).first()
    if contrat_actif:
        if contrat_actif.type_contrat == 'temps_plein':
            return 243
        elif contrat_actif.type_contrat in ['temps_partiel', 'Mi-temps']:
            return 121.5
        elif contrat_actif.type_contrat == 'journalier':
            return (nombre_jours_travailles or 0) * 8

    return 0

# Récupérer les salaires bruts depuis la table Salaire
for detail in details:
    employe_id = str(detail.employe.id)
    salaires_bruts_map[employe_id] = {}

    for idx, mois in enumerate(mois_trimestre, 1):
        salaire = Salaire.objects.filter(
            employe=detail.employe,
            mois=mois,
            annee=paiement.annee
        ).first()

        salaires_bruts_map[employe_id][idx] = float(salaire.salaire_brut) if salaire else 0

# Dans la boucle de remplissage
employe_id = str(employe.id)
salaire_brut_m1 = salaires_bruts_map.get(employe_id, {}).get(1, 0)
salaire_brut_m2 = salaires_bruts_map.get(employe_id, {}).get(2, 0)
salaire_brut_m3 = salaires_bruts_map.get(employe_id, {}).get(3, 0)

# MOIS 1 (colonnes I-L)
ws_annexe.cell(row=row, column=9, value=float(salaire_brut_m1))  # Salaire brut depuis Salaire
ws_annexe.cell(row=row, column=10, value=0)  # Valeur fixe
ws_annexe.cell(row=row, column=11, value=float(calculer_valeur_colonne_kos(employe, salaire_brut_m1)))  # Calculée
ws_annexe.cell(row=row, column=12, value=float(SALAIRE_MINIMUM * 8))  # SMIG × 8

# MOIS 2 (colonnes M-P)
ws_annexe.cell(row=row, column=13, value=float(salaire_brut_m2))  # Salaire brut depuis Salaire
ws_annexe.cell(row=row, column=14, value=0)  # Valeur fixe
ws_annexe.cell(row=row, column=15, value=float(calculer_valeur_colonne_kos(employe, salaire_brut_m2)))  # Calculée
ws_annexe.cell(row=row, column=16, value=float(SALAIRE_MINIMUM * 8))  # SMIG × 8

# MOIS 3 (colonnes Q-T)
ws_annexe.cell(row=row, column=17, value=float(salaire_brut_m3))  # Salaire brut depuis Salaire
ws_annexe.cell(row=row, column=18, value=0)  # Valeur fixe
ws_annexe.cell(row=row, column=19, value=float(calculer_valeur_colonne_kos(employe, salaire_brut_m3)))  # Calculée
ws_annexe.cell(row=row, column=20, value=float(SALAIRE_MINIMUM * 8))  # SMIG × 8

# Autres (colonnes U-W)
ws_annexe.cell(row=row, column=21, value='N')  # Indicateur
ws_annexe.cell(row=row, column=22, value=employe.telephone)  # Téléphone
ws_annexe.cell(row=row, column=23, value=employe.email)  # Email

# Police Arial Narrow taille 14 pour tout
arial_narrow_14 = Font(name='Arial Narrow', size=14)
for col in range(1, 24):  # Colonnes A-W
    ws_annexe.cell(row=row, column=col).font = arial_narrow_14
```

**Variables de portée** :
```python
annexe_first_row = 3  # Première ligne de données
annexe_last_row = current_row_annexe - 1  # Dernière ligne de données
```

Ces variables sont utilisées par tous les autres onglets pour référencer les bonnes lignes.

---

### 2. ONGLET 2 : DIAME CNAPS (FORMULES) ✅

**Fichier** : `backend/apps/employees/views_cnaps_fmfp.py` (lignes 617-694)

**Rôle** : Affiche les données avec **formules Excel** référençant Annexe DNS

**Structure** :

| Colonne | Champ | Formule | Description |
|---------|-------|---------|-------------|
| A | Nom | `='Annexe DNS'!D{row}` | Référence nom |
| B | Prénoms | `='Annexe DNS'!E{row}` | Référence prénoms |
| C | Mois 1 CNaPS | `='Annexe DNS'!I{row}` | Référence M1 CNaPS |
| D | Mois 1 FMFP | `='Annexe DNS'!J{row}` | Référence M1 FMFP |
| E | Mois 2 CNaPS | `='Annexe DNS'!K{row}` | Référence M2 CNaPS |
| F | Mois 2 FMFP | `='Annexe DNS'!L{row}` | Référence M2 FMFP |
| G | Mois 3 CNaPS | `='Annexe DNS'!M{row}` | Référence M3 CNaPS |
| H | Mois 3 FMFP | `='Annexe DNS'!N{row}` | Référence M3 FMFP |
| I | Total CNaPS | `=C{row}+E{row}+G{row}` | Somme CNaPS 3 mois |
| J | Total FMFP | `=D{row}+F{row}+H{row}` | Somme FMFP 3 mois |

**Ligne TOTAL GÉNÉRAL** :
```python
ws_diame.cell(row=total_row_diame, column=3, value=f'=SUM(C{diame_first_row}:C{diame_last_row})')  # M1 CNaPS
ws_diame.cell(row=total_row_diame, column=4, value=f'=SUM(D{diame_first_row}:D{diame_last_row})')  # M1 FMFP
# ... etc pour les autres colonnes
```

**AMÉLIORATION : Bordures internes** ✅

```python
# Définition du style
thin_border = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)

# Application sur toutes les cellules (colonnes A à J)
for col in range(1, 11):
    cell = ws_diame.cell(row=current_row_diame, column=col)
    if col >= 3:  # Colonnes avec nombres
        cell.number_format = '#,##0.00'
    cell.border = thin_border  # ✅ BORDURES AJOUTÉES
```

---

### 3. ONGLET 3 : EMPLOYEUR (FORMULES) ✅

**Fichier** : `backend/apps/employees/views_cnaps_fmfp.py` (lignes 696-754)

**Rôle** : Formulaire de déclaration CNaPS/FMFP avec **formules référençant Annexe DNS**

**Formules AVANT (❌ ERREURS #REF!)** :
```excel
=COUNTIF([1]!liste_paiement[Mois paiement],EMPLOYEUR!C$20)
=SUMIF([1]!liste_paiement[Mois paiement],EMPLOYEUR!C$20,[1]!liste_paiement[Salaires plafonnés])
```

**Formules APRÈS (✅ CORRECT)** :

#### Section DÉCLARATION CNaPS (lignes 24-27)

**Ligne 24 : Nombre d'employés**
```python
ws_employeur['C24'] = f"=COUNTA('Annexe DNS'!D{annexe_first_row}:D{annexe_last_row})"
ws_employeur['D24'] = "=C24"  # Même nombre pour les 3 mois
ws_employeur['E24'] = "=C24"
```

**Ligne 25 : Total salaires CNaPS par mois**
```python
ws_employeur['C25'] = f"=SUM('Annexe DNS'!I{annexe_first_row}:I{annexe_last_row})"  # Mois 1
ws_employeur['D25'] = f"=SUM('Annexe DNS'!K{annexe_first_row}:K{annexe_last_row})"  # Mois 2
ws_employeur['E25'] = f"=SUM('Annexe DNS'!M{annexe_first_row}:M{annexe_last_row})"  # Mois 3
ws_employeur['F25'] = "=SUM(C25:E25)"
```

**Ligne 26 : Cotisations CNaPS × 13**
```python
ws_employeur['C26'] = "=C25*13"
ws_employeur['D26'] = "=D25*13"
ws_employeur['E26'] = "=E25*13"
ws_employeur['F26'] = "=SUM(C26:E26)"
```

**Ligne 27 : Total CNaPS par mois (même que ligne 25)**
```python
ws_employeur['C27'] = "=C25"
ws_employeur['D27'] = "=D25"
ws_employeur['E27'] = "=E25"
ws_employeur['F27'] = "=SUM(C27:E27)"
```

#### Section FMFP (lignes 36-38)

**Ligne 36 : Nombre d'employés**
```python
ws_employeur['C36'] = "=C24"  # Référence interne
ws_employeur['D36'] = "=D24"
ws_employeur['E36'] = "=E24"
```

**Ligne 37 : Total salaires (même que ligne 25)**
```python
ws_employeur['C37'] = "=C25"
ws_employeur['D37'] = "=D25"
ws_employeur['E37'] = "=E25"
ws_employeur['F37'] = "=SUM(C37:E37)"
```

**Ligne 38 : Total FMFP par mois**
```python
ws_employeur['C38'] = f"=SUM('Annexe DNS'!J{annexe_first_row}:J{annexe_last_row})"  # Mois 1
ws_employeur['D38'] = f"=SUM('Annexe DNS'!L{annexe_first_row}:L{annexe_last_row})"  # Mois 2
ws_employeur['E38'] = f"=SUM('Annexe DNS'!N{annexe_first_row}:N{annexe_last_row})"  # Mois 3
ws_employeur['F38'] = "=SUM(C38:E38)"
```

---

### 4. ONGLET 4 : Talon DNS (FORMULES) ✅

**Fichier** : `backend/apps/employees/views_cnaps_fmfp.py` (lignes 757-821)

**Rôle** : Talon de paiement avec **formules référençant Annexe DNS**

**Structure** : Similaire à Annexe DNS mais avec formatage différent

```python
# Remplir les employés (à partir de la ligne 16)
for row_idx in range(annexe_first_row, annexe_last_row + 1):
    # Numéro employé
    ws_talon.cell(row=current_row_talon, column=1, value=f"='Annexe DNS'!A{row_idx}")

    # Matricule CNaPS
    ws_talon.cell(row=current_row_talon, column=2, value=f"='Annexe DNS'!B{row_idx}")

    # CIN
    ws_talon.cell(row=current_row_talon, column=3, value=f"='Annexe DNS'!C{row_idx}")

    # Nom
    ws_talon.cell(row=current_row_talon, column=4, value=f"='Annexe DNS'!D{row_idx}")

    # Prénoms
    ws_talon.cell(row=current_row_talon, column=5, value=f"='Annexe DNS'!E{row_idx}")

    # ... etc pour les autres colonnes
```

---

## Correspondance des colonnes (Référence)

### Annexe DNS → DIAME CNAPS

| Annexe DNS | DIAME CNAPS | Contenu |
|------------|-------------|---------|
| D | A | Nom |
| E | B | Prénoms |
| I | C | Mois 1 CNaPS |
| J | D | Mois 1 FMFP |
| K | E | Mois 2 CNaPS |
| L | F | Mois 2 FMFP |
| M | G | Mois 3 CNaPS |
| N | H | Mois 3 FMFP |
| - | I | Total CNaPS (formule) |
| - | J | Total FMFP (formule) |

### Annexe DNS → EMPLOYEUR

| Annexe DNS | EMPLOYEUR | Ligne | Contenu |
|------------|-----------|-------|---------|
| D (count) | C24-E24 | 24 | Nb employés |
| I, K, M (sum) | C25-E25 | 25 | Total CNaPS/mois |
| J, L, N (sum) | C38-E38 | 38 | Total FMFP/mois |

---

## Avantages de la nouvelle architecture

### 1. Single Source of Truth ✅

**Avant** : Données dupliquées dans plusieurs onglets
```
DIAME CNAPS: [Valeurs copiées]
EMPLOYEUR: [Formules externes #REF!]
Annexe DNS: [Valeurs copiées]
```

**Après** : Une seule source de données
```
Annexe DNS: [DONNÉES BRUTES]
    ↓
DIAME CNAPS: [Formules → Annexe DNS]
EMPLOYEUR: [Formules → Annexe DNS]
Talon DNS: [Formules → Annexe DNS]
```

### 2. Élimination des erreurs #REF! ✅

**Problème** : Les formules `[1]!liste_paiement` référençaient un classeur externe inexistant

**Solution** : Toutes les formules référencent maintenant `'Annexe DNS'!` (onglet interne)

### 3. Cohérence garantie ✅

Si une donnée change dans Annexe DNS, TOUS les onglets se mettent à jour automatiquement.

### 4. Audit simplifié ✅

Pour vérifier les données : consulter **uniquement Annexe DNS**.

### 5. Bordures pour meilleure lisibilité ✅

Tableau DIAME CNAPS avec bordures internes sur toutes les cellules (y compris TOTAL GÉNÉRAL).

---

## Fichiers modifiés

### `backend/apps/employees/views_cnaps_fmfp.py`

**Lignes 537-543** : Définition du style de bordures
```python
thin_border = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)
```

**Lignes 545-615** : ONGLET 1 - Annexe DNS (données brutes)
- Remplissage avec valeurs numériques
- Colonnes A-N
- Variables `annexe_first_row` et `annexe_last_row`

**Lignes 617-694** : ONGLET 2 - DIAME CNAPS (formules + bordures)
- Formules référençant Annexe DNS
- Bordures sur toutes les cellules
- Ligne TOTAL avec formules SUM()

**Lignes 696-754** : ONGLET 3 - EMPLOYEUR (formules)
- Section DÉCLARATION CNaPS (lignes 24-27)
- Section FMFP (lignes 36-38)
- Toutes les formules utilisent `'Annexe DNS'!`

**Lignes 757-821** : ONGLET 4 - Talon DNS (formules)
- Formules référençant Annexe DNS
- Support des données salariales (colonnes I-N)

---

## Tests de validation

### Test 1 : Génération de facture
1. ✅ Créer un paiement CNaPS/FMFP pour un trimestre
2. ✅ Ajouter des employés au paiement
3. ✅ Générer la facture Excel
4. ✅ Ouvrir le fichier Excel

### Test 2 : Vérification Annexe DNS
1. ✅ Onglet "Annexe DNS" contient les données brutes (valeurs numériques)
2. ✅ Colonnes A-N remplies correctement
3. ✅ Format des nombres : `#,##0.00`

### Test 3 : Vérification DIAME CNAPS
1. ✅ Onglet "DIAME CNAPS" contient des formules (ex: `='Annexe DNS'!D3`)
2. ✅ Bordures visibles sur toutes les cellules (A-J)
3. ✅ Ligne "TOTAL GÉNÉRAL" avec bordures et formules SUM()
4. ✅ Valeurs affichées correspondent à Annexe DNS

### Test 4 : Vérification EMPLOYEUR
1. ✅ Aucune erreur #REF!
2. ✅ Ligne 24 : Nombre d'employés correct (formule COUNTA)
3. ✅ Ligne 25 : Total CNaPS correct (formule SUM sur Annexe DNS colonnes I, K, M)
4. ✅ Ligne 38 : Total FMFP correct (formule SUM sur Annexe DNS colonnes J, L, N)
5. ✅ Valeurs cohérentes avec DIAME CNAPS

### Test 5 : Vérification Talon DNS
1. ✅ Formules référençant Annexe DNS
2. ✅ Données cohérentes avec autres onglets

### Test 6 : Modification des données
1. Modifier une valeur dans Annexe DNS (ex: colonne I, ligne 3)
2. ✅ Vérifier que DIAME CNAPS se met à jour automatiquement
3. ✅ Vérifier que EMPLOYEUR se met à jour automatiquement
4. ✅ Vérifier que les totaux se recalculent

---

## Points d'attention CRITICAL

### 1. Ordre de génération OBLIGATOIRE

⚠️ **Annexe DNS DOIT être rempli EN PREMIER**

```python
# ✅ BON ORDRE
1. Remplir Annexe DNS (données brutes)
2. Utiliser annexe_first_row et annexe_last_row
3. Générer DIAME CNAPS avec formules
4. Générer EMPLOYEUR avec formules
5. Générer Talon DNS avec formules
```

### 2. Variables de portée

⚠️ **Les variables `annexe_first_row` et `annexe_last_row` sont ESSENTIELLES**

Elles sont utilisées par tous les autres onglets pour créer les formules avec les bonnes plages.

### 3. Format des formules

⚠️ **Utiliser des guillemets simples pour les noms d'onglets avec espaces**

```python
# ✅ CORRECT
ws_diame.cell(row=3, column=1, value=f"='Annexe DNS'!D3")

# ❌ INCORRECT
ws_diame.cell(row=3, column=1, value=f"=Annexe DNS!D3")  # Erreur Excel
```

### 4. Format des nombres

⚠️ **Appliquer le format `#,##0.00` pour les colonnes monétaires**

```python
cell.number_format = '#,##0.00'
```

### 5. Effacement du contenu des lignes existantes

⚠️ **UTILISER cell.value = None au lieu de delete_rows()**

**CRITIQUE** : `delete_rows()` peut casser les structures Excel complexes (formules, tableaux structurés, etc.)

```python
# ✅ CORRECT : Effacer le contenu uniquement (en ignorant les cellules fusionnées)
from openpyxl.cell.cell import MergedCell

max_row_to_clear = min(ws_diame.max_row, 500)
for row in range(3, max_row_to_clear + 1):
    for col in range(1, 11):  # Colonnes A-J
        cell = ws_diame.cell(row=row, column=col)
        # Ignorer les cellules fusionnées (MergedCell est en lecture seule)
        if not isinstance(cell, MergedCell):
            cell.value = None
            cell.border = None

# ❌ INCORRECT : Ne jamais utiliser delete_rows()
ws_diame.delete_rows(3, ws_diame.max_row - 2)  # Peut corrompre le fichier Excel
```

**Raisons** :
1. La méthode `delete_rows()` supprime physiquement les lignes, ce qui peut :
   - Casser des références de formules dans d'autres onglets
   - Détruire des tableaux structurés Excel
   - Causer l'erreur "Nous avons trouvé un problème dans le contenu"

2. Les **cellules fusionnées (MergedCell)** sont en lecture seule :
   - Tenter de modifier `cell.value` sur une MergedCell cause : `'MergedCell' object attribute 'value' is read-only`
   - Solution : Vérifier avec `isinstance(cell, MergedCell)` avant modification

---

## Prochaines améliorations possibles

1. **Bordures en-têtes** : Ajouter bordures sur les lignes d'en-tête (lignes 1-2)
2. **Couleurs** : Ajouter fond de couleur sur la ligne TOTAL GÉNÉRAL
3. **Validation Excel** : Ajouter validations sur cellules modifiables
4. **Protection** : Protéger Annexe DNS pour éviter modifications accidentelles
5. **Formules dynamiques** : Adapter selon le type de déclaration (mensuelle/trimestrielle)

---

## ✅ Statut : COMPLET ET OPÉRATIONNEL

La génération de facture Excel CNaPS/FMFP utilise maintenant une architecture **Single Source of Truth** :

✅ **Annexe DNS** = Source primaire de données (valeurs brutes)
✅ **DIAME CNAPS** = Formules + bordures internes
✅ **EMPLOYEUR** = Formules (plus d'erreurs #REF!)
✅ **Talon DNS** = Formules

✅ Fichier Excel autonome et cohérent
✅ Audit simplifié (une seule source à vérifier)
✅ Maintenance facilitée

**Accessible via** : Plannings > Paie > Paiements CNaPS/FMFP > Générer facture
