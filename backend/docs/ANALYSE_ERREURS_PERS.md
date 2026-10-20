# Analyse des erreurs PERS - Guide d'utilisation

## Vue d'ensemble

Lorsque la conversion en partie double génère des erreurs avec des entrées ayant `Journal=00PERS` ou `Cat=00PERS`, il est essentiel d'identifier quelles valeurs PERS posent problème et pourquoi.

## Accès

**Page** : Conversion Partie Double
**Bouton** : "Analyser erreurs PERS" (rouge, avec icône triangle d'avertissement)

## Fonctionnalités

### 1. Statistiques globales

Affiche 4 indicateurs clés :

- **Total valeurs PERS** : Nombre de valeurs PERS uniques trouvées dans les entrées avec Journal=00PERS ou Cat=00PERS
- **Trouvables** : Nombre de valeurs PERS qui peuvent être résolues (employé, fournisseur ou '00SPLIT')
- **Introuvables** : Nombre de valeurs PERS qui ne peuvent PAS être résolues
- **Entrées affectées** : Nombre total d'entrées DiameX qui seront en erreur

### 2. Tableau détaillé

Affiche jusqu'à 50 valeurs PERS les plus fréquentes avec :

| Colonne | Description | Exemple |
|---------|-------------|---------|
| **Valeur PERS** | La valeur exacte du champ PERS | `2513`, `Jean`, `00SPLIT` |
| **Nombre d'entrées** | Combien d'entrées DiameX utilisent cette valeur | `156` |
| **Type** | Où cette valeur a été trouvée | Employé / Fournisseur / Split / Introuvable |
| **État** | Si la conversion peut fonctionner | OK (vert) / Introuvable (rouge) |

### 3. Codes couleur

**Badges Type** :
- 🔵 **Bleu (info)** : Employé - Trouvé dans `employes.surnom`
- 🟠 **Orange (warning)** : Fournisseur - Trouvé dans `fournisseurs.idxls`
- ⚪ **Gris (ghost)** : Split, vide ou introuvable

**Badges État** :
- ✅ **Vert (success)** : OK - La valeur peut être convertie
- ❌ **Rouge (error)** : Introuvable - La valeur ne peut PAS être convertie

## Messages d'erreur améliorés

Lors de la conversion, les erreurs affichent maintenant la valeur PERS problématique :

**Avant** :
```
Entrée 62194: Code Cat introuvable pour 00PERS
```

**Après** :
```
Entrée 62194: Code Cat introuvable - Cat=00PERS, PERS=2513
```

Cela permet d'identifier immédiatement :
- La valeur PERS qui pose problème (`2513`)
- Si c'est un Journal ou un Cat qui utilise 00PERS

## Résolution des erreurs

### Cas 1 : Valeur PERS correspond à un fournisseur sans code_tiers

**Problème** : Le fournisseur existe dans la base mais n'a pas de `code_tiers` renseigné.

**Exemple** :
```
PERS: 2513
Type: Fournisseur
État: Introuvable
```

**Solution** :
1. Aller dans **Référentiel → Fournisseurs**
2. Rechercher par ID XLS : `2513`
3. Modifier le fournisseur et renseigner le champ **Code Tiers** (6 chiffres)
4. Relancer la conversion

### Cas 2 : Valeur PERS correspond à un employé sans code_tiers

**Problème** : L'employé existe mais n'a pas de `code_tiers` renseigné.

**Exemple** :
```
PERS: Jean
Type: Employé
État: Introuvable
```

**Solution** :
1. Aller dans **Employés → Liste des employés**
2. Rechercher par surnom : `Jean`
3. Modifier l'employé et renseigner le champ **Code Tiers** (6 chiffres)
4. Relancer la conversion

### Cas 3 : Valeur PERS n'existe nulle part

**Problème** : La valeur PERS n'est ni un surnom d'employé, ni un IDxls de fournisseur.

**Exemple** :
```
PERS: 9999
Type: Introuvable
État: Introuvable
```

**Solutions possibles** :

**A. Créer le fournisseur manquant** :
1. Aller dans **Référentiel → Fournisseurs**
2. Créer un nouveau fournisseur
3. Renseigner **ID XLS** : `9999`
4. Renseigner **Code Tiers** : `4XXXXX` (6 chiffres)
5. Relancer la conversion

**B. Créer l'employé manquant** :
1. Aller dans **Employés → Nouveau**
2. Renseigner **Surnom** : `9999`
3. Renseigner **Code Tiers** : `4XXXXX` (6 chiffres)
4. Relancer la conversion

**C. Corriger les données DiameX** :
Si la valeur PERS est une erreur de saisie :
1. Identifier les entrées DiameX concernées
2. Corriger le champ `pers` dans la base
3. Relancer la conversion

### Cas 4 : Valeur PERS vide

**Problème** : Le champ PERS est vide ou NULL.

**Exemple** :
```
PERS: (vide)
Type: Introuvable
État: Introuvable
```

**Solution** :
1. Identifier les entrées DiameX avec `pers IS NULL` ou `pers = ''`
2. Renseigner une valeur PERS valide ou un code comptable fixe
3. Relancer la conversion

## Workflow recommandé

### 1. Première tentative de conversion
```
1. Cliquer "Convertir toutes les entrées"
2. Observer les erreurs (ex: "1429 erreurs")
```

### 2. Analyser les erreurs PERS
```
1. Cliquer "Analyser erreurs PERS"
2. Observer les statistiques :
   - Total valeurs PERS: 45
   - Trouvables: 30
   - Introuvables: 15
   - Entrées affectées: 1,429
```

### 3. Identifier les valeurs les plus problématiques
```
Trier le tableau par "Nombre d'entrées" (déjà trié par défaut)
Exemple:
- PERS: 2513, Entrées: 856 ← Priorité 1 (plus d'impact)
- PERS: 4567, Entrées: 245 ← Priorité 2
- PERS: Jean, Entrées: 150 ← Priorité 3
```

### 4. Résoudre les erreurs par ordre de priorité
```
Pour chaque valeur PERS introuvable :
1. Vérifier si c'est un employé ou fournisseur
2. Renseigner le code_tiers manquant
3. OU créer l'entité manquante
```

### 5. Reconvertir
```
1. Cliquer "Reconvertir toutes (force)"
2. Vérifier que le nombre d'erreurs a diminué
3. Répéter 2-5 jusqu'à 0 erreur
```

## Limites

1. **Top 50 uniquement** : Le tableau affiche les 50 valeurs PERS les plus fréquentes
2. **Pas de modification directe** : Il faut aller dans les modules Employés/Fournisseurs pour corriger
3. **Case-insensitive** : La recherche est insensible à la casse (Jean = jean = JEAN)

## Conseils

1. **Commencer par les plus fréquents** : Résoudre une valeur PERS qui affecte 800 entrées est plus efficace que résoudre 10 valeurs à 5 entrées chacune

2. **Vérifier les doublons** : Certaines valeurs PERS peuvent être des variantes (ex: "Jean" et "jean" sont la même chose)

3. **Documenter les codes tiers** : Tenir une liste des codes tiers utilisés pour éviter les doublons
   - Employés : 421001-421999
   - Fournisseurs : 401001-499999

4. **Contrôler en amont** : Utiliser la page **Contrôle Conversion** AVANT de lancer la conversion pour identifier les erreurs

## Exemples réels

### Exemple 1 : Fournisseur sans code tiers

**Analyse** :
```
PERS: 2513
Nombre: 856 entrées
Type: Fournisseur
État: Introuvable
```

**Action** :
```sql
-- Dans la base PostgreSQL
SELECT * FROM fournisseurs WHERE idxls = '2513';
-- Résultat: LAHA BRUNO, code_tiers=NULL

UPDATE fournisseurs
SET code_tiers = '401234'
WHERE idxls = '2513';
```

**Résultat** : 856 erreurs résolues en 1 action !

### Exemple 2 : Employé sans code tiers

**Analyse** :
```
PERS: Victorien
Nombre: 245 entrées
Type: Employé
État: Introuvable
```

**Action** :
```
Interface web:
1. Employés → Liste
2. Rechercher "Victorien"
3. Modifier → Code Tiers: 421045
4. Enregistrer
```

**Résultat** : 245 erreurs résolues !

## Maintenance

Pour éviter les erreurs à l'avenir :

1. **Toujours renseigner code_tiers** lors de la création d'un employé/fournisseur
2. **Valider les imports DiameX** avant conversion
3. **Utiliser l'analyse PERS régulièrement** pour détecter les nouveaux problèmes

## Voir aussi

- [Contrôle Conversion](CONTROLE_CONVERSION.md)
- [Conversion Partie Double](CONVERSION_PARTIE_DOUBLE.md)
- [Guide des codes tiers](CODE_TIERS_GUIDE.md)
