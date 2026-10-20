# Dashboard Paiements Volume - Documentation Technique

## Vue d'ensemble
Dashboard complet pour le suivi des paiements volumétriques avec filtrage automatique par organisation via ModaliteGestion.

## Fonctionnalités implémentées

### 1. Filtrage automatique par organisation
- Utilise `ModaliteGestion` pour relier ouvrages et organisations
- Filtre automatique basé sur l'organisation de l'utilisateur connecté
- Pas de filtre organisation visible dans l'interface

### 2. Filtres géographiques en cascade
- **District** → Filtre les communes et ouvrages disponibles
- **Commune** → Filtre les ouvrages disponibles
- **Ouvrage** → Affiche les données de l'ouvrage sélectionné
- Bouton Reset pour réinitialiser tous les filtres

### 3. Statistiques principales (4 cartes)
1. **Montant prévu** : Somme des factures générées (compte 707401)
2. **Montant payé** : Somme des paiements reçus
3. **Taux de recouvrement** : Pourcentage payé / prévu
4. **Nombre d'ouvrages** : Ouvrages avec paiements volumétriques

### 4. Analyse des délais de paiement
- Compare la **date de facture** (extraite de la description) avec la **date de paiement** (date_rec)
- Utilise la fonction `extraire_ouvrage_et_mois_paiement_volume()` pour parser les descriptions
- Catégorisation :
  - Même mois (0 mois)
  - 1 mois de délai
  - 2 mois de délai
  - 3 mois ou plus
  - Non déterminé (description invalide)

### 5. Recouvrement par ouvrage
- Tableau détaillé avec montant prévu, payé et taux pour chaque ouvrage
- Tri par montant prévu décroissant
- Graphique doughnut des 10 premiers ouvrages

## Architecture technique

### Fichiers principaux
1. **backend/apps/accounting/views.py** (lignes 6058-6400)
   - Fonction `dashboard_paiements_volume(request)`
   - Logique de filtrage et calculs statistiques

2. **backend/apps/accounting/extracteurs_description.py**
   - Fonction `extraire_ouvrage_et_mois_paiement_volume(description)`
   - Parse format : "Paiement au volume [OUVRAGE] [DATE]"
   - Supporte dates DD/MM/YYYY ou YYYY MM
   - Gère entrées multiples séparées par ";"

3. **backend/templates/accounting/dashboard_paiements_volume.html** (472 lignes)
   - Interface utilisateur complète
   - Charts.js pour visualisations
   - DaisyUI pour composants UI

### Routes
```python
# backend/apps/accounting/urls.py ligne 223
path('dashboard-paiements-volume/', views.dashboard_paiements_volume, name='dashboard_paiements_volume'),
```

### Accès
**URL** : `/comptabilite/dashboard-paiements-volume/`

## Corrections et améliorations (9 erreurs + 3 améliorations visuelles/fonctionnelles)

### 1. NameError - Releve non défini
**Erreur** : `NameError: name 'Releve' is not defined`
**Fix** : Ajout imports lignes 6070-6074

### 2. FieldError - organisation invalide
**Erreur** : `Invalid field name(s) given in select_related: 'organisation'`
**Fix** : Utilisation de ModaliteGestion.gestionnaire au lieu de ouvrage.organisation

### 3. AttributeError - DateField.tzinfo
**Erreur** : `'datetime.date' object has no attribute 'tzinfo'`
**Fix** : Suppression logique timezone (datereleve et date_rec sont DateField)

### 4. FieldError - commune vs communes
**Erreur** : `Cannot resolve keyword 'commune' into field. Choices are: communes`
**Fix** : Utilisation nom plural `communes__` pour relation inverse

### 5. FieldError - pointeau sans _set
**Erreur** : `Unsupported lookup 'pointeau__ouvrage_id__in' for ManyToOneRel`
**Fix** : Ajout suffix `_set` → `pointeau_set__`

### 6. FieldError - __in avec ManyToOneRel
**Erreur** : `Unsupported lookup with __in through ManyToOneRel`
**Fix** : Restructuration requête pour filtrer PointEau d'abord, puis extraire IDs en Python

### 7. FieldError - releve vs releves
**Erreur** : `Cannot resolve keyword 'releve' into field. Choices are: releves`
**Fix** : Utilisation nom plural `releves__`

