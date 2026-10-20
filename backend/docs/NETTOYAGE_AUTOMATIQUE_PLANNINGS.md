# 🧹 NETTOYAGE AUTOMATIQUE DES PLANNINGS

## Vue d'ensemble

Commande Django pour nettoyer automatiquement les plannings passés et leurs données associées (PlanningDetails, Bons de livraison, Paiements forfaitaires).

## Règles de nettoyage

### 1. Plannings (table `plannings`)
**Critère** : Date de plus de N jours (défaut 30)
- ✅ Passe `estvalide=True` si actuellement `False`

### 2. PlanningDetails (table `planning_details`)
**Critère** : Liés à des plannings de plus de N jours
- ✅ Passe `retour=True` si actuellement `False`
- ✅ Passe `date_retour=date_planning` si actuellement `NULL`

### 3. BonLivraison (table `bons_livraison`)
**Critère** : Liés directement aux plannings passés
- ✅ Passe `retour=True` si actuellement `False`
- ✅ Passe `date_retour=date_planning` si actuellement `NULL`

### 4. PaiementForfaitaire (table `paiements_forfaitaires`)
**Critère** : `created_at` de plus de N jours
- ✅ Passe `paye=True` si actuellement `False`
- ✅ Passe `date_paiement=date_facture` si actuellement `NULL`

## Utilisation

### Mode test (dry-run)
Affiche ce qui serait modifié **SANS appliquer les changements** :

```bash
cd backend
python manage.py nettoyer_plannings_passes --dry-run
```

**Exemple de sortie** :
```
[DRY RUN] Nettoyage des données de plus de 30 jours
Date limite : 2025-12-26 10:00:00

=== 1. PLANNINGS ===
Plannings à valider : 145
  - Planning uuid-1 | HERIZO | Bilan | 2025-11-15
  - Planning uuid-2 | FARA | MP | 2025-11-20
  ... et 143 autre(s)

=== 2. PLANNING DETAILS ===
PlanningDetails à marquer retournés : 67
  - Detail uuid-3 | Tuyau PVC | Planning: 2025-11-18
  ... et 66 autre(s)

=== 3. BONS DE LIVRAISON ===
Bons de livraison à marquer retournés : 23
  - Bon BL-2025-123 | Quincaillerie Soakoja | Planning: 2025-11-22
  ... et 22 autre(s)

=== 4. PAIEMENTS FORFAITAIRES ===
Paiements forfaitaires à marquer payés : 89
  - Paiement uuid-4 | RAKOTO Jean | Montant: 5000 Ar | Cree: 2025-11-10
  ... et 88 autre(s)

=== RÉSUMÉ ===
[DRY RUN] Aucune modification appliquée

Ce qui SERAIT modifié :
  - Plannings validés : 145
  - PlanningDetails retournés : 67
  - Bons de livraison retournés : 23
  - Paiements forfaitaires payés : 89

  TOTAL : 324 enregistrement(s)

Pour appliquer ces modifications, relancez sans --dry-run :
  python manage.py nettoyer_plannings_passes --days 30
```

### Mode production (application réelle)
Applique réellement les modifications :

```bash
python manage.py nettoyer_plannings_passes
```

### Personnaliser le délai
Nettoyer les données de plus de 45 jours :

```bash
python manage.py nettoyer_plannings_passes --days 45
```

## Options

| Option | Description | Défaut |
|--------|-------------|--------|
| `--dry-run` | Mode test, affiche sans modifier | Non actif |
| `--days N` | Nombre de jours dans le passé | 30 |

## Workflow recommandé

### 1. Tester avec dry-run
```bash
python manage.py nettoyer_plannings_passes --dry-run
```

**Vérifier** :
- Nombre d'enregistrements qui seront modifiés
- Exemples affichés pour chaque catégorie
- Aucune donnée importante ne sera perdue

### 2. Appliquer les modifications
Si tout semble correct :

```bash
python manage.py nettoyer_plannings_passes
```

### 3. Vérifier manuellement
Après exécution, vérifier les données restantes :

**Plannings non validés** :
```python
python manage.py shell
>>> from apps.planning.models import Planning
>>> from django.utils import timezone
>>> from datetime import timedelta
>>> date_limite = timezone.now() - timedelta(days=30)
>>> Planning.objects.filter(date__lt=date_limite, estvalide=False).count()
0  # Doit être 0 ou très faible
```

**PlanningDetails non retournés** :
```python
>>> from apps.planning.models import PlanningDetail
>>> PlanningDetail.objects.filter(
...     planning__date__lt=date_limite,
...     retour=False
... ).count()
0  # Doit être 0 ou très faible
```

## Automatisation avec Cron Job

### Configuration Cron (Linux/Mac)

**Exécution mensuelle** : Le 1er de chaque mois à 2h du matin
```bash
crontab -e
```

