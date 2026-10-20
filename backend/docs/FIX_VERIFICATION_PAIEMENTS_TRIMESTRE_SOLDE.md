# Correction 14 : Trimestre avec année après + Ajustement solde de tout compte

**Date** : 11 décembre 2025
**Fichier** : `backend/apps/employees/views_verification_paiements.py`

## Problème

### Descriptions NON CONFORMES

4 descriptions étaient marquées NON CONFORMES :

```
1. _CM RANDRIANANTENAINA Alain_Charge FMFP_1er trimestre 2025
2. _CM RANDRIANANTENAINA Alain_Charge Cnaps_1er trimestre 2025
3. _CM RANDRIANANTENAINA Alain_Charge CNaPS_4è trimestre 2024 [-10419913,6 split 1/39]
4. _AM VICTORIEN Angeliot_Ajustement solde de tout compte_2025 04 (période du 1 Juin 2022 au 4 Mars 2025)
```

**Erreurs** :
- Types détectés correctement (fmfp, cnaps, salaire)
- MAIS : "Format date incorrect"

### Analyse

**Problème 1 - Ordre des groupes capturés** :

Les patterns existants pour CNaPS/FMFP avec trimestre attendaient :
```
YYYY trimestre    →  Pattern: (\d{4})\s+([1-4]e?\s+trimestre)
```

Mais les descriptions avaient :
```
trimestre YYYY    →  Format: 1er trimestre 2025
```

**Problème 2 - Variations de casse** :

Le pattern utilisait `[Cc]naps` qui ne gère que le premier caractère :
- `Cnaps` : ✅ Match (c minuscule)
- `CNaPS` : ❌ No match (a minuscule non géré)

**Problème 3 - Caractères spéciaux** :

Les ordinaux ont différentes graphies :
- `1er` (e + r)
- `2e` (e seul)
- `3e` (e seul)
- `4è` (è avec accent grave)

**Problème 4 - Solde de tout compte avec préfixe** :

Pattern existant :
```python
r'_Solde de tout compte_(\d{4})\s+(\d{1,2})'
```

Ne reconnaît pas :
```
_Ajustement solde de tout compte_2025 04
```

## Solutions appliquées

### 1. Nouveau pattern CNaPS avec trimestre après année

**Ajout dans `PATTERNS_DESCRIPTION['cnaps']` (lignes 33-34)** :

```python
'cnaps': [
    r'_Charge CNaPS_(\d{4})\s+(\d{1,2})',
    r'_CNaPS_(\d{4})\s+(\d{1,2})',
    r'_CNaPS_(\d{4})\s+([1-4]e?\s+trimestre)',  # Année avant
    r'_Charge [Cc][Nn][Aa][Pp][Ss]_([1-4])(?:er|è|e)?\s+trimestre\s+(\d{4})',  # ✅ Année après
    r'_[Cc][Nn][Aa][Pp][Ss]_([1-4])(?:er|è|e)?\s+trimestre\s+(\d{4})',  # ✅ Sans "Charge"
],
```

**Explications** :
- `[Cc][Nn][Aa][Pp][Ss]` : Insensible à la casse complète (accepte CNaPS, Cnaps, CNAPS, cnaps)
- `([1-4])` : Capture le numéro du trimestre (1-4)
- `(?:er|è|e)?` : Suffixe ordinal optionnel (1er, 2e, 3e, 4è)
- `\s+trimestre\s+` : Mot "trimestre" avec espaces
- `(\d{4})` : Année (second groupe capturé)

### 2. Nouveau pattern FMFP avec trimestre après année

**Ajout dans `PATTERNS_DESCRIPTION['fmfp']` (lignes 40-41)** :

```python
'fmfp': [
    r'_Charge FMFP_(\d{4})\s+(\d{1,2})',
    r'_FMFP_(\d{4})\s+(\d{1,2})',
    r'_FMFP_(\d{4})\s+([1-4]e?\s+trimestre)',  # Année avant
    r'_Charge FMFP_([1-4])(?:er|è|e)?\s+trimestre\s+(\d{4})',  # ✅ Année après
    r'_FMFP_([1-4])(?:er|è|e)?\s+trimestre\s+(\d{4})',  # ✅ Sans "Charge"
],
```

### 3. Nouveau pattern "Ajustement solde de tout compte"

**Ajout dans `PATTERNS_DESCRIPTION['salaire']` (ligne 24)** :

```python
'salaire': [
    r'_Salaire_(\d{4})\s+(\d{1,2})',
    r'_Solde de tout compte_(\d{4})\s+(\d{1,2})',
    r'_.*?[Ss]olde de tout compte_(\d{4})\s+(\d{1,2})',  # ✅ Avec texte avant
    r'_Prime_(\d{4})',
    r'_.*?[Ss]alaire_(\d{4})\s+(\d{1,2})(?:\s+\d{1,2})*',
],
```

