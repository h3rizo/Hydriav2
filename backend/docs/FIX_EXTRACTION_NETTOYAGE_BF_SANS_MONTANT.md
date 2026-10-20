# Fix Extraction Nettoyage BF sans Montant

**Date** : 29 décembre 2025
**Contexte** : Page de vérification comptable avec ouvrage

## Problème identifié

Dans la page `/comptabilite/verification-avec-ouvrage/`, certaines descriptions de transactions DiameX ne permettaient pas d'extraire le nom de l'ouvrage :

**Exemples de descriptions problématiques** :
- `_RAMIADANA Francelette_Nettoyage BF3_Vohipenohely`
- `_RAVOLOLONIRINA Harimalala Lydia_Nettoyage BF2_Anjohy`

**Symptôme** : L'ouvrage n'était pas extrait et ces lignes apparaissaient dans la liste des transactions sans ouvrage identifié.

## Cause

Le pattern de regex existant pour `Nettoyage BF` attendait obligatoirement un montant avant le nom de l'ouvrage :

```python
# Pattern 1b2 (ANCIEN) - Exige un montant
pattern_bf = r'Nettoyage\s+BF(\d+).*?_(\d+)_(?:Ar_)?(.+)$'
#                                     ^^^^^^ montant obligatoire
```

Or, les nouvelles descriptions ont un format simplifié **sans montant** :
- Format attendu par l'ancien pattern : `Nettoyage BF3_Fft_20000_Vohipenohely`
- Format réel des nouvelles descriptions : `Nettoyage BF3_Vohipenohely`

## Solution

Ajout d'un nouveau pattern `1b2a` qui reconnaît le format **sans montant** :

```python
# Pattern 1b2a: Nettoyage BF[numéro]_[OUVRAGE] (sans montant)
# Ex: "_RAMIADANA Francelette_Nettoyage BF3_Vohipenohely"
# Ex: "_RAVOLOLONIRINA Harimalala Lydia_Nettoyage BF2_Anjohy"
# Format simplifié : Nettoyage BF suivi d'un numéro, puis underscore et nom ouvrage
# DOIT être testé AVANT Pattern 1b3 (plus spécifique - avec numéro)
pattern_bf_simple = r'Nettoyage\s+BF(\d+)_([^_]+)$'
match_bf_simple = re.search(pattern_bf_simple, description, re.IGNORECASE)

if match_bf_simple:
    idxls = match_bf_simple.group(1)  # Le numéro après BF
    ouvrage_nom = match_bf_simple.group(2).strip()  # Le nom après l'underscore

    result['point_eau_idxls'] = idxls
    result['type_indemnite'] = 'BF'
    result['ouvrage_nom'] = ouvrage_nom

    # Chercher l'ouvrage
    try:
        ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
        if not ouvrage:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
        result['ouvrage_obj'] = ouvrage

        # Chercher le point d'eau par IDxls ET ouvrage
        if ouvrage:
            point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
            result['point_eau_obj'] = point_eau
    except:
        pass

    return result
```

### Détails du pattern

**Pattern** : `r'Nettoyage\s+BF(\d+)_([^_]+)$'`

**Explication** :
- `Nettoyage\s+` : Le mot "Nettoyage" suivi d'espaces
- `BF(\d+)` : "BF" suivi d'un ou plusieurs chiffres (capturé dans group(1) = IDXLS)
- `_` : Un underscore
- `([^_]+)$` : Un ou plusieurs caractères qui ne sont PAS des underscores jusqu'à la fin (capturé dans group(2) = nom ouvrage)

**Pourquoi `[^_]+` ?**
- Accepte tout caractère sauf underscore
- Permet d'avoir des espaces dans le nom d'ouvrage (ex: "Vohipenohely", "Anjohy")
- S'arrête au premier underscore rencontré (s'il y en a)

## Ordre de test des patterns

⚠️ **CRITICAL** : Le nouveau pattern `1b2a` est placé **AVANT** le pattern `1b3` (sans numéro) car il est **plus spécifique**.

