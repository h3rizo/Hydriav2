# 📊 VÉRIFICATION COMPTABILITÉ - PAIEMENTS MULTI-SEGMENTS (28 décembre 2025)

## Vue d'ensemble

Module permettant de diviser automatiquement les lignes de paiement volumétrique concernant plusieurs ouvrages et périodes différents en lignes individuelles pour une meilleure lisibilité dans l'interface de vérification comptabilité.

## Problème résolu

**Contexte métier** : Un seul paiement peut concerner plusieurs ouvrages et/ou périodes différentes. L'ancien format stockait tout sur une seule ligne DiameX, rendant la vérification difficile.

**Exemple de description problématique** :
```
"Paiement au volume Antsahatanteraka 01/12/24 4300; Antsahatanteraka 01/01/2025 25900; Antsahatanteraka 01/02/2025 364500"
```

Dans cette description :
- 3 paiements différents pour le même ouvrage
- 3 mois différents (décembre 2024, janvier 2025, février 2025)
- 3 montants : 4 300 + 25 900 + 364 500 = 394 700 Ar (montant total IN)

**Problème** : Afficher cette ligne unique rend la vérification par ouvrage et par mois impossible.

## Solution implémentée

### 1. Nouveau format de description standardisé

**Format obligatoire** : `"Paiement au volume [Ouvrage] [Date] [Montant]; [Ouvrage] [Date] [Montant]; ..."`

**Règles** :
- Séparateur entre segments : `;` (point-virgule)
- Format date supporté : `DD/MM/YYYY` ou `DD/MM/YY`
- Montant : Nombre entier (sans séparateur de milliers)
- La somme des montants segments DOIT égaler le montant_in total de la ligne originale

**Exemples valides** :
```
Paiement au volume Antsahatanteraka 01/02/2025 84200; Antsahatanteraka 01/03/2024 296600
Paiement au volume Antsahatanteraka 01/12/24 4300; Antsahatanteraka 01/01/2025 25900; Antsahatanteraka 01/02/2025 364500
```

### 2. Parser automatique côté backend

**Fichier** : `backend/apps/accounting/views_verification_ouvrages.py`

**Fonction** : `diviser_paiement_volume_multi(description, compte_code, montant_total)` (lignes 21-114)

**Logique** :
1. Détecte si la description contient `;` ET commence par "Paiement au volume"
2. Parse chaque segment avec regex : `([^;]+?)\s+(\d{2}/\d{2}/\d{2,4})\s+(\d+)`
3. Extrait : Nom ouvrage, Date, Montant
4. Valide la somme des segments = montant total (tolérance 1 Ar)
5. Appelle `extraire_ouvrage_et_mois_generique()` pour chaque segment
6. Retourne liste de dict avec extraction complète

**Code clé** :
```python
def diviser_paiement_volume_multi(description, compte_code, montant_total):
    """
    Divise une description multi-segments en lignes individuelles
    """
    if not description or 'Paiement au volume' not in description:
        return []

    pattern = r'([^;]+?)\s+(\d{2}/\d{2}/\d{2,4})\s+(\d+)'
    segments = []

    # Parser chaque segment...

    # Vérifier cohérence montants
    somme_montants = sum(s['montant'] for s in segments)
    if abs(somme_montants - float(montant_total)) > 1:
        return []  # Échec validation

    return segments
```

### 3. Modification API liste de vérification

**Fichier** : `backend/apps/accounting/views_verification_ouvrages.py`

**Fonction** : `api_verification_list()` (lignes 286-376)

**Logique** :
```python
# Détection automatique des paiements multi-segments (compte 707401)
segments = []
if entry.compte_code == '707401' and entry.description and ';' in entry.description:
    segments = diviser_paiement_volume_multi(
        entry.description,
        entry.compte_code,
        entry.montant_in if is_entree else entry.montant_out
    )

# Si segments trouvés : créer une ligne par segment
if segments:
    for idx, segment in enumerate(segments):
        entry_data = {
            'id': f"{entry.id}_seg{idx}",  # ID unique composite
            'original_id': entry.id,
            'segment_index': idx,
            'is_segment': True,  # Flag pour indicateur visuel
            'description': segment['description_partielle'],
            'montant_in': segment['montant'],  # Montant du segment
            # ... extraction ouvrage/mois spécifique au segment
        }
        entries_analysees.append(entry_data)
else:
    # Pas de segments : traitement normal (une seule ligne)
    # ...
```

