# Correction Import DiameX - Synchronisation complète avec suppression (12 décembre 2025)

## Problème identifié

**Symptôme** : Les lignes supprimées dans le fichier Access continuent d'exister dans la table PostgreSQL après un nouvel import.

**Exemple concret** :
- Ligne avec `ID=7086` supprimée du fichier Access `DiameX v3.16.1- Base 1 - Soakoja Vavatenina_20251014 RAF (2).accde`
- Après ré-import, la ligne `ID=7086` existe toujours dans la table `BaseDiameX` de PostgreSQL

## Cause racine

L'ancien algorithme d'import faisait uniquement :
- **INSERT** : Ajouter les nouvelles lignes
- **UPDATE** : Mettre à jour les lignes existantes

Mais il ne **supprimait JAMAIS** les lignes qui ont été effacées du fichier Access source.

**Code problématique** (ancien) :
```python
# Créer ou mettre à jour
if existing:
    for key, value in entry_data.items():
        setattr(existing, key, value)
    existing.save()
    updated_count += 1
else:
    BaseDiameX.objects.create(**entry_data)
    imported_count += 1
```

❌ Aucun mécanisme de suppression des entrées obsolètes

## Solution appliquée

### Stratégie de synchronisation complète

**Fichier modifié** : `backend/apps/accounting/views.py`

**Concept** : Import en 2 étapes pour garantir une synchronisation parfaite entre Access et PostgreSQL.

#### Étape 1 : Import avec tracking des IDs

**Lignes 150-225** - Table DATA :
```python
with transaction.atomic():
    # ÉTAPE 1 : Collecter tous les IDs présents dans le fichier Access
    access_ids = set()
    current_row = 0

    for row in cursor.fetchall():
        # ... code d'import ...
        id_access = data.get('ID')
        if not id_access:
            continue

        # Ajouter l'ID à l'ensemble des IDs présents
        access_ids.add(id_access)

        # Créer ou mettre à jour (comme avant)
        if existing:
            # ... update ...
        else:
            # ... create ...
```

**Lignes 276-349** - Table SoldesReels :
```python
with transaction.atomic():
    # ÉTAPE 1 : Collecter tous les triplets (journal, date_m, rec) présents dans Access
    soldes_keys = set()

    for row in cursor.fetchall():
        journal = soldes_data.get('Journal')
        date_m = soldes_data.get('DateM')
        rec = soldes_data.get('Rec')

        # Ajouter la clé au set
        soldes_keys.add((journal, date_m, rec))

        # Créer ou mettre à jour (comme avant)
        # ...
```

#### Étape 2 : Nettoyage des entrées obsolètes

**Lignes 227-241** - Table DATA :
```python
# ÉTAPE 2 : Supprimer les entrées qui n'existent plus dans Access
log_progress(f"[PROGRESS] Nettoyage des entrées supprimées dans Access...")

# Récupérer toutes les entrées de ce fichier dans PostgreSQL
existing_entries = BaseDiameX.objects.filter(fichier_source=fichier_nom)
deleted_count = 0

for entry in existing_entries:
    if entry.id_access not in access_ids:
        # Cette entrée n'existe plus dans Access, la supprimer
        entry.delete()
        deleted_count += 1

if deleted_count > 0:
    log_progress(f"[OK] {deleted_count} entrée(s) supprimée(s) (n'existent plus dans Access)")
```

**Lignes 351-365** - Table SoldesReels :
```python
# ÉTAPE 2 : Supprimer les entrées SoldesReels qui n'existent plus dans Access
log_progress(f"[PROGRESS] Nettoyage SoldesReels - Suppression des entrées obsolètes...")

existing_soldes = SoldesReels.objects.filter(fichier_source=fichier_nom)
soldes_deleted_count = 0

for solde_entry in existing_soldes:
    solde_key = (solde_entry.journal, solde_entry.date_m, solde_entry.rec)
    if solde_key not in soldes_keys:
        # Cette entrée n'existe plus dans Access, la supprimer
        solde_entry.delete()
        soldes_deleted_count += 1

if soldes_deleted_count > 0:
    log_progress(f"[OK] {soldes_deleted_count} entrée(s) SoldesReels supprimée(s) (n'existent plus dans Access)")
```

### Logs enrichis

**Message final DATA** (ligne 243) :
```python
log_progress(f"[OK] Import DATA terminé: {imported_count} nouveaux, {updated_count} mis à jour, {deleted_count} supprimés")
```

**Message final SoldesReels** (ligne 368) :
```python
log_progress(f"[OK] Import SoldesReels terminé: {soldes_imported} nouveaux, {soldes_updated} mis à jour, {soldes_deleted_count} supprimés")
```

## Identifiants uniques utilisés

### Table DATA (BaseDiameX)
**Clé d'unicité** : `(fichier_source, id_access)`

- `fichier_source` : Nom du fichier Access (ex: `"DiameX v3.16.1- Base 1 - Soakoja Vavatenina_20251014 RAF (2).accde"`)
- `id_access` : Colonne `ID` dans la table DATA d'Access

### Table SoldesReels
**Clé d'unicité** : `(fichier_source, journal, date_m, rec)`

- `fichier_source` : Nom du fichier Access
- `journal` : Code journal (ex: `"BD"`, `"BK"`)
- `date_m` : Date de mouvement
- `rec` : Numéro de reçu/référence

## Comportement attendu

