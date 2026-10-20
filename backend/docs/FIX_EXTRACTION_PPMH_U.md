# Fix Extraction Indemnité PPMH avec Format _U_

**Date** : 29 décembre 2025
**Contexte** : Pages de vérification et recoupement comptable

## Problème identifié

Dans les pages de vérification comptable, certaines descriptions d'indemnités PPMH utilisent un format avec `_U_` suivi de numéros qui n'était pas reconnu par les patterns existants :

**Exemple de description problématique** :
- `_RAVONIARIMANANA Lucie_Indemnité PPMH_U_1_5000_Ampetsapetsa PPMH2`

**Symptôme** : L'ouvrage n'était pas correctement extrait à cause du format `_U_[num1]_[num2]_` qui ne correspondait à aucun pattern existant.

**Spécification utilisateur** : "le nom de l'ouvrage est après le dernier underscore"

## Cause

La fonction `extraire_indemnite_rbf_ppmh()` ne disposait pas de pattern pour reconnaître le format PPMH avec `_U_` :

```python
# Formats existants reconnus :
# Pattern 1c: Indemnité PPMH_[OUVRAGE] (classique)
# Ex: "_RAZAFINDRAVAO Pierette_Indemnité PPMH_Ambohijatovo PPMH"

# Format NON reconnu :
# Indemnité PPMH_U_1_5000_Ampetsapetsa PPMH2
#                ^^^^^^^^^^
#                Partie _U_[num]_[num]_ inconnue
```

Le découpage classique par underscore ne fonctionnait pas car la séquence `_U_1_5000_` créait trop de segments.

## Solution

Ajout d'un nouveau pattern `1c_U` spécifiquement pour le format PPMH avec `_U_` suivi de numéros :

```python
# Pattern 1c_U: Indemnité PPMH_U_[num1]_[num2]_[OUVRAGE]
# Ex: "_RAVONIARIMANANA Lucie_Indemnité PPMH_U_1_5000_Ampetsapetsa PPMH2"
# Format avec _U_ suivi de numéros, le nom de l'ouvrage est après le dernier underscore
# DOIT être testé AVANT Pattern 1c (plus spécifique - avec _U_)
pattern_ppmh_u = r'Indemnité\s+PPMH_U_\d+_\d+_(.+)$'
match_ppmh_u = re.search(pattern_ppmh_u, description, re.IGNORECASE)

if match_ppmh_u:
    ouvrage_nom = match_ppmh_u.group(1).strip()

    result['type_indemnite'] = 'PPMH'
    result['ouvrage_nom'] = ouvrage_nom

    # Chercher l'ouvrage
    try:
        ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
        if not ouvrage:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
        result['ouvrage_obj'] = ouvrage

        # Pour PPMH, récupérer automatiquement le point d'eau s'il n'y en a qu'un seul
        if ouvrage:
            points_eau = PointEau.objects.filter(ouvrage=ouvrage)
            if points_eau.count() == 1:
                result['point_eau_obj'] = points_eau.first()
    except:
        pass

    return result
```

### Détails du pattern regex

**Pattern** : `r'Indemnité\s+PPMH_U_\d+_\d+_(.+)$'`

**Explication** :
- `Indemnité\s+` : Le mot "Indemnité" suivi d'espaces
- `PPMH_U_` : Chaîne "PPMH_U_" littérale
- `\d+_\d+_` : Un ou plusieurs chiffres, underscore, un ou plusieurs chiffres, underscore
- `(.+)$` : Capture tout jusqu'à la fin de la ligne (le nom de l'ouvrage)

**Exemples de matching** :
- `Indemnité PPMH_U_1_5000_Ampetsapetsa PPMH2` → Capture : "Ampetsapetsa PPMH2"
- `Indemnité PPMH_U_2_10000_Test Ouvrage` → Capture : "Test Ouvrage"
- `Indemnité PPMH_U_123_999999_Mon Ouvrage` → Capture : "Mon Ouvrage"

**Ordre de test des patterns** : Pattern 1c_U est placé **AVANT** Pattern 1c (format classique) car il est plus spécifique.

## Résultats des tests

### Test 1 : `_RAVONIARIMANANA Lucie_Indemnité PPMH_U_1_5000_Ampetsapetsa PPMH2`