**Points CRITICAL** :
- ⚠️ ID composite : `"{entry.id}_seg{idx}"` pour unicité
- ⚠️ Flag `is_segment=True` pour différencier des lignes normales
- ⚠️ Chaque segment a son propre montant et extraction
- ⚠️ Si parsing échoue, fallback sur traitement normal

### 4. Support format date DD/MM/YY

**Fichier** : `backend/apps/accounting/extracteurs_description.py`

**Fonction** : `extraire_ouvrage_et_mois_paiement_volume()` (lignes 82-117)

**Modification** : Pattern regex étendu pour supporter année sur 2 chiffres

**AVANT (ne supportait que DD/MM/YYYY)** :
```python
pattern1 = r'Paiement au volume\s+(.+?)\s+(\d{2}/\d{2}/\d{4})'
```

**APRÈS (supporte DD/MM/YYYY et DD/MM/YY)** :
```python
pattern1 = r'Paiement au volume\s+(.+?)\s+(\d{2}/\d{2}/\d{2,4})'

# Parser avec les deux formats
if len(date_str) == 10:  # DD/MM/YYYY
    date_obj = datetime.strptime(date_str, '%d/%m/%Y')
elif len(date_str) == 8:  # DD/MM/YY
    date_obj = datetime.strptime(date_str, '%d/%m/%y')
```

**Raison** : Les descriptions utilisent parfois des années abrégées (ex: `01/12/24` au lieu de `01/12/2024`)

### 5. Indicateur visuel interface utilisateur

**Fichier** : `backend/templates/accounting/verification_par_ouvrage.html`

**Modification** : Badge orange avec icône ciseaux pour identifier les lignes segmentées

**Code JavaScript** (lignes 570-573) :
```javascript
// Badge ligne segmentée (pour les paiements multi-segments)
const segmentBadge = entry.is_segment === true
    ? `<span class="badge badge-warning badge-sm gap-1 ml-2"
             title="Ligne divisée depuis un paiement multi-segments. Segment ${entry.segment_index + 1}">
         <i class="fas fa-scissors"></i> Segment ${entry.segment_index + 1}
       </span>`
    : '';
```

**Affichage** (lignes 614-619) :
```html
<td class="max-w-md whitespace-normal break-words">
    <div class="flex flex-col gap-1">
        <span>${entry.description || '-'}</span>
        ${segmentBadge}
    </div>
</td>
```

**Résultat visuel** :
```
Description : Paiement au volume Antsahatanteraka 01/12/24
Badge       : [✂ Segment 1] (orange)

Description : Paiement au volume Antsahatanteraka 01/01/2025
Badge       : [✂ Segment 2] (orange)

Description : Paiement au volume Antsahatanteraka 01/02/2025
Badge       : [✂ Segment 3] (orange)
```

**Avantages** :
- ✅ Identification immédiate des lignes segmentées
- ✅ Numéro de segment visible (Segment 1, 2, 3...)
- ✅ Tooltip explicatif au survol
- ✅ Badge orange DaisyUI avec icône ciseaux (`fa-scissors`)

## Workflow utilisateur

### Scénario complet

**1. Saisie dans DiameX (Access)** :
```
Date    : 01/02/2025
Compte  : 707401
Prog    : SOAKOJA
Description : Paiement au volume Antsahatanteraka 01/12/24 4300; Antsahatanteraka 01/01/2025 25900; Antsahatanteraka 01/02/2025 364500
Montant IN : 394700
```

**2. Import depuis DiameX vers Hydria** :
- La ligne est stockée TELLE QUELLE dans la table `BaseDiameX`
- Aucune modification du format original

**3. Consultation dans page de vérification** (`http://localhost:8000/comptabilite/verification-avec-ouvrage/`) :

