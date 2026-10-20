# Status de l'app Infrastructure - NE PAS SUPPRIMER

## ⚠️ IMPORTANT : Infrastructure doit RESTER

Contrairement à ce qui était indiqué dans les commentaires, **l'app `infrastructure` ne peut PAS être supprimée** car elle contient des modèles centraux utilisés massivement dans toute l'application.

## 📊 Modèles de infrastructure et leur utilisation

### 1. **EquipementConstitutif** (le plus utilisé)
- **Table** : `equipementsconstitutifs`
- **Description** : Équipements constitutifs d'une infrastructure (pompes, vannes, compteurs, etc.)
- **Utilisé dans** :
  - `apps.planning` - Détails de planning liés aux équipements
  - `apps.organization` - Gestion des équipements par ouvrage
  - `apps.inspections` - Inspections d'équipements
  - `apps.core` - Dashboard et statistiques
  - `apps.ouvrages` - Formulaires et vues
  - `apps.geography` - Capture de données terrain
  - `apps.inventory` - Stocks d'équipements

### 2. **Adresse**
- **Table** : `adresses`
- **Description** : Adresses des ouvrages
- **Utilisé dans** :
  - `apps.organization` - Localisation des ouvrages
  - `apps.ouvrages` - Gestion des adresses
  - `hydria` - Dashboard principal

### 3. **CarteSociale**
- **Table** : `cartes_sociales`
- **Description** : Cartes sociales des abonnés (tarification sociale)
- **Utilisé dans** :
  - `apps.billing` - Relevés et facturation
  - `apps.organization` - Gestion des cartes
  - `apps.core` - Statistiques

### 4. **TypeEquipement**
- **Table** : `types_equipements`
- **Description** : Types d'équipements (pompe, vanne, compteur, etc.)
- **Utilisé dans** :
  - `apps.organization` - APIs et gestion
  - `apps.inspections` - Types de composants

### 5. **EquipementControle**
- **Table** : `equipements_controle`
- **Description** : Équipements de contrôle pour inspections
- **Utilisé dans** :
  - `apps.organization` - Gestion des contrôles

### 6. Autres modèles
- **MaintenanceTask** - Tâches de maintenance
- **Incident** - Incidents sur infrastructure
- **TypeOuvrage** - Types d'ouvrages (peut-être remplaçable par organization.TypeOuvrage)
- **PointControleInfra, InspectionInfra, ResultatControleInfra** - Système d'inspection

## ✅ Correction appliquée (9 novembre 2025)

**Problème trouvé** :
- Une référence incorrecte à `apps.infrastructure.models.Ouvrage` dans `apps/core/views.py:924`
- Le modèle `Ouvrage` a été supprimé de infrastructure (voir ligne 42-43 de models.py)

**Solution appliquée** :
```python
# AVANT (incorrect)
from apps.infrastructure.models import Ouvrage

# APRÈS (correct)
from apps.organization.models import Ouvrage
```

## 🔍 Raison du doublon apparent

L'app `infrastructure` et `organization` ont des rôles complémentaires :
- **infrastructure** : Modèles techniques (équipements, adresses, cartes sociales)
- **organization** : Modèles organisationnels (organisations, ouvrages, bases, programmes)

Il n'y a **PAS de doublon**, juste une séparation logique des responsabilités.

## 🚀 Pour votre VPS

Si vous avez une erreur de migration sur le VPS, elle est probablement causée par :

1. ✅ **[CORRIGÉ]** Import incorrect de `Ouvrage` depuis infrastructure au lieu de organization
2. ❓ **Migrations manquantes** : Assurez-vous que toutes les migrations sont présentes
3. ❓ **Base de données désynchronisée** : Vérifiez l'état de `django_migrations`

### Commandes de diagnostic sur le VPS :

```bash
# Vérifier les apps installées
python manage.py showmigrations

# Vérifier la configuration
python manage.py check

# Voir les migrations en attente
python manage.py migrate --plan

# Appliquer les migrations (après vérification)
python manage.py migrate
```

### Si les migrations échouent encore :

Envoyez-moi le message d'erreur exact et je pourrai vous aider à le résoudre.

## 📝 Résumé

- ✅ **Infrastructure doit RESTER** dans INSTALLED_APPS
- ✅ Import incorrect de `Ouvrage` corrigé dans `apps/core/views.py`
- ✅ Commentaire mis à jour dans `settings.py`
- ✅ Pas de doublon - séparation logique des responsabilités
- ⚠️ Ne pas supprimer cette app sans refactoring majeur (très risqué)
