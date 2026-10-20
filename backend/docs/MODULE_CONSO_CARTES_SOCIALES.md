# Module Suivi des Consommations Cartes Sociales

## 📋 Vue d'ensemble

Module permettant de suivre et analyser les volumes d'eau gratuits accordés aux bénéficiaires de cartes sociales. Le système affiche les consommations par commune, par ouvrage et par point d'eau, avec une vue mensuelle détaillée.

## 🎯 Objectif

Suivre les **volumes carte sociale** (champ `volume_carte_sociale` du modèle `Releve`) - c'est-à-dire les volumes d'eau accordés gratuitement aux familles bénéficiaires de cartes sociales.

## 🔍 Pages disponibles

### 1. Vue Globale par Commune
**URL** : `/plannings/conso-cartes-sociales/global/`
**Fonction** : `gestion_conso_cartes_sociales_global()`

**Affichage** :
- Statistiques globales (volume total, nombre de relevés, communes)
- Tableau récapitulatif par commune avec :
  - Volume total consommé
  - Nombre de relevés
  - Nombre de points d'eau distincts

**Filtres disponibles** :
- Année
- Région
- District
- Communes (multi-sélection via GET param `communes`)
- Ouvrage

### 2. Vue Détaillée par Point d'Eau
**URL** : `/plannings/conso-cartes-sociales/`
**Fonction** : `gestion_conso_cartes_sociales()`