**Backend automatique** :
- Détecte compte 707401 + `;` dans description
- Parse et valide les 3 segments
- Somme : 4 300 + 25 900 + 364 500 = 394 700 ✅ (= montant IN)
- Crée 3 entry_data avec IDs uniques

**Frontend affiche 3 lignes distinctes** :

| Date | Type | Description | Ouvrage | Mois | Montant |
|------|------|-------------|---------|------|---------|
| 01/02/25 | Entrée | Paiement au volume Antsahatanteraka 01/12/24<br>[✂ Segment 1] | Antsahatanteraka | Déc 2024 | 4 300 |
| 01/02/25 | Entrée | Paiement au volume Antsahatanteraka 01/01/2025<br>[✂ Segment 2] | Antsahatanteraka | Jan 2025 | 25 900 |
| 01/02/25 | Entrée | Paiement au volume Antsahatanteraka 01/02/2025<br>[✂ Segment 3] | Antsahatanteraka | Fév 2025 | 364 500 |

**4. Vérification par ouvrage et par mois** :
- Chaque ligne est maintenant vérifiable indépendamment
- Extraction ouvrage : ✅ Antsahatanteraka trouvé en base
- Extraction mois : ✅ Décembre 2024, Janvier 2025, Février 2025
- Montants : ✅ Correspond aux relevés de chaque mois

## Validation et tests

### Cas de test 1 : 2 segments, même ouvrage, mois différents
**Input** :
```
Description: "Paiement au volume Antsahatanteraka 01/02/2025 84200; Antsahatanteraka 01/03/2024 296600"
Montant IN: 380800
```

**Output attendu** : 2 lignes
- Segment 1 : Antsahatanteraka, Février 2025, 84 200 Ar
- Segment 2 : Antsahatanteraka, Mars 2024, 296 600 Ar

**Validation** : ✅ 84 200 + 296 600 = 380 800 Ar

### Cas de test 2 : 3 segments, année abrégée
**Input** :
```
Description: "Paiement au volume Antsahatanteraka 01/12/24 4300; Antsahatanteraka 01/01/2025 25900; Antsahatanteraka 01/02/2025 364500"
Montant IN: 394700
```

**Output attendu** : 3 lignes
- Segment 1 : Antsahatanteraka, Décembre 2024, 4 300 Ar
- Segment 2 : Antsahatanteraka, Janvier 2025, 25 900 Ar
- Segment 3 : Antsahatanteraka, Février 2025, 364 500 Ar

**Validation** : ✅ 4 300 + 25 900 + 364 500 = 394 700 Ar

### Cas de test 3 : Format invalide (fallback)
**Input** :
```
Description: "Paiement au volume Antsahatanteraka 2025"
Montant IN: 50000
```

**Output attendu** : 1 ligne normale (pas de segmentation)
- Raison : Pas de `;` dans la description
- Traitement : Normal, comme avant

### Cas de test 4 : Montants ne correspondent pas (fallback)
**Input** :
```
Description: "Paiement au volume X 01/01/25 100; Y 01/02/25 200"
Montant IN: 500
```

**Output attendu** : 1 ligne normale (pas de segmentation)
- Raison : 100 + 200 = 300 ≠ 500 Ar
- Validation échouée → fallback sur traitement normal

## Points d'attention CRITICAL

### 1. Compte concerné
⚠️ **Seulement le compte 707401** (Paiement au volume) est traité
- Autres comptes : Traitement normal, pas de parsing multi-segments
- Raison : Format spécifique à ce type de transaction

### 2. Validation montants OBLIGATOIRE
⚠️ La somme des segments DOIT égaler le montant total (tolérance 1 Ar)
- Si validation échoue → fallback sur traitement normal
- Évite les erreurs de saisie dans la description

### 3. Format description STRICT
⚠️ Respecter exactement : `"Paiement au volume [Ouvrage] [Date] [Montant]; ..."`
- Séparateur : `;` (point-virgule avec espace après)
- Date : DD/MM/YYYY ou DD/MM/YY
- Montant : Entier, sans séparateur de milliers