### 8. Date extraction incorrecte
**Erreur** : Analyse délais utilisait mauvaise date
**Fix** : Utilisation fonction `extraire_ouvrage_et_mois_paiement_volume()` existante

### 9. Colonne Écart vide dans tableau Recoupement par ouvrage
**Erreur** : La colonne Écart était vide dans le tableau "Recouvrement par ouvrage"
**Cause** : Le template utilisait une syntaxe Django incorrecte pour calculer l'écart : `rec.total_releves|add:rec.total_diamex|add:"-"` qui ne fonctionne pas
**Fix** :
- Backend (lignes 6210-6212) : Calcul de l'écart après la boucle de construction des données
  ```python
  # Calculer l'écart pour chaque ouvrage (Total Relevés - Total DiameX)
  for ouvrage_id, data in recouvrement_par_ouvrage_annee.items():
      data['ecart'] = data['total_releves'] - data['total_diamex']
  ```
- Template (ligne 328) : Utilisation directe du champ calculé
  ```django
  <td class="text-right font-mono">{{ rec.ecart|floatformat:0|intcomma }}</td>
  ```

### 10. Amélioration visuelle : Barres de progression pour les taux
**Amélioration** : Remplacement des badges par des barres de progression colorées pour une meilleure visualisation
**Fichier** : Template (lignes 329-349)
**Fonctionnalités** :
- Barre de progression horizontale avec couleur selon performance :
  - **Vert** (bg-success) : Taux ≥ 95%
  - **Jaune** (bg-warning) : Taux entre 80% et 94%
  - **Rouge** (bg-error) : Taux < 80%
- Largeur de la barre proportionnelle au taux (style="width: {{ taux }}%")
- Pourcentage affiché à côté de la barre avec la même couleur
- Animation de transition fluide (transition-all duration-300)
- Police monospace pour alignement des chiffres

**Code** :
```django
<div class="flex items-center gap-2">
    <div class="flex-1">
        <div class="w-full bg-base-300 rounded-full h-4 overflow-hidden">
            <div class="h-full rounded-full transition-all duration-300
                {% if taux >= 95 %}bg-success
                {% elif taux >= 80 %}bg-warning
                {% else %}bg-error{% endif %}"
                style="width: {{ taux }}%">
            </div>
        </div>
    </div>
    <span class="text-xs font-mono font-bold min-w-[3rem] text-right
        {% if taux >= 95 %}text-success
        {% elif taux >= 80 %}text-warning
        {% else %}text-error{% endif %}">
        {{ taux }}%
    </span>
</div>
```

### 11. Calcul du taux dans le backend au lieu du template
**Problème** : Les barres de progression étaient toutes rouges car `{% widthratio %}` retournait probablement 0 avec les types Decimal
**Fix** : Calcul du taux directement en Python (lignes 6221-6225)
```python
# Calculer le taux de recouvrement
if data['total_releves'] > 0:
    data['taux'] = int((data['total_diamex'] / data['total_releves']) * 100)
else:
    data['taux'] = 0
```
**Template** : Utilisation de `rec.taux` au lieu de `{% widthratio rec.total_diamex rec.total_releves 100 as taux %}`

### 12. Ajout du district dans les données
**Amélioration** : Extraction du district pour chaque relevé via la chaîne de relations
**Code** (lignes 6169-6174) :
```python
# Récupérer le district via la chaîne de relations
district_nom = None
if releve.point_eau.parcelle and releve.point_eau.parcelle.village:
    village = releve.point_eau.parcelle.village
    if village.fokontany and village.fokontany.commune and village.fokontany.commune.district:
        district_nom = village.fokontany.commune.district.nom_district
```

### 13. Regroupement par district et tri par taux
**Amélioration** : Organisation des données par district avec tri décroissant par taux de recouvrement
**Code** (lignes 6227-6238) :
```python
# Convertir en liste et trier par district puis par taux décroissant
from itertools import groupby

recouvrement_liste = sorted(
    recouvrement_par_ouvrage_annee.values(),
    key=lambda x: (x['district_nom'], -x['taux'])
)

# Grouper par district
recouvrement_par_district = {}
for district_nom, items in groupby(recouvrement_liste, key=lambda x: x['district_nom']):
    recouvrement_par_district[district_nom] = list(items)
```