**Ordre correct** :
1. Pattern `1b2` : `Nettoyage BF[numéro]_..._[montant]_[OUVRAGE]` (avec montant)
2. Pattern `1b2a` : `Nettoyage BF[numéro]_[OUVRAGE]` (sans montant) ← **NOUVEAU**
3. Pattern `1b3` : `Nettoyage BF_[OUVRAGE]` (sans numéro)

## Résultats des tests

### Test 1 : `_RAMIADANA Francelette_Nettoyage BF3_Vohipenohely`

✅ **Résultat** :
- Ouvrage nom : `Vohipenohely`
- Ouvrage obj : `Vohipenohely` (objet trouvé dans la base)
- Point eau IDXLS : `3`
- Type indemnité : `BF`

### Test 2 : `_RAVOLOLONIRINA Harimalala Lydia_Nettoyage BF2_Anjohy`

✅ **Résultat** :
- Ouvrage nom : `Anjohy`
- Ouvrage obj : `Anjohy` (objet trouvé dans la base)
- Point eau IDXLS : `2`
- Type indemnité : `BF`

### Test 3 : `RAMIADANA Francelette_Nettoyage BF3_Fft_20000_Vohipenohely` (rétrocompatibilité)

✅ **Résultat** :
- Ouvrage nom : `Vohipenohely`
- Ouvrage obj : `Vohipenohely` (objet trouvé dans la base)
- Point eau IDXLS : `3`
- Type indemnité : `BF`

**Note** : Le format avec montant continue d'être reconnu par le pattern `1b2` (ancien pattern).

## Fichier modifié

**Fichier** : `backend/apps/accounting/extracteurs_description.py`

**Emplacement** : Lignes 1575-1605

**Fonction** : `extraire_indemnite_rbf_ppmh(description)`

## Impact

Cette amélioration permet de reconnaître automatiquement les descriptions de type "Nettoyage BF" même lorsqu'elles ne contiennent pas de montant explicite, ce qui améliore la couverture des extractions dans :

1. **Page de vérification avec ouvrage** (`/comptabilite/verification-avec-ouvrage/`)
2. **Page de recoupement** (`/comptabilite/recoupement/releves/`)
3. **Dashboard paiements volume** (`/comptabilite/dashboard-paiements-volume/`)

Toutes les pages qui utilisent `extraire_ouvrage_et_mois_generique()` avec le compte `621102` (Indemnités RBF/PPMH/BF) bénéficient automatiquement de cette amélioration.

## Tests de validation

- [x] Test format sans montant (cas 1) : `_RAMIADANA Francelette_Nettoyage BF3_Vohipenohely`
- [x] Test format sans montant (cas 2) : `_RAVOLOLONIRINA Harimalala Lydia_Nettoyage BF2_Anjohy`
- [x] Test format avec montant (rétrocompatibilité) : `RAMIADANA Francelette_Nettoyage BF3_Fft_20000_Vohipenohely`
- [x] Django check : 0 erreurs
- [x] Extraction objet ouvrage fonctionnelle
- [x] Extraction IDXLS fonctionnelle

## Déploiement

**⚠️ Aucune migration requise** : Modification uniquement dans le code Python (fonction d'extraction).

**Étapes** :
1. Commit et push du fichier `extracteurs_description.py`
2. Redémarrer le serveur Django
3. Vérifier les pages de vérification comptable

**Commande de redémarrage** :
```bash
# Windows
Ctrl+C (arrêter le serveur actuel)
python manage.py runserver
```

## Documentation

**Scripts de test créés** :
- `backend/test_extraction_nettoyage_bf.py` - Tests unitaires pour ce fix

**Documentation associée** :
- `backend/docs/EXTRACTION_MULTI_PAIEMENTS_AMELIORATION.md` - Extraction multi-paiements
- `backend/CLAUDE.md` (section "MODULE NON-CONFORMITÉS") - Contexte général
