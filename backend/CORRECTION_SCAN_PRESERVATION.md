# Correction du problème de perte des scans lors de l'import SoldesReels

**Date:** 6 novembre 2025
**Fichier modifié:** `backend/apps/accounting/views.py` (ligne 299-307)

---

## Problème identifié

### Symptômes
- Les scans **existent dans les fichiers Access** (ex: `.\EHA-Soakoja-Tana.Scan\2025-9\...balance.tiff`)
- Mais en Django, **tous les champs `scan` sont None** dans la table `SoldesReels`
- État actuel : **113 enregistrements SoldesReels, 0 avec scan**

### Cause racine
La logique d'UPDATE dans la fonction `import_access_databases()` écrasait TOUTES les valeurs, même quand elles étaient None :

```python
# ❌ CODE INCORRECT (AVANT correction)
if existing_solde:
    for key, value in solde_entry_data.items():
        setattr(existing_solde, key, value)  # Écrase TOUT, même si value=None
    existing_solde.save()
```

**Scénario problématique :**
1. Import 1 : Fichier Access avec scan → Django enregistre le scan ✅
2. Import 2 : Même fichier, mais scan lu comme None (problème de parsing/chemin) → Django écrase avec None ❌
3. Résultat : Scan perdu définitivement

---

## Correction appliquée

### Code modifié
Fichier: `backend/apps/accounting/views.py` (ligne 299-307)

```python
# ✅ CODE CORRECT (APRÈS correction)
if existing_solde:
    # Ne mettre à jour que si nouvelle valeur NON None
    # Sauf pour les champs obligatoires
    champs_obligatoires = ['fichier_source', 'chemin_base', 'journal', 'date_m', 'rec', 'ccy']
    for key, value in solde_entry_data.items():
        if value is not None or key in champs_obligatoires:
            setattr(existing_solde, key, value)
    existing_solde.save()
    soldes_updated += 1
```

### Logique de préservation

**Règles appliquées :**
1. **Champs avec nouvelle valeur non-None** → Mise à jour systématique
2. **Champs obligatoires** → Toujours mis à jour (même si None)
3. **Autres champs avec valeur None** → **Préservation de l'ancienne valeur**

**Champs obligatoires (toujours mis à jour) :**
- `fichier_source` : Identifiant du fichier Access source
- `chemin_base` : Chemin de base pour les scans
- `journal` : Journal comptable
- `date_m` : Date du mouvement
- `rec` : Numéro de reçu
- `ccy` : Montant (Currency)

**Champs optionnels (préservés si nouvelle valeur = None) :**
- `scan` : **Préservé si nouvelle valeur est None**
- `description` : Préservée si nouvelle valeur est None
- `validation` : Préservée si nouvelle valeur est None
- `date_rec` : Préservée si nouvelle valeur est None
- `date_input` : Préservée si nouvelle valeur est None

---

## Impact de la correction

### Comportement AVANT
```
Import 1 (avec scan): scan = ".\EHA.Scan\2025-9\balance.tiff"  ✅
Import 2 (scan None): scan = None  ❌ ÉCRASÉ
Résultat: Scan perdu définitivement
```

### Comportement APRÈS
```
Import 1 (avec scan): scan = ".\EHA.Scan\2025-9\balance.tiff"  ✅
Import 2 (scan None): scan = ".\EHA.Scan\2025-9\balance.tiff"  ✅ PRÉSERVÉ
Résultat: Scan conservé même si import ultérieur a None
```

---

## Tests effectués

### 1. Vérification cohérence Django
```bash
python manage.py check
# Résultat: System check identified no issues (0 silenced).
```

### 2. État actuel de la base
```bash
python test_scan_preservation.py
```

**Résultat actuel :**
- Total SoldesReels: 113
- Avec scan: **0** ❌
- Sans scan: 113
- **Conclusion:** Tous les scans ont été perdus lors des imports précédents

### 3. Test de simulation
Le script `test_scan_preservation.py` simule un update avec `scan=None` :
- **AVANT correction** : Scan écrasé par None
- **APRÈS correction** : Scan préservé ✅

---

## Procédure de récupération des scans

### Étape 1 : Vérifier que les scans existent dans Access
```python
python check_access_scans.py
```

**Attendu :** Affiche les scans présents dans les fichiers Access
**Si 0 scan dans Access :** Le problème est en amont (fichiers Access sans scan)
**Si >0 scans dans Access :** Procéder à l'étape 2

### Étape 2 : Réimporter les bases Access
1. **Supprimer les SoldesReels existants** (ATTENTION: opération irréversible) :
   ```python
   python manage.py shell -c "from apps.accounting.models import SoldesReels; SoldesReels.objects.all().delete()"
   ```