**Explication** :
- `_.*?` : Accepte n'importe quel texte avant "solde de tout compte"
- `[Ss]olde` : Accepte "Solde" ou "solde"

### 4. Logique de parsing des groupes capturés

**Modification dans `extraire_info_description()` (lignes 331-361)** :

```python
# Vérifier si le premier groupe est un numéro 1-4 (trimestre avant année)
try:
    premier_groupe_int = int(groups[0])
    if premier_groupe_int >= 1 and premier_groupe_int <= 4 and len(groups) == 2:
        # Pattern trimestre avec année après: (trimestre, année)
        # groups[0] = numéro trimestre (1-4)
        # groups[1] = année
        annee = int(groups[1])
        # Convertir le trimestre en mois (1er trimestre = mois 1, etc.)
        mois = (premier_groupe_int - 1) * 3 + 1
    else:
        # Pattern standard: (année, mois/trimestre)
        annee = premier_groupe_int
        # Le groupe 2 peut être un mois numérique ou un texte trimestre
        try:
            periode_str = groups[1]
            # Essayer d'abord de convertir comme mois numérique
            try:
                mois = int(periode_str)
            except (ValueError, TypeError):
                # Si pas un nombre, essayer comme trimestre
                mois_converti = convertir_trimestre_en_mois(periode_str)
                if mois_converti:
                    mois = mois_converti
        except IndexError:
            # Pas de groupe 2 (ex: Prime sans mois)
            mois = None
except (ValueError, TypeError):
    # groups[0] n'est pas un int (cas très rare)
    annee = None
```

**Logique** :
1. Si `groups[0]` est un int entre 1 et 4 avec 2 groupes → Format "trimestre YYYY"
   - `groups[0]` = numéro trimestre
   - `groups[1]` = année
   - Convertir trimestre en mois : `(trimestre - 1) * 3 + 1`
2. Sinon → Format standard "YYYY mois/trimestre"
   - `groups[0]` = année
   - `groups[1]` = mois ou trimestre texte

### Mapping Trimestre → Mois

```
1er trimestre → Mois 1 (janvier)
2e trimestre  → Mois 4 (avril)
3e trimestre  → Mois 7 (juillet)
4è trimestre  → Mois 10 (octobre)
```

**Formule** : `mois = (trimestre - 1) * 3 + 1`

## Tests de validation

### Test 1 : FMFP avec "1er trimestre"

```python
description = "_CM RANDRIANANTENAINA Alain_Charge FMFP_1er trimestre 2025"
result = extraire_info_description(description)
```

**Résultat** :
```
✅ CONFORME
Type: fmfp
Année: 2025
Mois: 1 (janvier - 1er trimestre)
```

### Test 2 : Cnaps (minuscule) avec "1er trimestre"

```python
description = "_CM RANDRIANANTENAINA Alain_Charge Cnaps_1er trimestre 2025"
result = extraire_info_description(description)
```

**Résultat** :
```
✅ CONFORME
Type: cnaps
Année: 2025
Mois: 1 (janvier - 1er trimestre)
```

### Test 3 : CNaPS avec "4è trimestre" + suffixe

```python
description = "_CM RANDRIANANTENAINA Alain_Charge CNaPS_4è trimestre 2024 [-10419913,6 split 1/39]"
result = extraire_info_description(description)
```

**Résultat** :
```
✅ CONFORME
Type: cnaps
Année: 2024
Mois: 10 (octobre - 4è trimestre)
```

**Note** : Le suffixe `[-10419913,6 split 1/39]` est ignoré (accepté par regex mais non parsé).

### Test 4 : Ajustement solde de tout compte

```python
description = "_AM VICTORIEN Angeliot_Ajustement solde de tout compte_2025 04 (période du 1 Juin 2022 au 4 Mars 2025)"
result = extraire_info_description(description)
```

**Résultat** :
```
✅ CONFORME
Type: salaire
Année: 2025
Mois: 4 (avril)
```

**Note** : Le texte entre parenthèses est ignoré (accepté mais non parsé).

## Cas d'usage

### 1. Charges trimestrielles CNaPS/FMFP

**Formats acceptés** :

```
✅ _CM XXX_Charge FMFP_1er trimestre 2025
✅ _CM XXX_Charge Cnaps_2e trimestre 2025
✅ _CM XXX_Charge CNaPS_3e trimestre 2025
✅ _CM XXX_Charge cnaps_4è trimestre 2025
✅ _CM XXX_FMFP_1er trimestre 2025 (sans "Charge")
✅ _CM XXX_CNaPS_4è trimestre 2024 [-123 split 1/39]
```

**Formats refusés** :

```
❌ _CM XXX_Charge FMFP_5e trimestre 2025 (trimestre invalide)
❌ _CM XXX_Charge FMFP_trimestre 1 2025 (ordre incorrect)
```

### 2. Solde de tout compte avec ajustement