### 4. ID composite pour unicité
⚠️ Les segments ont des IDs de type `"{original_id}_seg{index}"`
- Exemple : `"12345_seg0"`, `"12345_seg1"`, `"12345_seg2"`
- Permet de différencier les segments issus de la même ligne originale
- Important pour les actions (modifier, supprimer) qui utilisent l'ID

### 5. Extraction ouvrage par segment
⚠️ Chaque segment a sa propre extraction d'ouvrage et mois
- Un segment peut avoir un ouvrage différent d'un autre segment
- Permet la vérification indépendante par ouvrage/mois

## Fichiers modifiés

### Backend
1. **`apps/accounting/views_verification_ouvrages.py`**
   - Ajout fonction `diviser_paiement_volume_multi()` (lignes 21-114)
   - Modification `api_verification_list()` pour détecter et diviser (lignes 286-376)

2. **`apps/accounting/extracteurs_description.py`**
   - Support format date DD/MM/YY dans `extraire_ouvrage_et_mois_paiement_volume()` (lignes 82-117)

### Frontend
3. **`templates/accounting/verification_par_ouvrage.html`**
   - Ajout badge segment dans affichage JavaScript (lignes 570-573, 614-619)

## Améliorations futures possibles

1. **Support autres comptes** : Étendre le parsing à d'autres comptes si besoin métier
2. **Interface de saisie guidée** : Formulaire pour créer automatiquement le format multi-segments
3. **Validation temps réel** : Checker la somme des montants lors de la saisie
4. **Export Excel** : Permettre export avec segmentation visible
5. **Regroupement visuel** : Afficher les segments d'une même ligne groupés ensemble
6. **Statistiques** : Compter le nombre de paiements multi-segments dans les stats globales

## Documentation associée

- Guide timezone : `backend/TIMEZONE_GUIDE.md`
- Module recoupements : `backend/docs/RECOUPEMENT_FORFAITAIRES_AMELIORATIONS.md`
- Charte de vérification : Module intégré dans `apps/accounting/charte_verification.py`

## ✅ RÉSULTAT FINAL

**Le système de paiements multi-segments est maintenant entièrement fonctionnel avec :**

✅ **Parser automatique** côté backend pour diviser les lignes
✅ **Support format date DD/MM/YY** en plus de DD/MM/YYYY
✅ **Validation montants** automatique avec tolérance 1 Ar
✅ **Indicateur visuel** badge orange avec numéro de segment
✅ **Extraction ouvrage/mois** indépendante par segment
✅ **Fallback intelligent** si parsing échoue (traitement normal)
✅ **ID composite unique** pour chaque segment
✅ **Workflow transparent** pour l'utilisateur
✅ **Intégration recoupement** - Application automatique dans le 3e recoupement (Relevés vs DiameX 707401)

**Accessible via** :
- Comptabilité > Vérification - Comptes avec Ouvrage (`http://localhost:8000/comptabilite/verification-avec-ouvrage/`)
- Comptabilité > Recoupement Relevés > 3e recoupement (`http://localhost:8000/comptabilite/recoupement/releves/`)

**Page de test** : Filtrer par compte 707401 pour voir les paiements multi-segments

## 🔄 INTÉGRATION DANS LE RECOUPEMENT RELEVÉS (28 décembre 2025)

### Vue d'ensemble
La logique de segmentation a été étendue au **3e recoupement** (Relevés vs DiameX 707401) pour garantir que les paiements multi-segments sont correctement attribués aux bons ouvrages et aux bonnes périodes.

### Modifications apportées

**Fichier backend** : `backend/apps/accounting/views.py` (lignes 4650-4693)

**Logique implémentée** :
1. Détection automatique des paiements multi-segments (contient `;`)
2. Appel à `diviser_paiement_volume_multi()` pour parser les segments
3. Attribution de chaque segment au bon groupe (ouvrage_id, année, mois)
4. Fallback sur traitement normal si pas de segments