**Affichage** :
- Statistiques globales (points d'eau, cartes actives, volume total)
- Tableau détaillé par point d'eau avec :
  - Nom du point d'eau
  - Ouvrage associé
  - Commune
  - Nombre de cartes sociales actives
  - Nombre d'habitants bénéficiaires
  - Nombre de relevés avec volume carte sociale
  - Volume total annuel

**Filtres disponibles** :
- Année
- Commune
- Ouvrage
- Point d'eau (optionnel)

### 3. Page d'Impression
**URL** : `/plannings/conso-cartes-sociales/impression/`
**Fonction** : `impression_conso_cartes_sociales()`

**Format** : Paysage (landscape)

**Structure hiérarchique** :
```
Commune
  └─ Ouvrage
      └─ Point d'Eau
          └─ Volumes mensuels (Jan → Déc)
              └─ Total annuel
```

**Colonnes affichées** :
- Point d'Eau (nom)
- 12 colonnes pour les mois (Jan à Déc)
- Total annuel

**Totaux calculés** :
- Sous-total par ouvrage
- Total par commune
- Total général

## 📊 Modèles utilisés

### Releve (apps.billing.models)
**Champ clé** : `volume_carte_sociale` (FloatField)
- Volume d'eau gratuit accordé via carte sociale
- Soustrait du volume facturé

### CarteSociale (apps.infrastructure.models)
**Champs** :
- `numero_carte` : Numéro de la carte
- `nom_beneficiaire` : Nom du bénéficiaire
- `point_eau` : ForeignKey vers PointEau
- `nombre_habitants` : Nombre de personnes dans le foyer
- `statut` : active / suspendue / expiree / annulee

### PointEau (apps.billing.models)
**Relation** : `cartes_sociales` (reverse ForeignKey depuis CarteSociale)

### ModaliteGestion (apps.billing.models)
**Critère de filtrage** :
- `modalitepaiement__in=['au_volume', 'mixte']`
- `date_fin__isnull=True` (modalité active)

## ⚙️ Logique de filtrage

### Critères obligatoires appliqués automatiquement

1. **Modalités au volume ou mixte uniquement** :
```python
modalites_ids = ModaliteGestion.objects.filter(
    date_fin__isnull=True,
    modalitepaiement__in=['au_volume', 'mixte']
).values_list('ouvrage_id', flat=True).distinct()
```

2. **Volume carte sociale > 0** :
```python
releves = Releve.objects.filter(
    point_eau__ouvrage_id__in=modalites_ids,
    volume_carte_sociale__gt=0
)
```

3. **Filtrage par année** (en Python pour gérer le timezone) :
```python
for releve in releves:
    date_aware = releve.datereleve if releve.datereleve.tzinfo else timezone.make_aware(releve.datereleve)
    date_madagascar = date_aware.astimezone(tz_madagascar)
    if date_madagascar.year == int(annee_filter):
        releves_filtres.append(releve)
```

## 🗂️ Architecture des fichiers

### Backend - Vues
**Fichier** : `backend/apps/planning/views_conso_cartes_sociales.py`

**Fonctions** :
1. `gestion_conso_cartes_sociales_global()` - Vue globale par commune
2. `gestion_conso_cartes_sociales()` - Vue détaillée par point d'eau
3. `impression_conso_cartes_sociales()` - Page d'impression
4. `api_conso_cartes_sociales_data()` - API JSON (optionnel, pour futur développement)

### Backend - URLs
**Fichier** : `backend/apps/planning/urls.py`

**Routes ajoutées** :
```python
# Gestion consommations cartes sociales
path('conso-cartes-sociales/global/', views_conso_cartes_sociales.gestion_conso_cartes_sociales_global, name='conso_cartes_sociales_global'),
path('conso-cartes-sociales/', views_conso_cartes_sociales.gestion_conso_cartes_sociales, name='conso_cartes_sociales'),
path('conso-cartes-sociales/impression/', views_conso_cartes_sociales.impression_conso_cartes_sociales, name='impression_conso_cartes_sociales'),
path('conso-cartes-sociales/api/data/', views_conso_cartes_sociales.api_conso_cartes_sociales_data, name='api_conso_cartes_sociales_data'),
```

### Templates
1. `backend/templates/planning/conso_cartes_sociales_global.html` - Vue globale
2. `backend/templates/planning/conso_cartes_sociales.html` - Vue par point d'eau
3. `backend/templates/planning/conso_cartes_sociales_impression.html` - Impression

### Template Tags
**Fichier** : `backend/apps/planning/templatetags/planning_extras.py`

**Filter ajouté** : `get_item` - Permet d'accéder aux dictionnaires avec clé entière dans les templates
```python
@register.filter
def get_item(dictionary, key):
    try:
        key = int(key)
    except (ValueError, TypeError):
        pass
    return dictionary.get(key, 0)
```

**Usage dans template** :
```django
{{ pe_data.mois|get_item:i|floatformat:2 }}
```

## 📈 Statistiques calculées

### Vue Globale
- **Volume Total** : Somme de tous les `volume_carte_sociale` pour l'année
- **Nombre de Relevés** : Nombre de relevés avec volume_carte_sociale > 0
- **Nombre de Communes** : Communes distinctes ayant des consommations

### Vue par Point d'Eau
- **Total Points d'Eau** : Points d'eau ayant au moins une carte sociale active
- **Total Cartes** : Nombre total de cartes sociales actives
- **Volume Global** : Somme de tous les volumes carte sociale

### Page Impression
- **Volume mensuel** : Volume carte sociale par mois pour chaque point d'eau
- **Total annuel par point d'eau** : Somme des 12 mois
- **Sous-total par ouvrage** : Somme de tous les points d'eau de l'ouvrage
- **Total par commune** : Somme de tous les ouvrages de la commune
- **Total général** : Somme de toutes les communes

## 🔐 Cas d'usage

### Cas 1 : Vue d'ensemble d'une commune
1. Accéder à `/plannings/conso-cartes-sociales/global/`
2. Filtrer par commune (ex: Ambanja)
3. Voir le volume total accordé gratuitement
4. Identifier les points d'eau avec le plus de consommations

### Cas 2 : Suivi détaillé par point d'eau
1. Accéder à `/plannings/conso-cartes-sociales/`
2. Filtrer par ouvrage
3. Voir combien de cartes sont actives par point d'eau
4. Analyser les volumes accordés

### Cas 3 : Rapport mensuel imprimable
1. Accéder à `/plannings/conso-cartes-sociales/impression/`
2. Filtrer par communes et/ou ouvrage
3. Voir la répartition mensuelle des volumes
4. Imprimer pour archivage ou présentation

## ⚠️ Points d'attention

1. **Timezone Madagascar** :
   - Toutes les dates sont converties en `Indian/Antananarivo` (UTC+3)
   - Filtrage par année en Python APRÈS conversion

2. **Modalités actives uniquement** :
   - Seuls les ouvrages avec `modalitepaiement='au_volume'` ou `'mixte'`
   - ET `date_fin IS NULL`

3. **Volume carte sociale vs Volume facturé** :
   - `volume_carte_sociale` : Volume GRATUIT accordé
   - `volume_facture` : Volume payant (= consommation - volume_carte_sociale - volume_non_facture)

4. **Cartes sociales actives** :
   - Seules les cartes avec `statut='active'` sont comptées

5. **Performance** :
   - Utilisation de `select_related()` pour optimiser les requêtes
   - Filtrage en Python pour le timezone (requiert chargement de tous les relevés de l'année)

## 🚀 Prochaines améliorations possibles

1. **Graphiques** : Ajouter Chart.js pour visualiser l'évolution mensuelle
2. **Export Excel** : Permettre l'export du tableau pour analyse externe
3. **Alertes** : Notifier si volumes carte sociale dépassent un seuil
4. **Comparaison annuelle** : Comparer année N vs année N-1
5. **API REST complète** : Développer l'API pour intégration avec d'autres systèmes
6. **Statistiques par bénéficiaire** : Tracker la consommation par carte sociale
7. **Calcul automatique du coût** : Estimer le manque à gagner (volume gratuit × tarif)

## 📝 Historique

**Date** : 15 décembre 2025
**Auteur** : Claude Code
**Version** : 1.0
**Ticket** : Création module suivi consommations cartes sociales

**Changements** :
- ✅ Création vues backend (global, détaillée, impression)
- ✅ Création templates HTML (3 pages)
- ✅ Configuration URLs
- ✅ Ajout template filter `get_item`
- ✅ Documentation complète

## 🔗 Liens vers d'autres modules

**Modules similaires** :
- Module volumétrique classique : `/plannings/volumetrique/`
- Vue globale paiements : `/plannings/volumetrique/global/`
- Impression volumétrique : `/plannings/volumetrique/impression/`

**Différences clés** :
- Volumétrique : Tous les volumes facturés (payants)
- Cartes sociales : Uniquement volumes gratuits (volume_carte_sociale)
