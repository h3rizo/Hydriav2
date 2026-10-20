# Module Paiements Cartes Sociales - Vue Hiérarchique

## Date : 16 décembre 2025

## Vue d'ensemble
Module de visualisation hiérarchique des paiements de cartes sociales, organisé par **Région → District → Commune** avec modal pour les détails.

## Fonctionnalités implémentées

### 1. Structure hiérarchique pliable (Accordéons)

**Niveau 1 - Région** :
- Accordéon DaisyUI collapse avec flèche
- Icône globe (fa-globe)
- Badge nombre de cartes
- Stats : Payées / Non payées / Taux %
- Fond gris clair (bg-base-200)

**Niveau 2 - District** :
- Accordéon imbriqué dans région
- Icône ville (fa-city)
- Badge nombre de cartes
- Stats : Payées / Non payées / Taux %
- Fond blanc (bg-base-100)
- Indent 4 (ml-4)

**Niveau 3 - Commune** :
- Tableau dans le district
- Colonnes : Commune, Cartes, Points d'Eau, Total, Payées, Non Payées, Taux, Action
- Icône marqueur (fa-map-marker-alt)
- Badges colorés pour chaque stat
- Radial progress pour taux de paiement
- Bouton "Détails" pour ouvrir modal

### 2. Modal détails commune

**Déclenchement** :
- Clic sur bouton "Détails" dans la ligne commune
- Fonction JavaScript : `openCommuneModal(communeId, communeNom)`

**Contenu du modal** :
- **Titre** : Nom commune (District, Région)
- **Stats** : 3 cartes (Total, Payées, Non Payées)
- **Tableau** : Liste des points d'eau avec détails
  - Colonnes : Point d'Eau, Ouvrage, Cartes, Total, Payées, Non Payées, Taux
  - Radial progress pour taux de paiement

**États du modal** :
- Loading : Spinner pendant chargement API
- Success : Affichage stats + tableau
- Error : Message d'erreur si échec

### 3. API détails commune

**Endpoint** : `GET /plannings/conso-cartes-sociales/api/commune/<commune_id>/`

**Paramètres** :
- `annee` : Année à filtrer (query param)

**Réponse JSON** :
```json
{
    "success": true,
    "commune": {
        "nom": "Ambanja",
        "district": "Ambanja",
        "region": "Diana"
    },
    "stats": {
        "nombre_total": 150,
        "nombre_payes": 120,
        "nombre_non_payes": 30,
        "taux_global": 80,
        "nombre_points_eau": 5,
        "nombre_cartes": 12
    },
    "points_eau": [
        {
            "id": "uuid",
            "nom": "PE Ambanja BP",
            "ouvrage": "Ambanja BP",
            "nombre_cartes": 3,
            "nombre_total": 50,
            "nombre_payes": 40,
            "nombre_non_payes": 10,
            "taux_paiement": 80
        }
    ]
}
```

## Avantages de la nouvelle structure

### Avant (structure plate)
- ❌ Table longue avec toutes les communes mélangées
- ❌ Pas de contexte géographique
- ❌ Nécessite scroll pour naviguer
- ❌ Redirection vers page complète pour détails

### Après (structure hiérarchique)
- ✅ Organisation géographique claire
- ✅ Navigation par région/district
- ✅ Accordéons pliables pour focus
- ✅ Modal rapide pour détails (pas de scroll)
- ✅ Stats agrégées à chaque niveau

## Structure backend

### Modification vue principale

**Fichier** : `backend/apps/planning/views_conso_cartes_sociales.py`

**Changement clé** :
```python
# Avant : data_par_commune = {commune_nom: {...}}
# Après : data_hierarchique = {
#     region_nom: {
#         'region': region_obj,
#         'districts': {
#             district_nom: {
#                 'district': district_obj,
#                 'communes': {
#                     commune_nom: {...}
#                 }
#             }
#         }
#     }
# }
```

**Agrégations** :
- Niveau commune : nombre_total, nombre_payes, nombre_non_payes, taux_paiement, nombre_cartes
- Niveau district : Somme des communes + taux_paiement
- Niveau région : Somme des districts + taux_paiement

### Nouvelle API

**Fonction** : `api_commune_details(request, commune_id)`

**Logique** :
1. Récupérer commune avec district et région
2. Filtrer points d'eau avec cartes sociales actives
3. Récupérer TOUS les relevés (pas de filtre volume_carte_sociale)
4. Filtrer par année (conversion timezone Madagascar)
5. Grouper par point d'eau
6. Calculer stats et taux de paiement

## Structure template

