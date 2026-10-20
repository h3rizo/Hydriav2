# Contraintes d'unicité sur code_tiers et idxls

## Date : 21 décembre 2025

## Objectif

Ajouter des contraintes d'unicité sur les colonnes `code_tiers` pour les employés et fournisseurs afin d'éviter les doublons et garantir l'intégrité des données pour la conversion comptabilité en partie double.

## Modifications appliquées

### 1. Modèle Employe (apps/employees/models.py)

**Ligne 114-121** : Ajout de `unique=True` sur le champ `code_tiers`

```python
code_tiers = models.CharField(
    max_length=6,
    null=True,
    blank=True,
    unique=True,  # ✅ AJOUTÉ
    verbose_name="Code Tiers",
    help_text="Code tiers comptabilité (6 chiffres) - doit être unique"
)
```

**Migration** : `apps/employees/migrations/0039_add_unique_code_tiers_employe.py`

### 2. Modèle Fournisseur (apps/billing/models.py)

**Ligne 452-459** : Ajout de `unique=True` sur le champ `code_tiers`

```python
code_tiers = models.CharField(
    max_length=6,
    null=True,
    blank=True,
    unique=True,  # ✅ AJOUTÉ
    verbose_name="Code Tiers",
    help_text="Code tiers comptabilité (6 chiffres) - doit être unique"
)
```

**Migration** : `apps/billing/migrations/0052_add_unique_code_tiers_fournisseur.py`

**Note** : Le champ `idxls` avait déjà `unique=True` (ligne 433)

```python
idxls = models.IntegerField(
    null=True,
    blank=True,
    unique=True,  # Déjà présent
    verbose_name="ID XLS"
)
```

## Nettoyage des doublons AVANT migration

### Employés (7 doublons détectés)

| Code Tiers | Employé gardé | Employé(s) mis à NULL |
|------------|--------------|----------------------|
| 425028 | BIHANONA Elito (embauché 2023-11-01) | DOLIN DOLIN |
| 425038 | RAMANJAKAMBALO Judicael (embauché 2025-01-01) | RABERIAKA Gaetan |
| 425036 | RAHARISON Danny (embauché 2025-10-16) | Seva Christophe |
| 425037 | GALY Luigi Florentin (embauché 2018-02-11) | Rinon Rinon |
| 425029 | FABIOLAIN FABIOLAIN (embauché 2025-01-01) | SAHIDY Angelys |
| 425027 | RENE (embauché 2019-07-01) | CHRISOS CHRISOS |
| 425030 | MAMONJISOA Heriniaina André (embauché 2025-10-16) | RAKOTOELINORO Jean René |

**Critère de sélection** : Employé avec date d'embauche la plus ancienne

### Fournisseurs (3 doublons détectés)

| Code Tiers | Fournisseur gardé | Fournisseur(s) mis à NULL |
|------------|------------------|--------------------------|
| 401005 | CARAMBOLE | VAVY TIANA DEA |
| 401017 | Taxe Ankazondandy | Taxe Antsahafilo |
| 401007 | ROYAL TEXTILE | TRANS TAFARAY |

**Critère de sélection** : Fournisseur avec ID le plus ancien

## Script de nettoyage utilisé

### Employés

```python
from apps.employees.models import Employe
from django.db.models import Count

doublons = Employe.objects.values('code_tiers').annotate(
    count=Count('id')
).filter(count__gt=1, code_tiers__isnull=False)

for doublon in doublons:
    code = doublon['code_tiers']
    employes = Employe.objects.filter(code_tiers=code).order_by('date_embauche')

    # Garder le premier (le plus ancien)
    premier = employes.first()
    autres = employes.exclude(id=premier.id)

    for autre in autres:
        autre.code_tiers = None
        autre.save()
```

### Fournisseurs

```python
from apps.billing.models import Fournisseur
from django.db.models import Count

doublons = Fournisseur.objects.values('code_tiers').annotate(
    count=Count('id')
).filter(count__gt=1, code_tiers__isnull=False)

for doublon in doublons:
    code = doublon['code_tiers']
    fournisseurs = Fournisseur.objects.filter(code_tiers=code).order_by('id')

    # Garder le premier
    premier = fournisseurs.first()
    autres = fournisseurs.exclude(id=premier.id)

    for autre in autres:
        autre.code_tiers = None
        autre.save()
```