**Code clé** :
```python
# Pour chaque transaction, vérifier si multi-segments
for entry in diamex_707401:
    # Détection des paiements multi-segments (contient ';')
    segments = []
    if entry.description and ';' in entry.description:
        segments = diviser_paiement_volume_multi(
            entry.description,
            entry.compte_code,
            entry.montant_in if entry.montant_in else 0
        )

    if segments:
        # Traiter chaque segment séparément
        for segment in segments:
            extraction = segment['extraction']

            # Vérifier si l'ouvrage du segment correspond à celui du groupe
            if extraction['ouvrage_obj'] and extraction['ouvrage_obj'].id == ouvrage_id:
                # Vérifier que le mois/année du segment correspondent
                mois_ok = True
                if extraction['mois'] and extraction['annee']:
                    mois_ok = (extraction['mois'] == mois and extraction['annee'] == annee)

                if mois_ok:
                    # Ce segment correspond à cet ouvrage/mois
                    montant_segment = Decimal(str(segment['montant']))
                    data['total_diamex'] += montant_segment
                    data['nb_transactions_diamex'] += 1
    else:
        # Traitement normal pour les entrées non segmentées
        # ... code existant ...
```

**Fichier frontend** : `backend/templates/accounting/recoupement_releves.html` (ligne 1007)

**Note informative ajoutée** :
> **Paiements multi-segments :** Les paiements DiameX contenant plusieurs ouvrages/périodes (format avec `;`) sont automatiquement segmentés. Chaque segment est attribué à la bonne période et au bon ouvrage.

### Exemple de fonctionnement

**Paiement multi-segments dans DiameX** :
```
Description: "Paiement au volume Antsahatanteraka 01/12/24 4300; Antsahatanteraka 01/01/2025 25900; Antsahatanteraka 01/02/2025 364500"
Montant IN: 394700 Ar
```

**Résultat dans le 3e recoupement** :
- **Groupe (Antsahatanteraka, 2024, 12)** : +4 300 Ar
- **Groupe (Antsahatanteraka, 2025, 01)** : +25 900 Ar
- **Groupe (Antsahatanteraka, 2025, 02)** : +364 500 Ar

**Avantages** :
- Précision maximale des recoupements par période
- Évite les faux écarts dus à l'attribution incorrecte
- Cohérence avec la page de vérification

---

## 🔍 MODAL DE DÉTAILS DU 3E RECOUPEMENT

### Vue d'ensemble
Un modal interactif permet de visualiser en détail les transactions DiameX et les relevés pour une période et un ouvrage donnés, facilitant l'analyse des écarts.

### Accès au modal

**Depuis le 3e recoupement** :
1. Naviguer vers le 3e recoupement (Relevés vs DiameX 707401)
2. Cliquer sur l'icône œil (👁️) dans la colonne "Actions" d'une ligne de période
3. Le modal s'ouvre avec les détails de cette période

### Structure du modal

**Layout en 2 colonnes** :

**Colonne GAUCHE - Transactions DiameX (707401)** :
- Date de la transaction
- Description complète (avec badge "Segment" si multi-segment)
- Montant attribué à cette période
- Programme (Prog)
- **Bouton scan** : Ouvre le fichier PDF scanné via le serveur

**Colonne DROITE - Relevés de compteurs** :
- IDXLS (identifiant relevé)
- Nom du point d'eau
- Date du relevé
- Index ancien → nouvel index
- Consommation (m³)
- Montant facturé

**Statistiques du recoupement** :
- Nombre de transactions DiameX + Total
- Nombre de relevés + Total
- **Écart** (coloré : vert = 0, orange < 1000, rouge ≥ 1000)

### Fonctionnalités CRITICAL

**1. Gestion multi-segments** :
```javascript
// Dans openDetailsModal3e()
data.transactions_diamex.forEach(trans => {
    // Badge affiché si transaction segmentée
    ${trans.is_segment ? '<span class="badge badge-info badge-xs ml-2">Segment</span>' : ''}
});
```