### Avant
```html
<table>
    {% for commune_nom, commune_data in data_par_commune.items %}
        <tr onclick="navigate_to_detail">...</tr>
    {% endfor %}
</table>
```

### Après
```html
<div class="space-y-3">
    {% for region_nom, region_data in data_hierarchique.items %}
    <div class="collapse">
        <div class="collapse-title"><!-- Région stats --></div>
        <div class="collapse-content">
            {% for district_nom, district_data in region_data.districts.items %}
            <div class="collapse">
                <div class="collapse-title"><!-- District stats --></div>
                <div class="collapse-content">
                    <table>
                        {% for commune_nom, commune_data in district_data.communes.items %}
                        <tr>
                            <td><button onclick="openCommuneModal()">Détails</button></td>
                        </tr>
                        {% endfor %}
                    </table>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endfor %}
</div>

<!-- Modal -->
<dialog id="modalDetailsCommune">
    <!-- Stats + Tableau points d'eau -->
</dialog>
```

## JavaScript

**Fonction principale** : `openCommuneModal(communeId, communeNom)`

**Étapes** :
1. Réinitialiser le modal (vider stats, tableau, erreurs)
2. Afficher spinner de chargement
3. Ouvrir le modal
4. Fetch API `/plannings/conso-cartes-sociales/api/commune/${communeId}/?annee=${anneeFilter}`
5. Masquer spinner
6. Si succès :
   - Mettre à jour titre avec localisation complète
   - Créer 3 stats cards (Total, Payées, Non Payées)
   - Remplir tableau avec points d'eau
   - Calculer couleur radial progress selon taux
7. Si erreur : Afficher message d'erreur

## URLs

**Route ajoutée** :
```python
path('conso-cartes-sociales/api/commune/<uuid:commune_id>/',
     views_conso_cartes_sociales.api_commune_details,
     name='api_commune_details')
```

## Fichiers modifiés

1. **backend/apps/planning/views_conso_cartes_sociales.py** (lignes 90-221, 250-367)
   - Modification : `gestion_conso_cartes_sociales_global()` pour structure hiérarchique
   - Ajout : `api_commune_details()` pour modal

2. **backend/apps/planning/urls.py** (ligne 106)
   - Ajout : Route API détails commune

3. **backend/templates/planning/conso_cartes_sociales_global.html** (lignes 133-398)
   - Remplacement : Table plate → Accordéons hiérarchiques
   - Ajout : Modal détails commune
   - Ajout : JavaScript `openCommuneModal()`

4. **backend/templates/base.html** (lignes 480, 220)
   - Ajout menu desktop : Tableaux & Rapports → Rapports & Analyses → "Paiements cartes sociales"
   - Ajout menu mobile : Rapports → "Paiements cartes sociales"

## Tests

### Vérification Django
```bash
cd backend && python manage.py check
# System check identified no issues (0 silenced)
```

### Tests fonctionnels à effectuer
- [ ] Accéder à `/plannings/conso-cartes-sociales/global/`
- [ ] Vérifier affichage hiérarchique Région → District → Commune
- [ ] Cliquer sur région → Expand/Collapse fonctionne
- [ ] Cliquer sur district → Expand/Collapse fonctionne
- [ ] Vérifier stats agrégées à chaque niveau (région, district)
- [ ] Cliquer sur "Détails" dans une commune
- [ ] Vérifier ouverture modal avec spinner
- [ ] Vérifier chargement stats + tableau points d'eau
- [ ] Vérifier fermeture modal (X ou backdrop)
- [ ] Tester avec filtres (année, région, district)

## Points d'attention CRITICAL

1. **Timezone** : Conversion obligatoire avec `tz_madagascar` pour filtrer par année
2. **Filtre volume_carte_sociale** : NE PAS utiliser `.filter(volume_carte_sociale__gt=0)` car toujours 0
3. **Structure imbriquée** : Utiliser `.items()` dans templates pour boucles dictionnaires
4. **Modal DaisyUI** : Utiliser `<dialog>` avec `.showModal()` en JS
5. **CSRF** : Pas nécessaire pour GET mais gérer fetch errors

## Prochaines améliorations possibles

1. **Recherche rapide** : Input pour chercher commune directement
2. **Export Excel** : Bouton export structure hiérarchique
3. **Graphiques** : Chart.js pour visualiser taux par région/district
4. **Filtres avancés** : Filtrer par taux de paiement (< 50%, 50-75%, > 75%)
5. **Tri** : Trier régions/districts par taux croissant/décroissant
6. **Impression** : Adapter vue impression pour structure hiérarchique