✅ **Résultat** :
- Ouvrage nom : `Ampetsapetsa PPMH2`
- Ouvrage obj : `Ampetsapetsa PPMH2` (objet trouvé dans la base)
- Type indemnité : `PPMH`
- Point eau obj : `None` (aucun point d'eau unique pour cet ouvrage)

### Test 2 : `_NOM Prénom_Indemnité PPMH_U_2_10000_Test Ouvrage`

✅ **Résultat** :
- Ouvrage nom : `Test Ouvrage`
- Ouvrage obj : `None` (ouvrage non trouvé dans la base - normal pour test)
- Type indemnité : `PPMH`

**Note** : L'ouvrage n'existe pas dans la base, mais le pattern extrait correctement le nom.

### Test 3 : `_RAZAFINDRAVAO Pierette_Indemnité PPMH_Ambohijatovo PPMH` (rétrocompatibilité)

✅ **Résultat** :
- Ouvrage nom : `Ambohijatovo`
- Ouvrage obj : `Ambohijatovo PPMH` (objet trouvé dans la base)
- Type indemnité : `PPMH`

**Note** : Le format classique sans `_U_` continue de fonctionner normalement via Pattern 1c.

## Impact

Cette amélioration permet de reconnaître les descriptions d'indemnités PPMH même lorsqu'elles contiennent la séquence `_U_[num1]_[num2]_`.

### Pages bénéficiaires

Toutes les pages qui utilisent `extraire_ouvrage_et_mois_generique()` avec le compte `621102` (Indemnités RBF/PPMH/BF) bénéficient automatiquement :

1. ✅ **Page Vérification avec ouvrage** (`/comptabilite/verification-avec-ouvrage/`)
2. ✅ **Page Recoupement relevés** (`/comptabilite/recoupement/releves/`)
3. ✅ **Dashboard paiements volume** (`/comptabilite/dashboard-paiements-volume/`)

### Cas d'usage typiques

**Format avec _U_** :
- `Indemnité PPMH_U_1_5000_Ampetsapetsa PPMH2`
- `Indemnité PPMH_U_2_10000_Soakoja AEPG`
- `Indemnité PPMH_U_3_7500_Village BP`

**Signification des numéros** :
- Premier numéro après `_U_` : Probablement quantité ou identifiant
- Deuxième numéro : Probablement montant ou tarif
- Nom après le dernier underscore : Nom de l'ouvrage

Tous ces cas sont maintenant gérés automatiquement.

## Fichier modifié

**Fichier** : `backend/apps/accounting/extracteurs_description.py`

**Emplacement** : Lignes 1702-1730

**Fonction** : `extraire_indemnite_rbf_ppmh(description)`

**Changements** :
1. Ajout Pattern 1c_U avant Pattern 1c (plus spécifique en premier)
2. Extraction du nom d'ouvrage après le dernier underscore
3. Même logique de recherche d'ouvrage que les autres patterns (exact match puis fuzzy)

## Tests de validation

- [x] Test format avec _U_ : `Indemnité PPMH_U_1_5000_Ampetsapetsa PPMH2`
- [x] Test format avec _U_ variations de chiffres
- [x] Test format classique sans _U_ (rétrocompatibilité)
- [x] Django check : 0 erreurs
- [x] Extraction objet ouvrage fonctionnelle
- [x] Type indemnité correctement défini à 'PPMH'

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

## Compatibilité

**✅ Rétrocompatibilité totale** : Les descriptions sans `_U_` continuent de fonctionner exactement comme avant via Pattern 1c.

**✅ Pas de régression** : Le nouveau pattern est testé en premier grâce à son placement avant Pattern 1c, mais si le format ne correspond pas, le système teste automatiquement les autres patterns.

## Documentation

**Scripts de test créés** :
- `backend/test_extraction_ppmh_u.py` - Tests unitaires pour ce fix

**Documentation associée** :
- `backend/docs/FIX_EXTRACTION_NETTOYAGE_BF_SANS_MONTANT.md` - Fix précédent pour Nettoyage BF
- `backend/docs/FIX_EXTRACTION_INSTALLATION_BP_CROCHETS.md` - Fix pour Installation BP avec crochets
- `backend/CLAUDE.md` - Contexte général du projet

## Prochaines améliorations possibles

1. **Extraction des numéros** : Stocker les valeurs numériques `[num1]` et `[num2]` pour traçabilité
2. **Validation du format** : Vérifier que les numéros correspondent à des valeurs attendues
3. **Statistiques** : Compter combien de paiements utilisent le format `_U_`
4. **Enrichissement** : Utiliser les numéros pour récupérer automatiquement quantité/tarif