**Formats acceptés** :

```
✅ _AM XXX_Solde de tout compte_2025 04
✅ _AM XXX_Ajustement solde de tout compte_2025 04
✅ _AM XXX_Régularisation solde de tout compte_2025 04
✅ _AM XXX_Correction Solde de tout compte_2025 04 (avec majuscule)
```

**Format refusé** :

```
❌ _AM XXX_Solde tout compte_2025 04 (manque "de")
```

## Impact

### Avant correction

**Statistiques** :
- **CNaPS/FMFP avec trimestre** : NON CONFORME
- **Ajustement solde de tout compte** : NON CONFORME

**Raisons** :
- Ordre des groupes capturés non géré
- Variations de casse non acceptées
- Pattern solde trop strict

### Après correction

**Statistiques** :
- **CNaPS/FMFP avec trimestre** : ✅ CONFORME
- **Ajustement solde de tout compte** : ✅ CONFORME

**Taux de conformité global** : +2 types de formats reconnus

## Notes techniques

### 1. Insensibilité à la casse

**Pourquoi `[Cc][Nn][Aa][Pp][Ss]` au lieu de `re.IGNORECASE` ?** :

Option 1 (choisie) :
```python
pattern = r'_Charge [Cc][Nn][Aa][Pp][Ss]_...'
```

Option 2 (non utilisée) :
```python
pattern = r'_Charge CNAPS_...'
re.search(pattern, description, re.IGNORECASE)
```

**Raison** : Les patterns sont stockés dans une liste et appliqués via `re.search()` simple. Ajouter `re.IGNORECASE` nécessiterait de changer toute la logique d'application des patterns.

### 2. Conversion trimestre → mois

**Choix du mois de référence** :

Chaque trimestre est représenté par son **premier mois** :

```
1er trimestre : Janvier-Mars    → Mois 1  (janvier)
2e trimestre  : Avril-Juin      → Mois 4  (avril)
3e trimestre  : Juillet-Sept    → Mois 7  (juillet)
4è trimestre  : Octobre-Déc     → Mois 10 (octobre)
```

**Alternative possible** : Utiliser le mois du milieu (2, 5, 8, 11) ou dernier (3, 6, 9, 12).

**Raison du choix** : Le premier mois est le plus intuitif et cohérent avec d'autres systèmes comptables.

### 3. Ordre des patterns

**Importance de l'ordre** :

Les patterns sont testés dans l'ordre de la liste. Les patterns les plus **spécifiques** doivent être en **premier**.

**Exemple CNaPS** :
```python
'cnaps': [
    r'_Charge CNaPS_(\d{4})\s+(\d{1,2})',  # Pattern 1 : Spécifique (mois)
    r'_CNaPS_(\d{4})\s+(\d{1,2})',  # Pattern 2 : Moins spécifique
    r'_CNaPS_(\d{4})\s+([1-4]e?\s+trimestre)',  # Pattern 3 : Spécifique (trimestre avant)
    r'_Charge [Cc][Nn][Aa][Pp][Ss]_([1-4])(?:er|è|e)?\s+trimestre\s+(\d{4})',  # Pattern 4 : Spécifique (trimestre après)
    r'_[Cc][Nn][Aa][Pp][Ss]_([1-4])(?:er|è|e)?\s+trimestre\s+(\d{4})',  # Pattern 5 : Moins spécifique
],
```

Si on inversait l'ordre, le pattern le plus large capturerait toutes les descriptions et les patterns spécifiques ne seraient jamais testés.

## Historique des corrections

Cette correction fait partie d'une série de 14 corrections pour améliorer la reconnaissance des descriptions de paiement :

1. ✅ Indemnité terrain - "du" optionnel
2. ✅ Frais - Accents e/é optionnels
3. ✅ Indemnité hors zone - Période complète acceptée
4. ✅ Frais - Période complète acceptée
5. ✅ Indemnités - Indemnite/Indemnité variations
6. ✅ Indemnité terrain - Connecteur "et" accepté
7. ✅ Indemnité terrain - Multiple connecteurs (au + et)
8. ✅ Indemnité terrain - Virgule comme séparateur
9. ✅ Frais - Underscore entre bénéficiaire et année
10. ✅ Frais - Espace après type de frais
11. ✅ Salaire - Multiple mois pour ajustements
12. ✅ Mutuelle santé - Texte descriptif accepté
13. ✅ Frais médicaux - "Remboursement pour" générique
14. ✅ **CNaPS/FMFP - Trimestre avec année après + Ajustement solde**

## Documentation liée

- Guide principal : `backend/docs/FIX_VERIFICATION_PAIEMENTS_INDEMNITES.md`
- Résumé : `backend/docs/CORRECTION_PAIEMENTS_SUMMARY.md`
- Tests : `backend/docs/TESTS_PAIEMENTS_VALIDES.txt`