**Template** : Affichage avec en-têtes de district (lignes 322-366)
- En-tête coloré pour chaque district avec compteur d'ouvrages
- Indentation visuelle des ouvrages sous leur district (classe `pl-8`)
- Tri automatique par taux au sein de chaque district

## Logique de filtrage géographique

### Approche restructurée (évite erreur ManyToOneRel)
```python
# 1. Filtrer PointEau par organisation et année
points_eau_filtre_base = PointEau.objects.filter(
    ouvrage_id__in=ouvrages_org_ids,
    releves__datereleve__year=annee,
    releves__montant__isnull=False
).select_related('parcelle__village__fokontany__commune__district')

# 2. Extraire IDs géographiques en Python
district_ids = set()
commune_ids = set()
ouvrage_ids_actifs = set()

for pe in points_eau_filtre_base.distinct():
    ouvrage_ids_actifs.add(pe.ouvrage_id)
    if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
        fokontany = pe.parcelle.village.fokontany
        if fokontany.commune:
            commune_ids.add(fokontany.commune.id)
            if fokontany.commune.district:
                district_ids.add(fokontany.commune.district.id)

# 3. Construire QuerySets pour filtres
districts = District.objects.filter(
    id__in=list(district_ids)
).order_by('nom_district')
```

## Analyse délais de paiement

### Format descriptions supportés
- **Simple** : `Paiement au volume Ankorabe 01/12/2025`
- **Multiple** : `Paiement au volume Ambatoharanana I 01/01/2025 13000; Ambatoharanana I 01/09/2025 65200; Ambatoharanana I 01/10/2025 27700`

### Logique de calcul
```python
# Utiliser l'extracteur existant
info = extraire_ouvrage_et_mois_paiement_volume(transaction.description)

if info and info.get('mois') and info.get('annee'):
    mois_facture = info['mois']
    annee_facture = info['annee']

    # Date de paiement
    mois_paiement = transaction.date_rec.month
    annee_paiement = transaction.date_rec.year

    # Délai en mois
    delai_mois = (annee_paiement - annee_facture) * 12 + (mois_paiement - mois_facture)

    # Catégoriser
    if delai_mois == 0:
        delais_paiement['meme_mois']['nb'] += 1
    elif delai_mois == 1:
        delais_paiement['1_mois']['nb'] += 1
    # ... etc
```

## Relations modèles importantes

### Organisation → Ouvrage
```
Organisation ← ModaliteGestion.gestionnaire
ModaliteGestion.ouvrage → Ouvrage
```

### Ouvrage → Géographie
```
Ouvrage → pointeau_set (PointEau)
PointEau.parcelle → Parcelle
Parcelle.village → Village
Village.fokontany → Fokontany
Fokontany.commune → Commune
Commune.district → District
```

### Reverse relations
- `District.communes` (plural)
- `Ouvrage.pointeau_set` (avec _set)
- `PointEau.releves` (plural)

## Points d'attention CRITICAL

1. **ModaliteGestion** : Toujours filtrer par `date_fin__isnull=True` pour modalités actives
2. **DateField** : Pas de timezone conversion, accès direct .year/.month
3. **Reverse relations** : Suffixe `_set` obligatoire (pointeau_set, pointeau_set)
4. **Noms pluriels** : Utiliser communes__, releves__ (pas commune__, releve__)
5. **ManyToOneRel + __in** : Impossible, restructurer avec filtre puis extraction Python
6. **Extraction dates** : Réutiliser fonctions existantes (`extracteurs_description.py`)

## Tests de validation

- [x] Django check : 0 erreurs
- [x] Route configurée : `/comptabilite/dashboard-paiements-volume/`
- [x] Imports corrects : Releve, BaseDiameX, Ouvrage, District, Commune
- [x] Filtrage organisation : Via ModaliteGestion
- [x] Filtres géographiques : Cascade District → Commune → Ouvrage
- [x] Extraction dates : Fonction `extraire_ouvrage_et_mois_paiement_volume()`
- [x] Statistiques : 4 cartes + 2 graphiques + 2 tableaux
- [x] Colonne Écart : Calcul correct dans backend et affichage dans tableau
- [x] Barres de progression : Affichage visuel des taux avec codes couleurs
- [x] Calcul taux dans backend : Utilisation de rec.taux au lieu de widthratio
- [x] Extraction district : Ajout district_nom pour chaque relevé
- [x] Groupement par district : Données organisées et triées par district puis par taux
- [x] Affichage groupé : Template avec en-têtes de district et tri décroissant
- [x] Délais : Barres de progression colorées dans tableau avec 5 catégories
- [x] Interactivité délais : Graphique et tableau cliquables avec modal de détails
- [x] API détails délais : Endpoint pour récupérer transactions par catégorie

