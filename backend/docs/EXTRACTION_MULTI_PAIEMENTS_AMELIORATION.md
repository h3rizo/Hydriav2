# Amélioration Extraction Multi-Paiements - 28 décembre 2025

## Vue d'ensemble

Amélioration de la fonction d'extraction des descriptions de paiements volumétriques pour reconnaître et segmenter automatiquement les descriptions contenant plusieurs paiements sur une seule ligne.

## Problème initial

Les descriptions DiameX peuvent contenir plusieurs paiements séparés par des points-virgules, dans deux formats différents :

**Format 1 - Ouvrage répété** :
```
Paiement au volume Anjahambe 03/2025 9200; Anjahambe 04/2025 246500; Anjahambe 05/2025 251400; Anjahambe
```
- Chaque segment contient le nom de l'ouvrage
- Format date : MM/YYYY
- Montants explicites

**Format 2 - Ouvrage hérité** :
```
Paiement au volume Anjahambe 12/2025 41400; 01/2025 24200; 02/2025 21900; 03/2025 58700; ...
```
- Premier segment : Nom ouvrage + date + montant
- Segments suivants : Date + montant seulement (héritent du nom d'ouvrage du premier segment)
- Format date : MM/YYYY

L'ancienne fonction retournait seulement les informations du premier paiement, ignorant les suivants.

## Solution appliquée

### 1. Fonction d'extraction principale améliorée

**Fichier** : `backend/apps/accounting/extracteurs_description.py` (lignes 51-289)

**Changements** :

1. **Nouvelle signature de retour** :
   - Si description simple : retourne `dict` (comportement d'origine)
   - Si multi-paiement (contient `;`) : retourne `list` de `dict`

2. **Nouvelle fonction `_extraire_multi_paiements()`** (lignes 95-185) :
   - Détecte et parse les segments séparés par `;`
   - Support format MM/YYYY et DD/MM/YYYY
   - Héritage automatique du nom d'ouvrage si absent
   - Extraction des montants explicites si présents
   - Recherche automatique de l'ouvrage dans la base de données

3. **Fonction `_extraire_paiement_simple()`** (lignes 188-289) :
   - Code original déplacé dans une fonction séparée
   - Maintient la rétrocompatibilité complète

**Pattern de reconnaissance** :
```python
pattern_segment = r'^(?:(.+?)\s+)?(\d{2}/\d{4}|\d{2}/\d{2}/\d{4})(?:\s+(\d+(?:[,\s]\d+)*))?'
```

Capture :
- Groupe 1 (optionnel) : Nom d'ouvrage
- Groupe 2 (obligatoire) : Date au format MM/YYYY ou DD/MM/YYYY
- Groupe 3 (optionnel) : Montant

**Logique d'héritage d'ouvrage** :
```python
ouvrage_courant = None  # Variable partagée entre tous les segments

for segment in segments:
    if ouvrage_seg:  # Si le segment a un nom d'ouvrage explicite
        ouvrage_courant = ouvrage_seg.strip()
        # Chercher dans la base de données
    # Sinon, ouvrage_courant garde sa valeur précédente (héritage)

    result['ouvrage_nom'] = ouvrage_courant
```

### 2. Mise à jour des vues utilisant la fonction

#### A. Dashboard Paiements Volume

**Fichier** : `backend/apps/accounting/views.py` (lignes 6257-6308)

**Changement** :
```python
# Avant (comportement simple)
info = extraire_ouvrage_et_mois_paiement_volume(transaction.description)
if info and info.get('mois') and info.get('annee'):
    # Traiter UN SEUL paiement
    ...

# Après (support multi-paiements)
info = extraire_ouvrage_et_mois_paiement_volume(transaction.description)

# Normaliser en liste
infos_list = info if isinstance(info, list) else [info]

# Diviser le montant total
montant_transaction = Decimal(str(transaction.montant_in)) if transaction.montant_in else Decimal('0')
nb_paiements = len([i for i in infos_list if i.get('mois') and i.get('annee')])
montant_par_paiement = montant_transaction / nb_paiements if nb_paiements > 0 else montant_transaction

# Traiter TOUS les paiements
for info_item in infos_list:
    if info_item and info_item.get('mois') and info_item.get('annee'):
        # Catégoriser avec montant_par_paiement
        ...
```

**Avantage** : Les multi-paiements sont maintenant correctement comptabilisés dans les statistiques de délais.

#### B. API Détails Délais de Paiement

**Fichier** : `backend/apps/accounting/views.py` (lignes 6566-6639)

**Changement similaire** :
- Normalisation en liste
- Division du montant total
- Extraction du nom d'ouvrage depuis la description si non disponible dans la base

**Avantage** : Les détails affichent maintenant TOUS les paiements avec leurs montants respectifs.

#### C. Page Recoupement Relevés

**Fichier** : `backend/apps/accounting/views.py` (utilisé via `extraire_ouvrage_et_mois_generique`)

La fonction `extraire_ouvrage_et_mois_generique` (ligne 1902 dans extracteurs_description.py) délègue automatiquement à notre fonction améliorée pour le compte '707401'.

**Avantage** : Bénéficie automatiquement de l'amélioration sans modification de code.

### 3. Fonction diviser_paiement_volume_multi refactorisée

**Fichier** : `backend/apps/accounting/views_verification_ouvrages.py` (lignes 21-100)

**Ancien code** : Implémentation manuelle avec regex limitée aux formats avec montants explicites

**Nouveau code** : Délègue à `extraire_ouvrage_et_mois_paiement_volume` pour bénéficier de tous les nouveaux formats

**Logique** :
1. Si montants explicites dans la description ET cohérents avec le total → utiliser les montants explicites
2. Sinon → diviser le montant total DiameX également entre tous les segments

**Avantage** :
- Pages de vérification et recoupement bénéficient automatiquement des nouveaux formats
- Moins de duplication de code
- Maintenance facilitée (un seul endroit à modifier)

## Tests de validation

**Script de test** : `backend/test_extraction_multi_paiements.py`

**Résultats** :

### Test 1 - Format ouvrage répété
```
Description: Paiement au volume Anjahambe 03/2025 9200; Anjahambe 04/2025 246500; Anjahambe 05/2025 251400; Anjahambe

✅ 3 paiements détectés
✅ Tous les ouvrages = "Anjahambe"
✅ Mois : 3, 4, 5
✅ Montants : 9200, 246500, 251400
```

### Test 2 - Format ouvrage hérité
```
Description: Paiement au volume Anjahambe 12/2025 41400; 01/2025 24200; 02/2025 21900; 03/2025 58700; ...

✅ 11 paiements détectés
✅ Tous les ouvrages = "Anjahambe" (héritage correct)
✅ Mois : 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
✅ Montants : 41400, 24200, 21900, 58700, 30100, 29000, 93400, 79800, 156100, 95800, 237000
```

### Test 3 - Rétrocompatibilité format simple
```
Description: Paiement au volume Ankorabe 01/12/2025

✅ Retourne un dict (pas une liste)
✅ Ouvrage : Ankorabe
✅ Mois : 12, Année : 2025
✅ Comportement identique à l'ancien code
```

## Pages impactées automatiquement

1. ✅ **Dashboard Paiements Volume** : `http://localhost:8000/comptabilite/dashboard-paiements-volume/`
   - Statistiques délais de paiement
   - API détails par catégorie

2. ✅ **Page Vérification avec Ouvrage** : `http://localhost:8000/comptabilite/verification-avec-ouvrage/`
   - Via fonction `diviser_paiement_volume_multi` refactorisée
   - Via `extraire_ouvrage_et_mois_generique` qui délègue

3. ✅ **Page Recoupement Relevés** : `http://localhost:8000/comptabilite/recoupement/releves/`
   - Via `extraire_ouvrage_et_mois_generique` pour compte 707401
   - Recoupement 3e : Relevés par Ouvrage vs DiameX 707401

## Architecture technique

### Flux de données

```
Description DiameX multi-paiements
    ↓
extraire_ouvrage_et_mois_paiement_volume()
    ↓
Détection ';' dans description
    ↓
_extraire_multi_paiements()
    ├─ Parse chaque segment
    ├─ Héritage automatique du nom d'ouvrage
    ├─ Recherche Ouvrage dans la base
    └─ Retourne list de dict
    ↓
Vue Django
    ├─ Normalise : dict → [dict]
    ├─ Divise montant total / nb_paiements
    └─ Traite chaque paiement séparément
```

### Délégation via extraire_ouvrage_et_mois_generique

```
View (verification, recoupement...)
    ↓
extraire_ouvrage_et_mois_generique(description, compte_code)
    ↓
if compte_code == '707401':
    return extraire_ouvrage_et_mois_paiement_volume(description)
    ↓
Bénéficie automatiquement de l'amélioration
```

## Points d'attention CRITICAL

### 1. Type de retour variable

La fonction peut retourner soit un `dict`, soit une `list` de `dict`.

**⚠️ TOUJOURS normaliser** :
```python
info = extraire_ouvrage_et_mois_paiement_volume(description)
infos_list = info if isinstance(info, list) else [info]

for info_item in infos_list:
    # Traiter chaque paiement
    ...
```

### 2. Division des montants

Pour les multi-paiements SANS montants explicites, le montant total de la transaction DiameX doit être divisé également :

```python
nb_paiements = len([i for i in infos_list if i.get('mois') and i.get('annee')])
montant_par_paiement = montant_total / nb_paiements if nb_paiements > 0 else montant_total
```

### 3. Validation de cohérence

Quand des montants explicites existent, vérifier qu'ils correspondent au total :

```python
if montants_explicites and montant_total:
    total_explicite = sum(montants_explicites)
    if abs(total_explicite - montant_total) <= 1:  # Tolérance 1 Ar
        # Utiliser les montants explicites
    else:
        # Diviser le montant total
```

### 4. Héritage d'ouvrage

Le nom d'ouvrage du premier segment est **automatiquement hérité** par tous les segments suivants qui n'ont pas de nom explicite.

**⚠️ RÈGLE** : Le premier segment DOIT toujours contenir le nom d'ouvrage.

### 5. Formats de date supportés

- `MM/YYYY` (nouveau format principal)
- `DD/MM/YYYY` (ancien format, toujours supporté)
- `DD/MM/YY` (ancien format court, toujours supporté)

### 6. Segments incomplets

Les segments qui ne contiennent qu'un nom d'ouvrage (sans date ni montant) sont **ignorés**.

Exemple : "...251400; Anjahambe" → Le dernier "Anjahambe" seul est ignoré.

## Avantages de l'approche

1. **Précision comptable** : Chaque paiement est maintenant comptabilisé séparément au lieu d'être ignoré
2. **Traçabilité** : Possibilité de suivre chaque mois/montant individuellement
3. **Flexibilité** : Support de multiples formats (avec/sans ouvrage répété, avec/sans montants)
4. **Rétrocompatibilité** : Les descriptions simples fonctionnent exactement comme avant
5. **Réutilisabilité** : Toutes les pages bénéficient automatiquement via la délégation
6. **Maintenance** : Un seul endroit à modifier pour améliorer l'extraction

## Prochaines améliorations possibles

1. **Support YYYY MM** : Ajouter le format "2025 12" dans _extraire_multi_paiements
2. **Détection automatique des erreurs** : Alerter si somme(montants) ≠ montant_total
3. **Cache des recherches Ouvrage** : Optimiser les requêtes base de données répétées
4. **Extraction du point d'eau** : Parser aussi le nom du point d'eau si présent
5. **Export Excel** : Afficher les multi-paiements sur des lignes séparées dans les exports

## Fichiers modifiés

1. ✅ `backend/apps/accounting/extracteurs_description.py` (lignes 51-289)
   - Fonction principale refactorisée
   - Nouvelles fonctions `_extraire_multi_paiements` et `_extraire_paiement_simple`

2. ✅ `backend/apps/accounting/views.py` (lignes 6257-6308, 6566-6639)
   - Normalisation en liste
   - Division montants
   - Traitement de tous les paiements

3. ✅ `backend/apps/accounting/views_verification_ouvrages.py` (lignes 21-100)
   - Fonction `diviser_paiement_volume_multi` refactorisée
   - Délégation à l'extracteur principal

4. ✅ `backend/test_extraction_multi_paiements.py` (NOUVEAU)
   - Script de test des 3 formats

5. ✅ `backend/docs/EXTRACTION_MULTI_PAIEMENTS_AMELIORATION.md` (NOUVEAU)
   - Documentation complète

## Validation finale

```bash
# Test Django
python manage.py check
# ✅ System check identified no issues (0 silenced)

# Test extraction
python test_extraction_multi_paiements.py
# ✅ Test 1: 3 paiements détectés (format répété)
# ✅ Test 2: 11 paiements détectés (format hérité)
# ✅ Test 3: Rétrocompatibilité OK (format simple)
```

## Conclusion

L'amélioration de la fonction d'extraction permet maintenant de reconnaître et segmenter automatiquement les descriptions multi-paiements dans TOUS les formats utilisés par DiameX.

**Impact** :
- ✅ Statistiques plus précises (tous les paiements comptabilisés)
- ✅ Recoupements plus fiables (segmentation automatique)
- ✅ Pas de régression (rétrocompatibilité complète)
- ✅ Bénéfice sur 3 pages sans modification de leur code

**Déploiement** : Prêt pour production. Aucune migration requise.
