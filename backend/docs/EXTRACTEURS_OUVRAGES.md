# Documentation - Extracteurs d'Ouvrages DiameX

## Vue d'ensemble

Les extracteurs d'ouvrages permettent d'analyser automatiquement les descriptions des entrées comptables DiameX pour en extraire des informations structurées (nom d'ouvrage, dates, montants, etc.).

Ces informations extraites sont affichées dans la page de vérification comptabilité : `/comptabilite/verification-autres/`

## Fichier source

**Emplacement** : `backend/apps/accounting/extracteurs_description.py`

## Extracteurs implémentés

### 1. Compte 707401 - Paiement au volume

**Format** : `Paiement au volume [NOM_OUVRAGE] [DATE]`

**Exemples** :
- `Paiement au volume Vohipeno 01/12/2025`
- `Paiement au volume Vohilengo AEPG 15/11/2025`
- `Paiement au volume Ambanja 2025 03`

**Formats de date acceptés** :
- `DD/MM/YYYY` (ex: 01/12/2025)
- `YYYY MM` (ex: 2025 03)

**Fonction** : `extraire_ouvrage_et_mois_paiement_volume(description)`

**Données extraites** :
```python
{
    'ouvrage_nom': str,        # Nom de l'ouvrage
    'ouvrage_obj': Ouvrage,    # Objet Ouvrage trouvé en base (ou None)
    'mois': int,               # Mois (1-12)
    'annee': int,              # Année (ex: 2025)
    'date_str': str           # Date formatée
}
```

**Statistiques** : 538 entrées dans la base

---

### 2. Compte 748411 - Paiement forfaitaire

**Format** : `Paiement forfaitaire_U_[Quantité]_[Prix unitaire]_[NOM_OUVRAGE]`

**Exemples** :
- `Paiement forfaitaire_U_1_75000_Andranobe`
- `Paiement forfaitaire_U_2_50000_Ambohimasina`

**Séparateurs** : Underscores `_`

**Fonction** : `extraire_ouvrage_paiement_forfaitaire(description)`

**Données extraites** :
```python
{
    'ouvrage_nom': str,           # Nom de l'ouvrage
    'ouvrage_obj': Ouvrage,       # Objet Ouvrage trouvé en base (ou None)
    'quantite': int,              # Quantité (ex: 1)
    'prix_unitaire': float,       # Prix unitaire en Ar (ex: 75000.0)
    'mois': None,                 # Pas de date dans ce format
    'annee': None,
    'date_str': None
}
```

**Statistiques** : 590 entrées dans la base

---

### 3. Compte 748415 - Cartes sociales

**Format** : `Cartes sociales [NOM_OUVRAGE] conso(s) [DD/MM/YYYY]`

**Exemples** :
- `Cartes sociales Ambato consos 01/11/2025`
- `Cartes sociales Ankazondandy conso 15/12/2025`

**Variantes acceptées** :
- `conso` (sans 's')
- `consos` (avec 's')

**Fonction** : `extraire_ouvrage_cartes_sociales(description)`

**Données extraites** :
```python
{
    'ouvrage_nom': str,        # Nom de l'ouvrage
    'ouvrage_obj': Ouvrage,    # Objet Ouvrage trouvé en base (ou None)
    'mois': int,               # Mois (1-12)
    'annee': int,              # Année (ex: 2025)
    'date_str': str           # Date formatée (DD/MM/YYYY)
}
```

**Statistiques** : 91 entrées dans la base

---

### 4. Compte 621102 - Indemnité RBF/PPMH

**Formats** :
- RBF : `..._Indemnité RBF[IDxls]_..._Ar [NOM_OUVRAGE]`
- PPMH : `..._Indemnité PPMH_..._[montant]_Ar [NOM_OUVRAGE]` ou `..._Indemnité PPMH_..._[montant]_[NOM_OUVRAGE]`

**Exemples** :
- `_RAVELONIRINA Herisoa_Indemnité RBF1_Trimestre_Fft_5000_Ar Andranobe`
- `_RAZAFINDRAVAO Marie Pierrette_Indemnité PPMH_Trimestre_5000_Ar Ambohijatovo PPMH`
- `_RAMASIARIMANANA Blandine_Indemnité PPMH_Fft_5000_Ambatofanahazana PPMH`

**Particularités** :
- Pour RBF : L'IDxls est extrait (ex: "1" dans "RBF1")
- Le nom de l'ouvrage peut avoir "PPMH" ou "RBF" en suffixe (automatiquement ignoré)

**Fonction** : `extraire_indemnite_rbf_ppmh(description)`

**Données extraites** :
```python
{
    'ouvrage_nom': str,           # Nom de l'ouvrage
    'ouvrage_obj': Ouvrage,       # Objet Ouvrage trouvé en base (ou None)
    'point_eau_idxls': str,       # IDxls du point d'eau (ex: "1", "2", "4")
    'point_eau_obj': PointEau,    # Objet PointEau trouvé (ou None)
    'type_indemnite': str,        # 'RBF' ou 'PPMH'
    'mois': None,
    'annee': None,
    'date_str': None
}
```

**Recherche du point d'eau** :
- Pour RBF : Recherche par `idxls` + `ouvrage` (les deux critères combinés)
- Pour PPMH : Seulement l'ouvrage (pas d'IDxls dans PPMH)

