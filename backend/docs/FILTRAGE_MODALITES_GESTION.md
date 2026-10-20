# Filtrage par Modalités de Gestion - Pages Consolidées

## 📋 Vue d'ensemble

Les pages consolidées des Points d'Eau et Équipements affichent maintenant **uniquement les entités appartenant aux ouvrages affectés à l'organisation** de l'utilisateur connecté via les modalités de gestion actives.

## 🎯 Objectif

Garantir que chaque organisation ne voit que les points d'eau et équipements des ouvrages qu'elle gère activement, selon les modalités de gestion en vigueur.

## 🔍 Pages concernées

1. **Points d'Eau consolidés** : `/facturation/consolidated-points-eau/`
2. **Équipements consolidés** : `/consolidated-equipements/`

## ⚙️ Logique de filtrage

### Critères de filtrage

```python
# 1. Utilisateur doit être un employé
if hasattr(request.user, 'employe') and request.user.employe:
    employe = request.user.employe
    organisation = employe.organisation

    # 2. Récupérer les ouvrages avec modalité active pour cette organisation
    if organisation:
        ouvrages_ids = ModaliteGestion.objects.filter(
            date_fin__isnull=True,       # ✅ Modalité active (pas terminée)
            gestionnaire=organisation    # ✅ Organisation de l'employé
        ).values_list('ouvrage_id', flat=True).distinct()

        # 3. Filtrer les points d'eau / équipements
        points_eau = points_eau.filter(ouvrage_id__in=ouvrages_ids)
        equipements = equipements.filter(ouvrage_id__in=ouvrages_ids)
```

### Relations utilisées

```
User → Employe → Base → Organisation
                           ↓
                    ModaliteGestion (date_fin=NULL) → Ouvrage
                                                          ↓
                                               PointEau / EquipementConstitutif
```

## 📊 Modèle ModaliteGestion

**Table** : `modalitesgestions`

**Champs clés** :
- `ouvrage` : ForeignKey vers Ouvrage
- `gestionnaire` : ForeignKey vers Organisation
- `date_debut` : Date de début de gestion
- `date_fin` : Date de fin (NULL = modalité active)
- `statut` : actif / suspendu / résilié

**Modalité active** = `date_fin IS NULL`

## 🔐 Cas d'usage

### Cas 1 : Employé Soakoja
- Organisation : Soakoja
- Modalités actives : 219 ouvrages gérés par Soakoja
- **Résultat** : Voit uniquement les points d'eau et équipements de ces 219 ouvrages

### Cas 2 : Employé ST
- Organisation : ST (Superviseur Technique)
- Modalités actives : 45 ouvrages gérés par ST
- **Résultat** : Voit uniquement les points d'eau et équipements de ces 45 ouvrages

### Cas 3 : Administrateur sans employé
- Pas d'objet `Employe` lié au compte
- **Résultat** : Voit TOUS les points d'eau et équipements (aucun filtre appliqué)

### Cas 4 : Employé sans organisation
- A un profil `Employe` mais `organisation=NULL`
- **Résultat** : Voit TOUS les points d'eau et équipements (aucun filtre appliqué)

## 📁 Fichiers modifiés

### 1. Points d'Eau (`apps/billing/views.py` - lignes 586-725)

**Fonction** : `consolidated_points_eau(request)`

**Modifications** :
- Ligne 593 : Import `ModaliteGestion`
- Lignes 602-614 : Filtrage des ouvrages via modalités actives
- Lignes 623-625 : Application du filtre sur `points_eau`
- Lignes 722-725 : Filtrage de la liste des ouvrages pour les filtres

```python
# Import ajouté
from apps.billing.models import ModaliteGestion

# Filtrage ajouté
ouvrages_ids = None
if hasattr(request.user, 'employe') and request.user.employe:
    employe = request.user.employe
    organisation = employe.organisation if hasattr(employe, 'organisation') else None

    if organisation:
        ouvrages_ids = ModaliteGestion.objects.filter(
            date_fin__isnull=True,
            gestionnaire=organisation
        ).values_list('ouvrage_id', flat=True).distinct()

# Application du filtre
if ouvrages_ids is not None:
    points_eau = points_eau.filter(ouvrage_id__in=ouvrages_ids)
```

