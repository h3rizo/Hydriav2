# Migration des Congés : Planning → DemandeConge

## Contexte

La page `/demandes-conges/` affichait des données incohérentes avec l'état réel des congés des employés car les congés étaient uniquement enregistrés dans la table `Planning` et non dans la table `DemandeConge`.

## Objectif

Synchroniser les données historiques de congés depuis `Planning` vers `DemandeConge` pour que la page de gestion des congés soit cohérente avec la réalité.

## Solution

Un script de migration Django (`migrate_conges_from_planning`) a été créé pour :

1. **Extraire** tous les plannings de type "Congé" depuis la table `Planning`
2. **Regrouper** les dates consécutives en périodes de congé (ex: 3 jours du 01/01 au 03/01)
3. **Créer** des entrées `DemandeConge` correspondantes
4. **Valider automatiquement** les congés passés (date_fin < aujourd'hui)
5. **Laisser à valider** les congés futurs (date_fin >= aujourd'hui)

## Utilisation

### Mode simulation (dry-run)

Pour voir ce qui serait fait **sans modifier** la base de données :

```bash
cd backend
python manage.py migrate_conges_from_planning --dry-run
```

### Migration réelle

Pour appliquer les changements :

```bash
python manage.py migrate_conges_from_planning
```

### Migration pour un employé spécifique

```bash
python manage.py migrate_conges_from_planning --employe "VICTORIEN"
```

## Résultats de la migration (8 décembre 2025)

### Statistiques globales

- **Total demandes créées** : 226
- **Inscrites au planning** : 225
- **Congés passés (validés automatiquement)** : 220
- **Congés futurs (à valider manuellement)** : 6

### Employés traités

- **30 employés** concernés
- **473 entrées** de planning analysées
- **225 périodes** de congé identifiées

### Top 10 employés par nombre de jours

| Employé | Nb demandes | Total jours |
|---------|-------------|-------------|
| CHRISTIAN | 18 | 39 |
| PEROLIN | 12 | 34 |
| ALAIN | 14 | 33 |
| MANITRASINA | 16 | 30 |
| IRÈNE | 19 | 28 |
| FRIDA | 16 | 26 |
| STANISLAS | 8 | 24 |
| VALÉRIE | 9 | 23 |
| LYDIE | 12 | 22 |
| SANDRINE | 8 | 21 |

## Algorithme de regroupement

Le script regroupe intelligemment les dates consécutives :

**Exemple :**
```
Planning :
- 2025-01-02 : Congé
- 2025-01-03 : Congé
- 2025-01-06 : Congé
- 2025-01-07 : Congé
- 2025-01-08 : Congé

Devient :
- Demande 1 : 2025-01-02 → 2025-01-03 (2 jours)
- Demande 2 : 2025-01-06 → 2025-01-08 (3 jours)
```

## Validation automatique

Les congés sont validés automatiquement si leur date de fin est **passée** (< date du jour) :

- `statut` = `'inscrite_planning'`
- `date_validation_chef` = maintenant
- `date_validation_directeur` = maintenant
- `date_inscription_planning` = maintenant

Les congés **futurs** sont créés avec le statut `'inscrite_planning'` mais **sans dates de validation**, permettant une validation manuelle ultérieure.

## Champs renseignés

Pour chaque demande créée :

| Champ | Valeur |
|-------|--------|
| `employe` | Employé du planning |
| `type_demande` | `'conge'` |
| `date_debut` | Première date de la période |
| `date_fin` | Dernière date de la période |
| `nb_jours_demandes` | Nombre de jours calculé |
| `motif` | `"Migré depuis Planning - Activité: Congé"` |
| `reliquat_conge_avant` | Dernier solde disponible (SoldeConge) |
| `reliquat_permission_avant` | Dernier solde permissions |
| `statut` | `'inscrite_planning'` |
| `date_demande` | Maintenant (timezone Madagascar) |

## Gestion des doublons

Le script **ignore** les demandes existantes ayant les mêmes dates :

```python
demande_existante = DemandeConge.objects.filter(
    employe=employe,
    date_debut=date_debut,
    date_fin=date_fin
).first()

if demande_existante:
    # Ignorée
```

## Timezone

Toutes les conversions de dates respectent le timezone Madagascar (`Indian/Antananarivo`, UTC+3) comme spécifié dans `TIMEZONE_GUIDE.md`.

## Impact sur la page /demandes-conges/

Après migration :

- ✅ Les congés passés s'affichent correctement
- ✅ Les reliquats sont cohérents
- ✅ L'historique est complet
- ✅ Les futures demandes sont visibles
- ⚠️ Les congés futurs nécessitent une validation manuelle si besoin

## Relancer la migration

Le script peut être relancé sans risque :

- Les demandes existantes sont **ignorées** (pas de doublon)
- Seules les nouvelles périodes depuis Planning seront ajoutées

## Commandes utiles

### Vérifier le résultat

```python
from apps.employees.models_conges import DemandeConge

# Total
DemandeConge.objects.count()  # 226

# Par statut
DemandeConge.objects.filter(statut='inscrite_planning').count()  # 225

# Pour un employé
from apps.employees.models import Employe
victorien = Employe.objects.get(surnom='VICTORIEN')
DemandeConge.objects.filter(employe=victorien).count()  # 6
```

### Supprimer la migration (si besoin)

```python
# ⚠️ ATTENTION : Supprime toutes les demandes migrées
from apps.employees.models_conges import DemandeConge

DemandeConge.objects.filter(
    motif__icontains='Migré depuis Planning'
).delete()
```

## Fichiers concernés

- **Script** : `backend/apps/employees/management/commands/migrate_conges_from_planning.py`
- **Modèles** :
  - `apps.planning.models.Planning`
  - `apps.planning.models.Activite`
  - `apps.employees.models_conges.DemandeConge`
  - `apps.employees.models_conges.SoldeConge`

## Améliorations futures

1. **Import depuis Excel** : Permettre l'import de congés depuis un fichier Excel
2. **Recalcul automatique des soldes** : Mettre à jour les SoldeConge après migration
3. **Notification** : Envoyer un email aux employés avec leur historique de congés
4. **Validation en masse** : Interface pour valider rapidement les congés futurs

## Support

En cas de problème, vérifier :

1. Les activités de type "Congé" existent : `Activite.objects.filter(nom__icontains='Congé')`
2. Les employés ont des plannings liés : `Planning.objects.filter(employe__isnull=False)`
3. Les dates sont en timezone Madagascar : Voir `TIMEZONE_GUIDE.md`

---

**Date de migration initiale** : 8 décembre 2025
**Résultat** : ✅ Succès - 226 demandes créées, 220 validées automatiquement
