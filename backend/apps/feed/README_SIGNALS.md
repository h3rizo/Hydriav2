# Système de Surveillance Automatique du Fil d'Actualité

Ce système surveille automatiquement les changements dans les pages suivantes et poste des mises à jour de statistiques dans le fil d'actualité:

## Pages Surveillées

### 1. Paiements Forfaitaires
- **URL**: `/dashboard/paiements-forfaitaires/`
- **Type de post**: `paiement_forfaitaire`
- **Déclencheurs**:
  - Modification d'une modalité de gestion forfaitaire
  - Création/modification d'un paiement via PlanningDetail

### 2. Réparations & Réhabilitations
- **URL**: `/plannings/reparations/`
- **Type de post**: `planning` (avec tag `reparations`)
- **Déclencheurs**:
  - Création/modification d'une inspection
  - Création/modification d'un planning de réparation/réhabilitation

## Statistiques Affichées

### Paiements Forfaitaires
- Total modalités forfaitaires actives
- Nombre de points d'eau avec tarif forfaitaire
- Montant prévu total (Ar)
- Montant payé total (Ar)
- Taux de recouvrement (%)

### Réparations & Réhabilitations
- Nombre de réparations effectuées
- Nombre de réhabilitations effectuées
- Nombre de réparations de pannes
- Total d'interventions
- Nombre d'ouvrages concernés

## Mise à Jour

### Automatique (via Signaux Django)
Les posts sont automatiquement créés ou mis à jour lors de:
- Sauvegarde d'une `ModaliteGestion` avec type forfaitaire
- Sauvegarde d'une `Inspection`
- Sauvegarde d'un `Planning` de type réparation/réhabilitation

Un seul post par jour est créé pour chaque type. Si un post existe déjà pour aujourd'hui, il est mis à jour au lieu de créer un doublon.

### Manuelle (via Commande Django)

Pour forcer la mise à jour des posts:

```bash
# Mettre à jour tous les posts de statistiques
python manage.py update_feed_stats

# Mettre à jour seulement les paiements
python manage.py update_feed_stats --type=paiements

# Mettre à jour seulement les réparations
python manage.py update_feed_stats --type=reparations
```

## Configuration d'une Tâche Planifiée (Optionnel)

Pour mettre à jour automatiquement les stats chaque jour, vous pouvez:

### Option 1: Cron (Linux/Mac)
```bash
# Éditer le crontab
crontab -e

# Ajouter cette ligne pour une mise à jour quotidienne à 8h00
0 8 * * * cd /path/to/backend && python manage.py update_feed_stats
```

### Option 2: Planificateur de tâches Windows
```powershell
# Créer une tâche planifiée qui exécute quotidiennement:
cd C:\path\to\backend
python manage.py update_feed_stats
```

### Option 3: Django Celery (Recommandé pour production)
Configurer une tâche périodique Celery pour exécuter la commande.

## Architecture

### Fichiers Principaux

#### `apps/feed/signals.py`
Contient toute la logique de surveillance:
- `calculate_paiement_stats()`: Calcule les stats des paiements forfaitaires
- `calculate_reparation_stats()`: Calcule les stats des réparations
- `create_or_update_paiement_forfaitaire_post()`: Crée/met à jour le post paiements
- `create_or_update_reparation_post()`: Crée/met à jour le post réparations
- Signaux Django qui déclenchent les mises à jour

#### `apps/feed/apps.py`
Enregistre les signaux au démarrage de l'application.

#### `apps/feed/management/commands/update_feed_stats.py`
Commande Django pour forcer la mise à jour manuelle.

### Modèles Surveillés

- `apps.billing.ModaliteGestion`: Modalités de paiement forfaitaire
- `apps.inspections.Inspection`: Inspections d'ouvrages
- `apps.planning.Planning`: Plannings d'activités (réparations/réhabilitations)

## Dépannage

### Les posts ne se créent pas automatiquement

1. Vérifier que les signaux sont bien importés:
```python
# Dans apps/feed/apps.py
def ready(self):
    import apps.feed.signals  # Cette ligne doit être présente
```

2. Vérifier qu'un utilisateur système existe:
```bash
python manage.py shell
>>> from apps.employees.models import Employe
>>> Employe.objects.filter(nom_employe='Système').exists()
# ou
>>> Employe.objects.first()  # Il doit y avoir au moins un employé
```

3. Forcer une mise à jour manuelle:
```bash
python manage.py update_feed_stats
```

### Erreurs lors du calcul des stats

Les fonctions de calcul incluent des blocs try/except pour gérer les erreurs. Si une erreur se produit, elle est ignorée silencieusement et les stats par défaut (0) sont utilisées.

Pour voir les erreurs détaillées:
```bash
python manage.py update_feed_stats
```

## Personnalisation

### Modifier la fréquence des mises à jour

Par défaut, un seul post par jour est créé. Pour changer cela, modifiez les filtres dans les fonctions `create_or_update_*_post()`:

```python
# Dans signals.py, ligne ~156
existing_post = Post.objects.filter(
    type_post='paiement_forfaitaire',
    date_creation__date=today  # Changer cette condition
).first()
```

### Ajouter de nouvelles statistiques

1. Modifier la fonction `calculate_*_stats()` pour ajouter de nouveaux calculs
2. Mettre à jour le template du post dans `create_or_update_*_post()`
3. Redémarrer le serveur Django pour charger les nouveaux signaux

### Changer le format des posts

Les posts utilisent Markdown pour le formatage. Modifier les templates dans les fonctions `create_or_update_*_post()`:

```python
contenu = f"""
**Titre Section**
- Élément 1: **{stats['value']}**
- Élément 2: **{stats['other_value']}**

🔗 [Lien](/url/)
"""
```

## Support

Pour toute question ou problème, consultez:
- La documentation Django sur les signaux: https://docs.djangoproject.com/en/stable/topics/signals/
- Le code source dans `apps/feed/signals.py`