### Scénario 1 : Nouvelle ligne dans Access
- **Fichier Access** : Ligne `ID=8000` ajoutée
- **PostgreSQL** : `INSERT` effectué
- **Compteurs** : `imported_count += 1`

### Scénario 2 : Ligne modifiée dans Access
- **Fichier Access** : Ligne `ID=7086` modifiée (description changée)
- **PostgreSQL** : `UPDATE` effectué
- **Compteurs** : `updated_count += 1`

### Scénario 3 : Ligne supprimée dans Access
- **Fichier Access** : Ligne `ID=7086` supprimée
- **PostgreSQL** : `DELETE` effectué automatiquement
- **Compteurs** : `deleted_count += 1`
- **Log** : `"[OK] 1 entrée(s) supprimée(s) (n'existent plus dans Access)"`

### Scénario 4 : Import d'un fichier déjà importé sans changement
- **Fichier Access** : Aucune modification depuis dernier import
- **PostgreSQL** : Toutes les lignes sont `UPDATE` (même valeurs)
- **Compteurs** : `updated_count = total_rows`, `imported_count = 0`, `deleted_count = 0`

## Avantages de la solution

✅ **Synchronisation complète** : PostgreSQL reflète exactement l'état du fichier Access source

✅ **Traçabilité** : Les logs indiquent clairement combien d'entrées ont été supprimées

✅ **Transaction atomique** : L'import et le nettoyage sont dans la même transaction → Cohérence garantie

✅ **Performance** : Utilisation de `set()` pour vérification rapide des IDs présents (O(1) au lieu de O(n))

✅ **Sécurité** : Filtre par `fichier_source` → Seules les entrées du fichier courant sont affectées

## Performance

### Complexité algorithmique

**Étape 1 - Import** :
- Lecture Access : O(n) où n = nombre de lignes
- Insertion/Update PostgreSQL : O(n)

**Étape 2 - Nettoyage** :
- Requête PostgreSQL : O(m) où m = nombre d'entrées existantes pour ce fichier
- Vérification présence : O(m) avec lookup O(1) dans le set
- Suppression : O(k) où k = nombre d'entrées à supprimer

**Complexité totale** : O(n + m) - Linéaire et optimale

### Cas d'usage typique

**Fichier Access** : 5,000 lignes
- 4,950 lignes inchangées → UPDATE (rapide)
- 40 nouvelles lignes → INSERT
- 10 lignes supprimées → DELETE

**Résultat** :
```
[OK] Import DATA terminé: 40 nouveaux, 4950 mis à jour, 10 supprimés
```

## Tests de validation

### Test 1 : Suppression simple
1. Importer un fichier Access avec 100 lignes
2. Supprimer 5 lignes dans Access
3. Ré-importer le fichier
4. **Résultat attendu** : `deleted_count = 5`

### Test 2 : Mix opérations
1. Importer un fichier Access avec 100 lignes
2. Ajouter 10 lignes, modifier 20 lignes, supprimer 5 lignes dans Access
3. Ré-importer
4. **Résultat attendu** : `imported=10, updated=85, deleted=5` (85 = 100 - 5 - 10)

### Test 3 : Aucun changement
1. Importer un fichier Access
2. Ré-importer immédiatement sans modification
3. **Résultat attendu** : `imported=0, updated=n, deleted=0`

### Test 4 : Fichiers multiples
1. Importer fichier A avec 50 lignes
2. Importer fichier B avec 50 lignes
3. Supprimer 10 lignes dans fichier A
4. Ré-importer fichier A
5. **Résultat attendu** : Seules les entrées de fichier A sont affectées (deleted=10)

## Migration depuis l'ancienne version

**Pas de migration nécessaire** : Le code est rétrocompatible.

**Recommandation** : Faire un ré-import complet de tous les fichiers Access pour garantir la cohérence.

## Cas limites gérés

1. **Ligne Access sans ID** : `continue` (ignorée, comme avant)
2. **Ligne SoldesReels incomplète** : `continue` (journal/date_m/rec manquant)
3. **Fichier_source identique** : Seules les entrées du fichier courant sont affectées
4. **Transaction échouée** : Rollback automatique (aucune modification partielle)

## Prochaines améliorations possibles

1. **Soft delete** : Marquer comme supprimé au lieu de supprimer physiquement
   - Ajouter champ `deleted_at` et `is_deleted`
   - Permettre restauration en cas d'erreur

2. **Historique** : Logger les suppressions dans une table d'audit
   - Table `ImportHistory` avec les détails de chaque opération

3. **Notification** : Alerter l'utilisateur si beaucoup de suppressions
   - Ex: Si `deleted_count > 100`, demander confirmation

4. **Dry-run mode** : Prévisualiser les changements avant de les appliquer
   - Paramètre `--preview` pour voir ce qui serait supprimé

## Fichiers modifiés

1. `backend/apps/accounting/views.py` (lignes 149-243, 276-372)
   - Ajout étape de nettoyage pour DATA
   - Ajout étape de nettoyage pour SoldesReels
   - Logs enrichis avec compteurs de suppressions

2. `backend/docs/FIX_IMPORT_DIAMEX_SYNCHRONISATION.md` (ce fichier)
   - Documentation complète de la correction

## Historique

**12 décembre 2025** : Correction du problème de synchronisation
- Ajout étape de nettoyage après import
- Utilisation de `set()` pour tracking des IDs
- Logs enrichis avec compteurs de suppressions

---

**Créé le** : 12 décembre 2025
**Auteur** : Claude Code
**Impact** : ✅ CRITIQUE - Garantit l'intégrité des données importées