### 2. Équipements (`apps/infrastructure/views.py` - lignes 372-519)

**Fonction** : `consolidated_equipements(request)`

**Modifications** :
- Ligne 380 : Import `ModaliteGestion`
- Lignes 389-401 : Filtrage des ouvrages via modalités actives
- Lignes 411-412 : Application du filtre sur `equipements`
- Lignes 428-462 : **Ajout des filtres géographiques** (région, district, commune) via PointEau
- Lignes 491-519 : Filtrage des listes pour les filtres dropdown (regions, districts, communes, ouvrages)

```python
# Import ajouté
from apps.billing.models import ModaliteGestion

# Même logique de filtrage que Points d'Eau

# Filtres géographiques via PointEau
if region_filter and region_filter != 'all':
    equipements = equipements.filter(
        ouvrage__pointeau__parcelle__village__fokontany__commune__district__region_id=region_filter
    ).distinct()

if district_filter and district_filter != 'all':
    equipements = equipements.filter(
        ouvrage__pointeau__parcelle__village__fokontany__commune__district_id=district_filter
    ).distinct()

if commune_filter and commune_filter != 'all':
    equipements = equipements.filter(
        ouvrage__pointeau__parcelle__village__fokontany__commune_id=commune_filter
    ).distinct()
```

## 🔄 Impact sur les filtres dropdown

Les listes déroulantes de filtrage (dropdown "Ouvrage", "Région", "District", "Commune") affichent **uniquement les entités** liées aux ouvrages avec modalités actives pour l'organisation de l'employé.

**Avant** :
```python
ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')
regions = Region.objects.all().order_by('nom_region')
# → Affichait tous les ouvrages et régions (ex: 350 ouvrages)
```

**Après** :
```python
if ouvrages_ids is not None:
    # Récupérer les IDs des régions liées aux points d'eau filtrés
    regions_ids = points_eau.values_list(
        'parcelle__village__fokontany__commune__district__region_id',
        flat=True
    ).distinct()

    regions = Region.objects.filter(id__in=regions_ids).order_by('nom_region')
    ouvrages = Ouvrage.objects.filter(id__in=ouvrages_ids).order_by('nom_ouvrage')
else:
    regions = Region.objects.all().order_by('nom_region')
    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')
# → Affiche uniquement les régions et ouvrages gérés (ex: 219 pour Soakoja)
```

## ✅ Tests de validation

### Test 1 : Utilisateur Soakoja
1. Se connecter avec un compte employé Soakoja
2. Accéder à `/facturation/consolidated-points-eau/`
3. **Vérifier** : Nombre de points d'eau correspond aux ouvrages Soakoja uniquement
4. **Vérifier** : Dropdown "Ouvrage" ne contient que les ouvrages Soakoja
5. **Vérifier** : Dropdowns "Région", "District", "Commune" ne contiennent que les zones concernées

### Test 2 : Utilisateur ST
1. Se connecter avec un compte employé ST
2. Accéder à `/consolidated-equipements/`
3. **Vérifier** : Nombre d'équipements correspond aux ouvrages ST uniquement
4. **Vérifier** : Dropdown "Ouvrage" ne contient que les ouvrages ST
5. **Vérifier** : Filtres géographiques ajoutés (Région, District, Commune)

### Test 3 : Administrateur
1. Se connecter avec un compte admin sans profil employé
2. Accéder aux deux pages
3. **Vérifier** : Voit TOUS les points d'eau et équipements

### Test 4 : Changement de modalité
1. Créer une nouvelle modalité de gestion (`date_fin=NULL`)
2. Assigner un ouvrage à une organisation différente
3. **Vérifier** : L'ouvrage apparaît maintenant dans la nouvelle organisation
4. Terminer la modalité (`date_fin=today`)
5. **Vérifier** : L'ouvrage disparaît de la liste

