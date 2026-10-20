# Guide d'application des permissions

## ✅ Vues déjà sécurisées

### Dashboard
- ✅ `hydria/views.py::home()` - Dashboard principal avec filtres de permissions
- ✅ `hydria/views.py::dashboard_api()` - API dashboard avec filtres

### Plannings
- ✅ `apps/planning/views.py::planning_list()` - Liste des plannings filtrée

### Organisation/Ouvrages
- ✅ `apps/organization/views.py::ouvrage_list()` - Liste des ouvrages filtrée
- ✅ `apps/organization/views.py::points_eau_list()` - Liste des points d'eau filtrée
- ✅ `apps/organization/views.py::equipements_list()` - Liste des équipements filtrée

## 🔧 Vues à sécuriser

### À appliquer systématiquement :

1. **Ajouter l'import** en haut du fichier views.py :
```python
from apps.employees.permissions import employe_required, filter_queryset_by_permissions
```

2. **Ajouter le décorateur** sur chaque vue :
```python
@employe_required
def ma_vue(request):
    ...
```

3. **Filtrer les querysets** selon les permissions :
```python
# Pour les ouvrages
ouvrages = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)

# Pour les points d'eau
points_eau = filter_queryset_by_permissions(PointEau.objects.all(), request.user)

# Pour les équipements
equipements = filter_queryset_by_permissions(EquipementConstitutif.objects.all(), request.user)

# Pour les employés
employes = filter_queryset_by_permissions(Employe.objects.all(), request.user)

# Pour les plannings
plannings = filter_queryset_by_permissions(Planning.objects.all(), request.user)
```

## 📋 Liste des vues à traiter par fichier

### apps/billing/views.py
- [ ] Toutes les vues CRUD de facturation
- [ ] Vues de modalités de gestion
- [ ] Vues de compteurs
- [ ] Vues de tarifs

### apps/infrastructure/views.py
- [ ] Vues de gestion des équipements
- [ ] Vues d'adresses
- [ ] Vues de cartes sociales

### apps/inspections/views.py
- [x] Import ajouté
- [ ] `dashboard_inspections()` - Filtrer les inspections
- [ ] `nouvelle_inspection_view()` - Filtrer les ouvrages sélectionnables
- [ ] `inspection_calendar_view()` - Filtrer les plannings affichés
- [ ] `equipment_selection_view()` - Filtrer les équipements/points d'eau
- [ ] Toutes les APIs doivent filtrer selon permissions

### apps/inventory/views.py
- [ ] Vues de stocks (filtrer par magasin de la base)
- [ ] Vues de mouvements de stock
- [ ] Vues d'achats

### apps/employees/views.py
- [ ] Liste des employés (déjà filtré via `get_accessible_employes()`)
- [ ] Détails employés (vérifier l'accès)

### apps/geography/views.py
- [ ] Filtrer les régions/districts/communes affichés selon les ouvrages accessibles

## ⚠️ Cas particuliers

### APIs REST Framework
Pour les ViewSets et APIViews, utiliser :
```python
class MonViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        queryset = super().get_queryset()
        return filter_queryset_by_permissions(queryset, self.request.user)
```

### Vues de détail
Vérifier que l'objet est accessible :
```python
@employe_required
def ouvrage_detail(request, pk):
    ouvrages_accessibles = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    ouvrage = get_object_or_404(ouvrages_accessibles, pk=pk)
    ...
```

### Vues de création
Vérifier que l'ouvrage parent est accessible :
```python
@employe_required
def point_eau_create(request, ouvrage_id):
    ouvrages_accessibles = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    ouvrage = get_object_or_404(ouvrages_accessibles, pk=ouvrage_id)
    # Créer le point d'eau pour cet ouvrage
    ...
```

## ✅ Modèles supportés par le système de permissions

Le système `filter_queryset_by_permissions()` supporte automatiquement :

**Facturation (Billing)** :
- PointEau, CompteurTete, TarifVolumetrique, ModaliteGestion
- Releve, Fournisseur

**Infrastructure** :
- EquipementConstitutif, Adresse, CarteSociale, OuvrageInfrastructure

**Inspections** :
- Visite, ResultatPointControle, ChecklistPointsControle

**Inventory (Stocks)** :
- Stock, StockMovement, Purchase, PurchaseItem

**Organization** :
- Base, Magasin, Ouvrage

**Plannings** :
- Planning (via méthode `get_accessible_plannings()`)

**Employés** :
- Employe (via méthode `get_accessible_employes()`)

## 🎯 Règles de cloisonnement

### Agent de recouvrement
- Voit uniquement les ouvrages dont il est responsable (via ModaliteGestion)
- Voit ses propres plannings
- Voit uniquement lui-même dans la liste d'employés
- Voit les stocks de sa base

### Superviseur technique
- Voit tous les ouvrages de sa base (via modalités des employés de sa base)
- Voit les plannings de tous les employés de sa base
- Voit tous les employés de sa base
- Voit les stocks de sa base

### Directeur
- Voit tous les ouvrages de son organisation
- Voit tous les plannings de son organisation
- Voit tous les employés de son organisation
- Voit les stocks de toutes les bases de son organisation

## 📝 Checklist d'application

Pour chaque vue :
- [ ] Import `employe_required` et `filter_queryset_by_permissions`
- [ ] Décorateur `@employe_required` ajouté
- [ ] Tous les `Ouvrage.objects.all()` remplacés par filtre de permissions
- [ ] Tous les `PointEau.objects.all()` remplacés par filtre de permissions
- [ ] Toutes les autres tables dépendantes filtrées
- [ ] `get_object_or_404()` utilise les querysets filtrés
- [ ] Tests effectués avec différents rôles (agent, superviseur, directeur)