Ajouter la ligne :
```cron
0 2 1 * * cd /path/to/backend && /path/to/venv/bin/python manage.py nettoyer_plannings_passes >> /var/log/hydria_nettoyage.log 2>&1
```

**Exécution hebdomadaire** : Tous les lundis à 3h
```cron
0 3 * * 1 cd /path/to/backend && /path/to/venv/bin/python manage.py nettoyer_plannings_passes >> /var/log/hydria_nettoyage.log 2>&1
```

### Configuration Windows Task Scheduler

1. **Ouvrir** : Panneau de configuration > Outils d'administration > Planificateur de tâches
2. **Créer une tâche de base**
3. **Nom** : "Nettoyage automatique Hydria"
4. **Déclencheur** : Mensuel, le 1er jour à 2h00
5. **Action** : Démarrer un programme
   - Programme : `C:\path\to\venv\Scripts\python.exe`
   - Arguments : `manage.py nettoyer_plannings_passes`
   - Répertoire : `C:\path\to\backend\`

## Logs et Monitoring

### Rediriger la sortie vers un fichier log
```bash
python manage.py nettoyer_plannings_passes >> nettoyage.log 2>&1
```

### Consulter les logs
```bash
tail -f nettoyage.log
```

### Format des logs
Chaque exécution affiche :
- Date et heure d'exécution
- Nombre d'enregistrements modifiés par catégorie
- Exemples de modifications (5 premiers pour chaque catégorie)
- Résumé total

## Sécurité et Précautions

### ⚠️ Points d'attention CRITICAL

1. **Toujours tester avec --dry-run AVANT la première exécution**
2. **Sauvegarder la base de données AVANT l'exécution** :
   ```bash
   pg_dump hydria > backup_avant_nettoyage.sql
   ```
3. **Vérifier que le délai (30 jours) est approprié** pour votre organisation
4. **Les modifications sont IRRÉVERSIBLES** (sans restauration de backup)

### Restauration en cas d'erreur

Si besoin de restaurer après un nettoyage erroné :

```bash
# PostgreSQL
psql hydria < backup_avant_nettoyage.sql

# SQLite (si dev local)
cp backup_avant_nettoyage.db db.sqlite3
```

## Cas d'usage

### 1. Nettoyage de fin de mois
**Quand** : Le 1er de chaque mois
**Commande** : `python manage.py nettoyer_plannings_passes --days 30`
**Objectif** : Valider automatiquement tous les plannings du mois précédent

### 2. Nettoyage trimestriel
**Quand** : Le 1er janvier, avril, juillet, octobre
**Commande** : `python manage.py nettoyer_plannings_passes --days 90`
**Objectif** : Nettoyer les données du trimestre écoulé

### 3. Nettoyage conservateur
**Quand** : Après chaque sprint (2 semaines)
**Commande** : `python manage.py nettoyer_plannings_passes --days 60`
**Objectif** : Nettoyer uniquement les données très anciennes (2 mois)

## Statistiques après nettoyage

Vérifier l'efficacité du nettoyage :

```python
from django.db.models import Count
from apps.planning.models import Planning
from datetime import timedelta
from django.utils import timezone

# Plannings par statut de validation
date_limite = timezone.now() - timedelta(days=30)
stats = Planning.objects.filter(date__lt=date_limite).aggregate(
    valides=Count('id', filter=Q(estvalide=True)),
    non_valides=Count('id', filter=Q(estvalide=False))
)
print(f"Plannings passés validés : {stats['valides']}")
print(f"Plannings passés non validés : {stats['non_valides']}")
```

## Dépannage

### Erreur : OperationalError
**Cause** : Base de données verrouillée (SQLite) ou connexion perdue
**Solution** : Relancer la commande ou vérifier la connexion PostgreSQL

### Erreur : IntegrityError
**Cause** : Contraintes de clés étrangères violées
**Solution** : Contacter le support technique, ne pas forcer la modification

### Aucune modification appliquée
**Cause** : Toutes les données sont déjà nettoyées OU le délai est trop court
**Solution** : Vérifier avec `--dry-run` et ajuster `--days` si nécessaire

## Fichiers modifiés/créés

**Créés** :
1. `backend/apps/planning/management/commands/nettoyer_plannings_passes.py` - Commande principale
2. `backend/docs/NETTOYAGE_AUTOMATIQUE_PLANNINGS.md` - Documentation

## ✅ COMMANDE OPÉRATIONNELLE

La commande de nettoyage automatique est maintenant disponible avec :
✅ Mode dry-run pour tester sans risque
✅ Option --days personnalisable
✅ Nettoyage de 4 types de données (Plannings, PlanningDetails, BonLivraison, PaiementForfaitaire)
✅ Affichage détaillé avec exemples
✅ Résumé complet des modifications
✅ Prêt pour automatisation avec cron job

**Accessible via** : `python manage.py nettoyer_plannings_passes`
**Documentation complète** : `backend/docs/NETTOYAGE_AUTOMATIQUE_PLANNINGS.md`