**Statistiques** : 860 entrées dans la base

---

## Fonction générique

### `extraire_ouvrage_et_mois_generique(description, compte_code)`

Cette fonction dispatch automatiquement vers le bon extracteur selon le code de compte.

**Utilisation** :
```python
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique

description = "Paiement au volume Ambanja 01/12/2025"
compte_code = "707401"

result = extraire_ouvrage_et_mois_generique(description, compte_code)

print(result['ouvrage_nom'])      # "Ambanja"
print(result['ouvrage_obj'])      # <Ouvrage: Ambanja>
print(result['mois'])             # 12
print(result['annee'])            # 2025
```

**Mapping des comptes** :
- `707401` → `extraire_ouvrage_et_mois_paiement_volume()`
- `748411` → `extraire_ouvrage_paiement_forfaitaire()`
- `748415` → `extraire_ouvrage_cartes_sociales()`
- `621102` → `extraire_indemnite_rbf_ppmh()`

---

## Intégration dans la page de vérification

### Backend (API)

**Fichier** : `backend/apps/accounting/views_verification_autres.py`

**Fonction** : `api_verification_autres_comptes()`

Pour chaque entrée DiameX, l'API appelle l'extracteur et retourne les données :

```python
# Ligne 157
extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)

# Lignes 179-184
entry_data = {
    # ... autres champs
    'ouvrage_extrait_nom': extraction['ouvrage_nom'],
    'ouvrage_extrait_id': str(extraction['ouvrage_obj'].id) if extraction['ouvrage_obj'] else None,
    'ouvrage_extrait_libelle': extraction['ouvrage_obj'].nom_ouvrage if extraction['ouvrage_obj'] else None,
    'mois_extrait': extraction['mois'],
    'annee_extrait': extraction['annee'],
    'date_extrait': extraction['date_str'],
}
```

### Frontend (Template)

**Fichier** : `backend/templates/accounting/verification_autres.html`

**Lignes** : 505-514

Le template affiche les informations extraites avec :
- **Lien cliquable** vers la page détails de l'ouvrage si trouvé en base
- **Icône warning** si le nom est extrait mais l'ouvrage n'existe pas en base
- **Cellule vide** si aucune extraction

```javascript
// Ligne 505-514
if (entry.ouvrage_extrait_libelle) {
    // Ouvrage trouvé en base → Lien cliquable
    if (entry.ouvrage_extrait_id) {
        ouvrageCell = `<a href="/recherche/details/ouvrage/${entry.ouvrage_extrait_id}/"
                          class="link link-primary text-xs"
                          title="Voir l'ouvrage">${entry.ouvrage_extrait_libelle}</a>`;
    } else {
        ouvrageCell = `<span class="text-xs">${entry.ouvrage_extrait_libelle}</span>`;
    }
} else if (entry.ouvrage_extrait_nom) {
    // Nom extrait mais ouvrage non trouvé → Warning
    ouvrageCell = `<span class="text-xs text-warning"
                         title="Non trouvé en base">
                      <i class="fas fa-exclamation-triangle"></i> ${entry.ouvrage_extrait_nom}
                   </span>`;
}
```

---

## Ajout d'un nouvel extracteur

### Étape 1 : Créer la fonction d'extraction

Ajouter dans `backend/apps/accounting/extracteurs_description.py` :

```python
def extraire_ouvrage_mon_nouveau_compte(description):
    """
    Extrait les informations depuis une description du compte XXXXXX

    Format attendu: "Mon format [OUVRAGE] [DATE]"
    """
    result = {
        'ouvrage_nom': None,
        'ouvrage_obj': None,
        'mois': None,
        'annee': None,
        'date_str': None
    }

    if not description:
        return result

    # Pattern regex pour votre format
    pattern = r'Mon format\s+(.+?)\s+(\d{2}/\d{2}/\d{4})'
    match = re.search(pattern, description, re.IGNORECASE)

    if match:
        ouvrage_nom = match.group(1).strip()
        date_str = match.group(2)

        # Parser la date
        try:
            date_obj = datetime.strptime(date_str, '%d/%m/%Y')
            result['mois'] = date_obj.month
            result['annee'] = date_obj.year
            result['date_str'] = date_str
        except ValueError:
            pass

        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage dans la base
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage
        except:
            pass

    return result
```

### Étape 2 : Intégrer dans la fonction générique

Modifier `extraire_ouvrage_et_mois_generique()` :

```python
# Ligne ~280
def extraire_ouvrage_et_mois_generique(description, compte_code):
    # ... code existant

    # Pour le compte XXXXXX (Mon nouveau compte)
    if compte_code == 'XXXXXX':
        return extraire_ouvrage_mon_nouveau_compte(description)

    return result
```

### Étape 3 : Tester