**2. Boutons scan fonctionnels** :
```javascript
// Utilise la fonction openScanViaServer() existante
${trans.scan_path ? `
    <button onclick="openScanViaServer('${trans.scan_path}')" class="btn btn-xs btn-success btn-circle">
        <i class="fas fa-file-pdf"></i>
    </button>
` : '<span class="text-base-content/30">-</span>'}
```

**3. Chargement asynchrone** :
- Spinner affiché pendant le fetch API
- Gestion d'erreurs avec message clair
- Mise à jour dynamique des tableaux

### API Backend

**Endpoint** : `GET /comptabilite/recoupement/releves/api/details-3e/`

**Paramètres** :
- `ouvrage_id` : UUID de l'ouvrage
- `annee` : Année (ex: 2025)
- `mois` : Mois (ex: 1 pour janvier)

**Réponse JSON** :
```json
{
    "success": true,
    "ouvrage": {
        "id": "uuid",
        "nom": "Antsahatanteraka"
    },
    "periode": {
        "annee": 2025,
        "mois": 1,
        "label": "Janvier 2025"
    },
    "transactions_diamex": [
        {
            "id": 123,
            "date_rec": "05/01/2025",
            "description": "Paiement au volume Antsahatanteraka 01/01/2025 25900",
            "montant_in": 25900.0,
            "prog": "SOAKOJA",
            "scan": "./Scans/2025/facture.pdf",
            "scan_path": "C:/Bases/DiameX/Scans/2025/facture.pdf",
            "is_segment": true,
            "rec": "001"
        }
    ],
    "releves": [
        {
            "id": "uuid",
            "idxls": "R-001",
            "point_eau": "PE Tanambao",
            "datereleve": "15/01/2025",
            "index_ancien": 120,
            "nouvelindex": 145,
            "consommation": 25.0,
            "montant": 12500.0,
            "numeroDiameX": "",
            "baseDiameX": ""
        }
    ],
    "stats": {
        "nb_transactions": 1,
        "total_diamex": 25900.0,
        "nb_releves": 1,
        "total_releves": 12500.0,
        "ecart": 13400.0
    }
}
```

### Avantages du modal

1. **Comparaison visuelle** : Côte à côte, DiameX vs Relevés
2. **Traçabilité complète** : Accès aux scans pour vérification
3. **Détection rapide des écarts** : Statistiques colorées
4. **Support multi-segments** : Badge visuel + montants segmentés
5. **Interface responsive** : S'adapte mobile/tablette/desktop

### Exemple d'utilisation

**Cas concret** : Écart de 13 400 Ar détecté pour Antsahatanteraka en janvier 2025

1. Clic sur l'icône œil dans le 3e recoupement
2. Le modal s'ouvre et montre :
   - **GAUCHE** : 1 transaction DiameX de 25 900 Ar (badge "Segment")
   - **DROITE** : 1 relevé de 12 500 Ar
3. L'utilisateur constate que le relevé ne couvre qu'une partie du paiement
4. Clic sur le bouton scan pour vérifier le document source
5. L'écart de 13 400 Ar est confirmé et peut être investigué

**Actions possibles après analyse** :
- Vérifier s'il manque des relevés dans la base
- Contrôler si le paiement DiameX correspond bien à cette période
- Signaler une anomalie si l'écart est incohérent

### Points d'attention CRITICAL (corrections appliquées)

**1. Champs du modèle PointEau** :
- ⚠️ **CRITICAL** : Le champ `idxls` est un attribut du modèle `PointEau`, PAS du modèle `Releve`
- ⚠️ **CRITICAL** : Le modèle `PointEau` n'a PAS de champ `nom`, utiliser `code_point_eau` à la place
- ⚠️ Accès correct aux champs :
  ```python
  'idxls': releve.point_eau.idxls if releve.point_eau and releve.point_eau.idxls else '-'
  'point_eau': releve.point_eau.code_point_eau if releve.point_eau and releve.point_eau.code_point_eau else '-'
  ```
- ⚠️ Code backend (views.py lignes 5845-5846)