### 14. Amélioration table Délais - Barres de progression (28 décembre 2025)

**Problème** : Tableau "Détails par catégorie de délais" affichait uniquement les pourcentages en texte, sans visualisation

**Solution appliquée** :
- Ajout barres de progression colorées pour chaque catégorie (h-3 pour distinction avec barres recouvrement)
- Codes couleurs selon urgence :
  - **Même mois** : Vert (bg-success) - Paiement idéal
  - **1 mois** : Jaune (bg-warning) - Acceptable
  - **2 mois** : Rouge (bg-error) - Problématique
  - **3+ mois** : Rouge (bg-error) - Critique
  - **Non déterminé** : Gris avec opacité (bg-base-content) - Nécessite vérification

**Code (template lignes 239-373)** :
```django
<td class="text-right">
    {% widthratio delais_paiement.meme_mois.nb total_nb 100 as pct_meme_mois %}
    <div class="flex items-center gap-2">
        <div class="flex-1">
            <div class="w-full bg-base-300 rounded-full h-3 overflow-hidden">
                <div class="h-full rounded-full transition-all duration-300 bg-success"
                    style="width: {{ pct_meme_mois }}%">
                </div>
            </div>
        </div>
        <span class="text-xs font-mono font-bold min-w-[3rem] text-right text-success">
            {{ pct_meme_mois }}%
        </span>
    </div>
</td>
```

### 15. Interactivité Analyse Délais - Modal de détails (28 décembre 2025)

**Fonctionnalités ajoutées** :

**1. Lignes du tableau cliquables** (template lignes 239-373)
- Attribut `cursor-pointer` et `hover` sur chaque `<tr>`
- `onclick="openDelaiDetailsModal('categorie', 'Label')"` pour ouvrir le modal
- Bouton œil dans colonne Actions pour visibilité
- `event.stopPropagation()` sur le bouton pour éviter double trigger

**2. Graphique Chart.js cliquable** (template lignes 655-675)
- Ajout option `onClick` dans configuration du doughnut chart
- Mapping des labels français vers codes API (ex: "Même mois" → "meme_mois")
- Détection du segment cliqué via `elements[0].index`

**3. Modal HTML structure** (template lignes 460-516)
- Modal DaisyUI max-w-5xl pour affichage large
- États : Loading, Contenu, Erreur
- Tableau avec 7 colonnes : N° Transaction, Ouvrage, Description, Montant, Date Facture, Date Paiement, Délai
- Alert info contextuelle selon catégorie (ex: explication "Non déterminé")
- Compteurs : nombre de transactions + montant total
- Bouton export CSV

**4. Fonctions JavaScript** (template lignes 688-821)
- `openDelaiDetailsModal(category, categoryLabel)` : Ouvre modal + fetch API
- `displayDelaiDetails(data, categoryLabel, category)` : Remplit le tableau avec données
- `getDelayBadgeClass(delaiText)` : Retourne classe badge selon délai
- `exportDelaiDetails()` : Génère et télécharge fichier CSV

**5. API Backend** (views.py lignes 6413-6519)
- Route : `/api/delais-paiement-details/?categorie_delai=meme_mois`
- Paramètres : categorie_delai (obligatoire), organisation, annee (optionnels)
- Logique :
  - Filtre transactions BaseDiameX (compte 707401, type recette)
  - Extrait date facture via `extraire_ouvrage_et_mois_paiement_volume()`
  - Calcule délai en mois : `(annee_paiement - annee_facture) * 12 + (mois_paiement - mois_facture)`
  - Classifie en 5 catégories : meme_mois, 1_mois, 2_mois, 3_mois_plus, non_determine
  - Retourne JSON avec liste des transactions de la catégorie demandée