## 🛡️ Sécurité et permissions

### Niveau 1 : Filtrage par modalités (NOUVEAU)
- Filtre par organisation via modalités actives
- Garantit la séparation des données entre organisations

### Niveau 2 : Permissions Django
- `filter_queryset_by_permissions(queryset, user)` est toujours appliqué **APRÈS**
- Ajoute des restrictions supplémentaires selon les permissions utilisateur

**Ordre d'application** :
```python
1. Filtrage par modalités actives (organisation)
2. Filtrage par permissions Django (filter_queryset_by_permissions)
3. Filtres géographiques (région, district, commune)
4. Recherche textuelle
```

## 📈 Statistiques impactées

Les statistiques affichées en haut de page reflètent maintenant **uniquement** les entités filtrées :

- Total points d'eau / équipements
- Points d'eau actifs / inactifs
- Avec / Sans GPS
- Avec / Sans photos
- Nombre d'ouvrages distincts
- Statistiques par type

## ⚠️ Points d'attention

1. **Modalités inactives** : Les ouvrages avec `date_fin` renseignée ne sont PAS affichés
2. **Multi-gestion** : Un ouvrage peut avoir plusieurs modalités actives (rare mais possible)
3. **Transfert de gestion** : Terminer une modalité (`date_fin`) et en créer une nouvelle pour transférer
4. **Admins sans employé** : Voient tout (aucun filtrage)
5. **Performance** : Utilisation de `values_list('ouvrage_id', flat=True)` pour optimiser la requête

## 🔧 Maintenance

### Requête SQL générée (exemple)

```sql
-- Étape 1 : Récupérer les IDs d'ouvrages
SELECT DISTINCT ouvrage_id
FROM modalitesgestions
WHERE date_fin IS NULL
  AND gestionnaire_id = 'uuid-soakoja';

-- Étape 2 : Filtrer les points d'eau
SELECT *
FROM points_eau
WHERE ouvrage_id IN (uuid1, uuid2, uuid3, ...);
```

### Debug

Pour vérifier les ouvrages filtrés :
```python
from apps.billing.models import ModaliteGestion

# Voir les modalités actives pour une organisation
modalites = ModaliteGestion.objects.filter(
    date_fin__isnull=True,
    gestionnaire_id='uuid-organisation'
)

print(f"Modalités actives : {modalites.count()}")
for m in modalites:
    print(f"- {m.ouvrage.nom_ouvrage} (depuis {m.date_debut})")
```

## 📝 Historique

**Date** : 15 décembre 2025
**Auteur** : Claude Code
**Version** : 1.0
**Ticket** : Filtrage par modalités de gestion dans pages consolidées

**Changements** :
- ✅ Ajout filtrage par organisation via modalités actives
- ✅ Application sur Points d'Eau consolidés
- ✅ Application sur Équipements consolidés
- ✅ Filtrage des dropdowns "Ouvrage"
- ✅ Ajout filtres géographiques (Région, District, Commune) sur Équipements
- ✅ Filtrage des dropdowns géographiques selon les entités visibles
- ✅ Template équipements mis à jour avec 4 filtres dropdown (Région, District, Commune, Ouvrage)
- ✅ Pagination préservant tous les filtres actifs
- ✅ Documentation complète

**Fichiers templates modifiés** :
- `backend/templates/infrastructure/consolidated_equipements.html` (lignes 149-206, 398-431)
  - Ajout des 4 filtres dropdown en grille responsive
  - Pagination avec conservation des filtres

## 🚀 Prochaines améliorations possibles

1. **Indicateur visuel** : Badge "X ouvrages gérés" en haut de page
2. **Filtre organisation** : Permettre aux admins de choisir l'organisation (override)
3. **Cache** : Mettre en cache la liste des ouvrages_ids (expire chaque heure)
4. **Logs** : Tracer les accès par organisation pour audit
5. **Export** : Limiter les exports Excel aux ouvrages gérés également