**1bis. Champs du modèle BaseDiameX** :
- ⚠️ **CRITICAL** : Le modèle `BaseDiameX` n'a PAS de champ `numero`, utiliser `rec` à la place
- ⚠️ Le champ `rec` contient le numéro de pièce/transaction
- ⚠️ Accès correct : `entry.rec or ''`
- ⚠️ Code backend (views.py ligne 5930)

**2. Structure complète des données relevé** :
- `id` : UUID du relevé
- `idxls` : Identifiant du point d'eau (via `point_eau.idxls`)
- `point_eau` : Code du point d'eau (via `point_eau.code_point_eau`)
- `datereleve` : Date du relevé (format DD/MM/YYYY)
- `index_ancien` : Ancien index du compteur (via `ancienindex`)
- `nouvelindex` : Nouvel index du compteur
- `consommation` : Volume consommé (m³)
- `montant` : Montant facturé (Ar)
- `numeroDiameX` / `baseDiameX` : Traçabilité comptable

**3. Décalage de dates et tri par IDXLS** :

**CRITICAL - Décalage de dates (Relevé → Facturation)** :
```python
from datetime import datetime
from dateutil.relativedelta import relativedelta

# La date de facturation = mois SUIVANT le relevé
# Ex: Relevé décembre 2024 → Facturé janvier 2025
# Donc pour les factures de janvier 2025, on cherche les relevés de décembre 2024
date_facturation = datetime(annee, mois, 1)
date_releve = date_facturation - relativedelta(months=1)

releves = Releve.objects.filter(
    montant__isnull=False,
    montant__gt=0,
    point_eau__ouvrage_id=ouvrage_id,
    datereleve__year=date_releve.year,  # Année du relevé (mois précédent)
    datereleve__month=date_releve.month  # Mois du relevé (mois précédent)
).select_related('point_eau', 'point_eau__type_point_eau')
```

**Tri numérique par IDXLS et affichage avec icônes** :
```python
# Ajouter un champ numérique pour tri correct + nom abonné + type
idxls_str = releve.point_eau.idxls if releve.point_eau and releve.point_eau.idxls else '-'
nom_abonne = releve.point_eau.nomabonne or '-' if releve.point_eau else '-'
type_point_eau = releve.point_eau.type_point_eau.nom_type if releve.point_eau and releve.point_eau.type_point_eau else ''

releves_data.append({
    'idxls': idxls_str,
    'idxls_num': int(idxls_str) if idxls_str.isdigit() else 999999,  # Pour tri numérique
    'nom_abonne': nom_abonne,
    'type_point_eau': type_point_eau,  # Pour affichage icônes (Kiosque, BI volume, BP)
    # ... autres champs
})

# Trier par IDXLS numérique (pas alphabétique)
releves_data.sort(key=lambda x: x['idxls_num'])
```

**Affichage avec icônes selon type** :
```javascript
// Frontend - Afficher icône selon le type
let icon = '';
if (type.toLowerCase() === 'kiosque') {
    icon = '<i class="fas fa-store text-info mr-1" title="Kiosque"></i>';
} else if (type.toLowerCase() === 'bi volume') {
    icon = '<i class="fas fa-faucet text-primary mr-1" title="BI volume"></i>';
} else if (type.toLowerCase() === 'bp') {
    icon = '<i class="fas fa-home text-success mr-1" title="BP"></i>';
}
// Affichage : ${icon}${releve.nom_abonne}
```

- ⚠️ **CRITICAL** : Le filtre sur `datereleve` utilise le **mois précédent** (relevé) et non le mois de facturation
- ⚠️ **CRITICAL** : Le tri par IDXLS doit être **numérique** (1, 2, 10, 20) et non alphabétique (1, 10, 2, 20)
- ⚠️ **CRITICAL** : Colonne affiche **Nom Abonné** (pas code point d'eau) avec icône de type
- ⚠️ Optimise les requêtes en préchargeant les relations `point_eau` et `point_eau__type_point_eau`
- ⚠️ Icônes : Kiosque (store), BI volume (faucet), BP (home)
- ⚠️ Code backend (views.py lignes 5862-5901)
- ⚠️ Code frontend (recoupement_releves.html lignes 1606-1629)