## Vérifications post-migration

### Test unicité code_tiers

```bash
# Employés
python manage.py shell -c "from apps.employees.models import Employe; from django.db.models import Count; doublons = Employe.objects.values('code_tiers').annotate(count=Count('id')).filter(count__gt=1, code_tiers__isnull=False); print('Doublons:', doublons.count())"
# Résultat: Doublons: 0 ✓

# Fournisseurs
python manage.py shell -c "from apps.billing.models import Fournisseur; from django.db.models import Count; doublons = Fournisseur.objects.values('code_tiers').annotate(count=Count('id')).filter(count__gt=1, code_tiers__isnull=False); print('Doublons:', doublons.count())"
# Résultat: Doublons: 0 ✓
```

### Test unicité idxls (Fournisseurs)

```bash
python manage.py shell -c "from apps.billing.models import Fournisseur; from django.db.models import Count; doublons = Fournisseur.objects.values('idxls').annotate(count=Count('id')).filter(count__gt=1, idxls__isnull=False); print('Doublons:', doublons.count())"
# Résultat: Doublons: 0 ✓
```

### Test Django check

```bash
python manage.py check
# Résultat: System check identified no issues (0 silenced). ✓
```

## Impact sur l'application

### Avantages

1. **Intégrité des données** : Impossible d'avoir deux employés/fournisseurs avec le même code_tiers
2. **Fiabilité conversion comptable** : Chaque code_tiers pointe vers un seul employé/fournisseur
3. **Détection automatique des doublons** : Django lève une erreur `IntegrityError` si tentative de création de doublon

### Contraintes à respecter

1. **Création/Modification via interface** : Vérifier que le code_tiers n'existe pas déjà
2. **Import Excel** : Valider l'unicité avant insertion
3. **Erreur utilisateur** : Afficher un message clair si code_tiers déjà utilisé

### Messages d'erreur

Lorsqu'un utilisateur tente de créer/modifier un employé/fournisseur avec un code_tiers existant :

```python
# Exemple de gestion d'erreur dans une vue
from django.db import IntegrityError

try:
    employe.save()
except IntegrityError as e:
    if 'code_tiers' in str(e):
        return JsonResponse({
            'success': False,
            'error': f'Le code tiers {employe.code_tiers} est déjà utilisé par un autre employé'
        })
```

## Fichiers modifiés

1. `backend/apps/employees/models.py` (ligne 114-121)
2. `backend/apps/billing/models.py` (ligne 452-459)
3. `backend/apps/employees/migrations/0039_add_unique_code_tiers_employe.py` (créé)
4. `backend/apps/billing/migrations/0052_add_unique_code_tiers_fournisseur.py` (créé)

## Action corrective pour les employés/fournisseurs avec code_tiers = NULL

Les employés/fournisseurs dont le `code_tiers` a été mis à NULL suite au nettoyage des doublons doivent être traités :

1. **Identifier les concernés** :
   ```python
   # Employés
   Employe.objects.filter(nom__in=['DOLIN DOLIN', 'RABERIAKA', ...])

   # Fournisseurs
   Fournisseur.objects.filter(nom_fournisseur__in=['VAVY TIANA DEA', ...])
   ```

2. **Actions possibles** :
   - Leur attribuer un nouveau code_tiers unique (6 chiffres)
   - Les marquer comme inactifs s'ils sont obsolètes
   - Les fusionner avec l'employé/fournisseur gardé

## Prochaines étapes suggérées

1. **Interface utilisateur** : Ajouter validation JavaScript pour vérifier unicité code_tiers avant soumission
2. **Import Excel** : Valider unicité dans le script d'import
3. **Audit** : Logger les tentatives de création de doublons
4. **Documentation utilisateur** : Guide pour attribution des codes tiers

## Conclusion

Les contraintes d'unicité sur `code_tiers` (employés et fournisseurs) et `idxls` (fournisseurs) sont maintenant actives. La base de données ne contient plus de doublons et toute tentative future de création de doublon sera automatiquement bloquée par PostgreSQL.

**Impact** : Système de conversion comptabilité en partie double sécurisé avec codes tiers uniques.