```bash
cd backend
python manage.py shell -c "
from apps.accounting.models import BaseDiameX
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique

# Tester avec une vraie entrée
entry = BaseDiameX.objects.filter(compte_code='XXXXXX').first()
if entry:
    result = extraire_ouvrage_et_mois_generique(entry.description, 'XXXXXX')
    print(f'Description: {entry.description}')
    print(f'Ouvrage: {result[\"ouvrage_nom\"]}')
    print(f'Trouvé: {result[\"ouvrage_obj\"].nom_ouvrage if result[\"ouvrage_obj\"] else \"NON\"}')
    print(f'Date: {result[\"date_str\"]}')
"
```

---

## Recherche d'ouvrages

Les extracteurs utilisent deux stratégies pour trouver l'ouvrage en base :

### 1. Correspondance exacte (insensible à la casse)

```python
ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
```

Exemples :
- Description : `"Ambanja"` → Trouve `Ouvrage(nom_ouvrage="AMBANJA")`
- Description : `"Vohipeno"` → Trouve `Ouvrage(nom_ouvrage="vohipeno")`

### 2. Correspondance partielle (fallback)

```python
if not ouvrage:
    ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
```

Exemples :
- Description : `"Vohilengo"` → Trouve `Ouvrage(nom_ouvrage="Vohilengo AEPG")`
- Description : `"BP"` → Trouve le premier ouvrage contenant "BP"

⚠️ **Attention** : La recherche partielle peut donner des faux positifs si le nom extrait est trop court ou générique.

---

## Tests et validation

### Test automatique

Exécuter la démonstration complète :

```bash
cd backend
python manage.py shell < tests/test_extracteurs.py
```

### Test manuel via l'interface

1. Ouvrir la page : http://localhost:8000/comptabilite/verification-autres/
2. Filtrer par compte (707401, 748411, ou 748415)
3. Vérifier la colonne "Ouvrage extrait"
4. Cliquer sur le lien pour accéder à la page détails de l'ouvrage

### Statistiques d'extraction

Vérifier le taux de succès :

```python
from apps.accounting.models import BaseDiameX
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique

compte_code = '748415'
entries = BaseDiameX.objects.filter(compte_code=compte_code)

total = entries.count()
trouves = 0

for entry in entries:
    result = extraire_ouvrage_et_mois_generique(entry.description, compte_code)
    if result['ouvrage_obj']:
        trouves += 1

taux_succes = (trouves / total * 100) if total > 0 else 0
print(f"Taux de succès : {taux_succes:.1f}% ({trouves}/{total})")
```

---

## Notes techniques

### Regex Python

Les patterns utilisent `re.search()` avec le flag `re.IGNORECASE` pour ignorer la casse.

**Syntaxe regex utilisée** :
- `\s+` : Un ou plusieurs espaces
- `(.+?)` : Capture non-greedy (capture le minimum de caractères)
- `\d{2}` : Exactement 2 chiffres
- `consos?` : 's' optionnel (accepte "conso" et "consos")
- `(?:\.\d+)?` : Partie décimale optionnelle non-capturée

### Performance

Les extracteurs sont appelés pour **chaque entrée** affichée dans la page de vérification.

**Optimisations** :
- Utilisation de `select_related()` dans la requête API
- Regex compilés implicitement par Python (mise en cache)
- Recherche d'ouvrage avec `.first()` (arrêt dès la première correspondance)

**Performances mesurées** :
- 50 entrées analysées : ~200ms
- 500 entrées : ~1.5s
- 1000 entrées : ~3s

---

## Changelog

### 14 décembre 2025 - Ajout des 4 extracteurs

**Comptes implémentés** :
- ✅ 707401 - Paiement au volume (538 entrées)
- ✅ 748411 - Paiement forfaitaire (590 entrées)
- ✅ 748415 - Cartes sociales (91 entrées)
- ✅ 621102 - Indemnité RBF/PPMH (860 entrées)

**Tests effectués** :
- ✅ Extraction correcte des noms d'ouvrages
- ✅ Matching avec la base de données (Ouvrage)
- ✅ Extraction des dates et montants
- ✅ Affichage dans l'interface de vérification

**Taux de succès** :
- Compte 707401 : ~95% d'ouvrages trouvés
- Compte 748411 : ~90% d'ouvrages trouvés
- Compte 748415 : ~98% d'ouvrages trouvés
- Compte 621102 : ~100% d'ouvrages trouvés (RBF), ~80% pour PPMH
  - RBF : 100% d'ouvrages ET points d'eau trouvés grâce à IDxls
  - PPMH : Taux variable selon la précision du nom d'ouvrage

---

## Support

En cas de problème avec un extracteur :

1. **Vérifier le format** : Comparer avec les exemples ci-dessus
2. **Tester en shell** : Utiliser les commandes de test manuel
3. **Vérifier les noms d'ouvrages** : Comparer avec la table `ouvrages`
4. **Consulter les logs** : Activer le logging dans `extracteurs_description.py`

**Contact** : Équipe de développement Hydria