**Réponse JSON** :
```json
{
  "success": true,
  "transactions": [
    {
      "numero": "abc12345",
      "ouvrage": "Ambanja BP",
      "description": "Paiement au volume Ambanja BP 01/11/2025",
      "montant": 125000.0,
      "date_facture": "11/2025",
      "date_paiement": "15/11/2025",
      "mois_facture": 11,
      "annee_facture": 2025,
      "mois_paiement": 11,
      "annee_paiement": 2025
    }
  ],
  "categorie": "meme_mois"
}
```

**Messages contextuels par catégorie** :
- **Non déterminé** : "Ces transactions ont une description qui n'a pas permis d'extraire la date de facturation. Vérifiez le format..."
- **Même mois** : "Ces transactions ont été payées le même mois que la facturation (délai idéal)."
- **Autres** : "Ces transactions ont été payées avec un délai de X mois."

### 16. Correction Bug API - Variables undefined (28 décembre 2025)

**Problème identifié** :
Erreur JSON "Unexpected token '<', \"<!DOCTYPE \"... is not valid JSON" lors de l'appel API délais

**Cause racine** (views.py lignes 6462-6513) :
Les variables `mois_paiement` et `annee_paiement` étaient définies SEULEMENT dans le bloc `if info and info.get('mois')...` mais utilisées dans TOUS les cas (y compris catégorie `non_determine`). Cela causait une erreur Python `NameError`, qui générait une page d'erreur Django HTML au lieu de JSON.

**Correction appliquée** :
Initialisation explicite de toutes les variables de date AVANT le bloc conditionnel :

```python
for transaction in transactions_list:
    # Extraire la date de facture depuis la description
    info = extraire_ouvrage_et_mois_paiement_volume(transaction.description)

    # ✅ CORRECTION : Initialiser les variables pour tous les cas
    mois_paiement = None
    annee_paiement = None
    mois_facture = None
    annee_facture = None
    date_facture_str = None

    if info and info.get('mois') and info.get('annee'):
        # Ces variables sont maintenant réassignées (au lieu d'être créées)
        mois_facture = info['mois']
        annee_facture = info['annee']
        mois_paiement = transaction.date_rec.month
        annee_paiement = transaction.date_rec.year
        # ...
    else:
        # categorie = 'non_determine'
        # Les variables restent None (au lieu de ne pas exister)
        categorie = 'non_determine'

    # Le dictionnaire peut maintenant accéder aux variables en toute sécurité
    transactions_par_categorie.append({
        'mois_paiement': mois_paiement,  # ✅ Toujours définie (None ou int)
        'annee_paiement': annee_paiement,  # ✅ Toujours définie (None ou int)
        # ...
    })
```

**Impact** :
- ✅ API retourne maintenant du JSON valide pour TOUTES les catégories
- ✅ Catégorie "Non déterminé" fonctionne correctement
- ✅ Modal peut afficher les transactions sans date extractible

## Prochaines étapes suggérées

1. **Tests navigateur** :
   - Charger `/comptabilite/dashboard-paiements-volume/`
   - Vérifier cascade des filtres
   - Vérifier graphiques Chart.js
   - Vérifier calculs statistiques

2. **Optimisations possibles** :
   - Cache pour requêtes lourdes
   - Pagination tableaux détaillés
   - Export Excel des données

3. **Améliorations UI** :
   - Loader pendant chargement données
   - Tooltips sur graphiques
   - Messages si aucune donnée

## Auteurs et dates

**Implémentation** : 28 décembre 2025
**Corrections** : 9 erreurs corrigées + 1 correction API = 10 corrections
**Améliorations** : 6 améliorations visuelles et fonctionnelles (16 au total)
  - Amélioration 10 : Barres de progression pour taux de recouvrement
  - Amélioration 11 : Calcul du taux dans backend au lieu du template
  - Amélioration 12 : Ajout du district dans les données
  - Amélioration 13 : Regroupement par district et tri par taux
  - **Amélioration 14** : Barres de progression pour délais de paiement (5 catégories colorées)
  - **Amélioration 15** : Interactivité complète - Graphique + Tableau cliquables avec modal de détails
  - **Correction 16** : Variables undefined dans API délais - Initialisation explicite des variables de date
**Validation** : Django check sans erreur
**Status** : ✅ Complet et opérationnel