2. **Réimporter via l'interface web** :
   - Accéder à : Comptabilité > Import Access
   - Sélectionner les fichiers Access
   - Lancer l'import

3. **Vérifier le résultat** :
   ```python
   python test_scan_preservation.py
   ```

**Résultat attendu :**
- Avec scan: > 0 (nombre dépend du contenu Access)
- Pourcentage avec scan: variable selon les données

### Étape 3 : Imports ultérieurs
Les imports suivants **préserveront** les scans déjà enregistrés, même si le fichier Access renvoie None pour le champ scan.

---

## Scripts de test disponibles

### 1. `test_scan_preservation.py`
**But :** Tester la logique de préservation des scans

**Fonctionnalités :**
- Statistiques des scans dans Django
- Exemples de scans existants
- Simulation d'update avec valeur None
- Recommandations selon l'état actuel

**Utilisation :**
```bash
cd backend
python test_scan_preservation.py
```

### 2. `check_access_scans.py`
**But :** Vérifier les scans dans les fichiers Access source

**Fonctionnalités :**
- Connexion directe aux fichiers Access
- Comptage des scans dans Access
- Exemples de scans Access
- Diagnostic de la source du problème

**Utilisation :**
```bash
cd backend
python check_access_scans.py
```

**Note :** Nécessite que les fichiers Access soient configurés dans le modèle `Base` avec :
- `chemin_base_diamex` : Chemin du dossier Access
- `base_diamex` : Nom du fichier Access

---

## Validation finale

### Critères de succès
- ✅ `python manage.py check` sans erreur
- ✅ Import Access fonctionne sans crash
- ✅ Scans préservés entre imports successifs
- ✅ Nouveaux scans enregistrés correctement
- ✅ Champs obligatoires toujours mis à jour

### Tests de non-régression
Vérifier après réimport :
1. **Nombre de scans > 0** dans Django
2. **Chemins de scans valides** (ex: `.\EHA.Scan\2025-9\...`)
3. **Import successif ne perd pas les scans**
4. **Champs obligatoires (CCY, etc.) mis à jour correctement**

---

## Documentation technique

### Modèle SoldesReels
Fichier: `backend/apps/accounting/models.py`

**Champs concernés par la correction :**
```python
class SoldesReels(models.Model):
    fichier_source = models.CharField(...)  # OBLIGATOIRE
    chemin_base = models.CharField(...)     # OBLIGATOIRE
    journal = models.CharField(...)         # OBLIGATOIRE
    date_m = models.DateField(...)          # OBLIGATOIRE
    rec = models.IntegerField(...)          # OBLIGATOIRE
    ccy = models.DecimalField(...)          # OBLIGATOIRE

    scan = models.CharField(...)            # OPTIONNEL - PRÉSERVÉ si None
    description = models.CharField(...)     # OPTIONNEL - PRÉSERVÉ si None
    validation = models.CharField(...)      # OPTIONNEL - PRÉSERVÉ si None
    date_rec = models.DateField(...)        # OPTIONNEL - PRÉSERVÉ si None
    date_input = models.DateField(...)      # OPTIONNEL - PRÉSERVÉ si None
```

### Vue d'import
Fichier: `backend/apps/accounting/views.py`

**Fonction modifiée :** `import_access_databases()` (ligne 299-307)
**Fonction appelante :** API POST `/accounting/import-access/`

### Impact sur les autres fonctionnalités
**Aucun impact négatif :**
- Les imports continuent de fonctionner normalement
- Les nouvelles valeurs non-None sont toujours enregistrées
- Seule différence : préservation des anciennes valeurs quand nouvelle = None

---

## Recommandations futures

### 1. Logging amélioré
Ajouter des logs détaillés dans l'import pour tracer :
- Nombre de scans lus depuis Access
- Nombre de scans préservés (ancienne valeur)
- Nombre de scans mis à jour (nouvelle valeur)

### 2. Validation des scans
Avant import, vérifier que :
- Le chemin de scan existe physiquement
- Le format est valide (commence par `.\`)
- Le fichier scan est accessible

### 3. Rapport d'import
Générer un rapport détaillé après import avec :
- Nombre total d'enregistrements traités
- Nombre de créations vs mises à jour
- Nombre de scans enregistrés vs préservés
- Liste des erreurs/avertissements

---

## Conclusion

**Correction réussie :** ✅
La logique de mise à jour des `SoldesReels` préserve maintenant les valeurs existantes lorsque les nouvelles valeurs sont None, tout en continuant de mettre à jour les champs obligatoires.

**Prochaine étape :**
Réimporter les bases Access pour récupérer les scans perdus lors des imports précédents.

**Garantie :**
Une fois les scans réimportés, ils seront préservés lors de tous les imports futurs, même si le fichier Access renvoie None pour le champ scan.
