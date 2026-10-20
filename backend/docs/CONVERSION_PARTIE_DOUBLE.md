# Conversion en Comptabilité Partie Double

## Vue d'ensemble

Ce module permet de convertir les écritures comptables de la base DiameX (système In/Out) en comptabilité partie double (système Débit/Crédit).

## Accès

**URL** : `http://localhost:8000/comptabilite/conversion-partie-double/`

**Menu** : Comptabilité → Conversion Partie Double

## Principe de conversion

### Correspondance In/Out ↔ Débit/Crédit

- **In = Crédit**
- **Out = Débit**

### Règles de conversion

Le système applique deux types de conversion selon la valeur de la colonne `Cat` (compte_code) :

#### 1. Cat = 00BOOK (Déjà en partie double)

Ces écritures sont déjà enregistrées en partie double dans DiameX. Elles génèrent **1 seule ligne** :

- **Compte** : Code Journal (calculé selon les règles du contrôle de conversion)
- **Débit** : Out
- **Crédit** : In

#### 2. Autres Cat (Conversion standard)

Toutes les autres écritures nécessitent une conversion. Elles génèrent **2 lignes** :

**Ligne 1** :
- **Compte** : Code Journal
- **Débit** : Out
- **Crédit** : In

**Ligne 2** (inversée) :
- **Compte** : Code Cat (calculé selon les règles)
- **Débit** : In (inversé)
- **Crédit** : Out (inversé)

### Calcul des codes

Le calcul des codes Journal et Cat suit exactement les mêmes règles que la page **Contrôle Conversion** :

#### Code Journal

- Si `Journal = vide` → Erreur
- Si `Journal = 00PERS` :
  - Si `PERS = 00SPLIT` → Code `401000`
  - Sinon chercher dans `employes.surnom` ou `fournisseurs.idxls` (insensible à la casse)
- Sinon chercher dans table `journaux.code`

#### Code Cat

- Si Cat est 6 chiffres → Déjà un code comptable
- Si `Cat = 00BOOK` → Utiliser Code Journal
- Si `Cat = 00FND1` → Code `742200` (Subventions d'exploitation)
- Si `Cat = 00FND2` → Code `742210` (Autres subventions d'exploitation)
- Si `Cat = 00PERS` :
  - Si `PERS = 00SPLIT` → Code `401000`
  - Sinon chercher dans `employes.code_tiers` ou `fournisseurs.code_tiers`

## Structure de la table résultante

### Colonnes de la table `ecritures_partie_double`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | UUID | Identifiant unique |
| `entree_diamex` | FK | Lien vers l'entrée DiameX source |
| `numero_ligne` | Integer | 1 ou 2 (pour les conversions doubles) |
| `rec` | Integer | Numéro de reçu |
| `date` | Date | Date de l'écriture |
| `compte` | String | Code comptable (6 chiffres) |
| `libelle` | String | Description |
| `debit` | Decimal | Montant au débit |
| `credit` | Decimal | Montant au crédit |
| `fournisseur` | String | Fournisseur |
| `detail` | String | Détail |
| `activ` | String | Activité |
| `financement` | String | Financement |
| `info` | String | Information |
| `id_lien` | String | UUID liant les 2 lignes d'une conversion |
| `scan` | URL | Lien vers le document scanné |
| `type_conversion` | Choix | `00BOOK` ou `standard` |

## Workflow d'utilisation

### 1. Vérifier les entrées convertibles

Avant de lancer la conversion, consulter la page **Contrôle Conversion** pour :
- Identifier les entrées convertibles
- Corriger les erreurs (codes introuvables, etc.)

### 2. Consulter les statistiques

La page affiche automatiquement :
- **Total DiameX** : Nombre total d'entrées dans la base
- **Déjà converties** : Nombre d'entrées déjà converties
- **Cat 00BOOK** : Nombre d'entrées déjà en partie double
- **Convertibles** : Nombre d'entrées valides selon le contrôle
- **À convertir** : Total - Déjà converties

### 3. Lancer la conversion

**Option 1 : Convertir les nouvelles entrées**
- Bouton : "Convertir toutes les entrées convertibles"
- Action : Convertit uniquement les entrées non encore converties
- Sécurité : Ne touche pas aux écritures existantes

**Option 2 : Reconvertir tout (force)**
- Bouton : "Reconvertir toutes (force)"
- Action : **SUPPRIME** toutes les écritures existantes et les recrée
- ⚠️ **ATTENTION** : Utiliser uniquement si correction nécessaire
- Demande confirmation

### 4. Consulter les résultats

Après conversion, un panneau affiche :
- **Total traité** : Nombre d'entrées traitées
- **Converties** : Nombre réussi
- **Cat 00BOOK** : Nombre de conversions simples (1 ligne)
- **Conversions standard** : Nombre de conversions doubles (2 lignes)
- **Erreurs** : Nombre d'échecs avec détails

### 5. Afficher les écritures converties

Bouton : "Afficher écritures converties"

Ouvre un tableau avec filtres :
- **Date début/fin** : Période
- **Compte** : Code comptable
- **Type** : Cat 00BOOK ou Conversion standard
- **Recherche** : Texte libre (libellé, compte, fournisseur, détail)

Le tableau affiche :
- Date, Rec, Compte, Libellé
- **Débit** : En gras, formaté avec séparateurs
- **Crédit** : En gras, formaté avec séparateurs
- Fournisseur, Type de conversion, Numéro de ligne
- **Équilibrée** : ✅ ou ❌ (vérifie que Débit = Crédit pour la paire)

## Exemples de conversion

### Exemple 1 : Cat = 00BOOK

**Entrée DiameX** :
```
Journal: BP
Cat: 00BOOK
In: 100000
Out: 0
PERS: -
```

**Code calculé** :
- Code Journal : `531000` (depuis table journaux où code='BP')

**Résultat (1 ligne)** :
```
Compte: 531000
Débit: 0
Crédit: 100000
```

### Exemple 2 : Conversion standard

**Entrée DiameX** :
```
Journal: BP
Cat: 601100
In: 0
Out: 50000
PERS: -
```

**Codes calculés** :
- Code Journal : `531000` (depuis table journaux où code='BP')
- Code Cat : `601100` (déjà 6 chiffres)

**Résultat (2 lignes)** :

**Ligne 1** :
```
Compte: 531000
Débit: 50000
Crédit: 0
```

**Ligne 2** :
```
Compte: 601100
Débit: 0
Crédit: 50000
```

### Exemple 3 : Journal = 00PERS

**Entrée DiameX** :
```
Journal: 00PERS
Cat: 621122
In: 0
Out: 300000
PERS: Jean
```

**Codes calculés** :
- PERS `Jean` → Employé avec surnom='Jean' et code_tiers='421001'
- Code Journal : `421001`
- Code Cat : `621122` (déjà 6 chiffres)

**Résultat (2 lignes)** :

**Ligne 1** :
```
Compte: 421001
Débit: 300000
Crédit: 0
```

**Ligne 2** :
```
Compte: 621122
Débit: 0
Crédit: 300000
```

## Gestion des erreurs

### Types d'erreurs

1. **Code journal introuvable**
   - Cause : Journal non présent dans table journaux
   - Solution : Ajouter le journal ou corriger l'entrée DiameX

2. **Code Cat introuvable**
   - Cause : Cat invalide (ni 6 chiffres, ni code spécial reconnu)
   - Solution : Corriger la valeur Cat dans DiameX

3. **PERS introuvable**
   - Cause : Surnom/IDxls absent des tables employes/fournisseurs
   - Solution : Ajouter l'employé/fournisseur ou corriger PERS

### Affichage des erreurs

Les erreurs sont affichées dans le panneau de résultats :
- Jusqu'à 10 erreurs détaillées
- Si plus de 10 : "... et X autres erreurs"
- Format : `Entrée {id}: {message d'erreur}`

## Vérification de cohérence

### Propriété `est_equilibree`

Chaque écriture possède une propriété qui vérifie :
- **Cat 00BOOK** : Toujours équilibrée (1 ligne suffit)
- **Conversions standard** : Débit total = Crédit total des 2 lignes
- Tolérance : 0.01 pour erreurs d'arrondi

### Utilisation dans l'interface

Une icône est affichée dans le tableau :
- ✅ Vert : Écriture équilibrée
- ❌ Rouge : Déséquilibre détecté (à corriger)

## ID Lien

Chaque paire de lignes (conversions standard) partage le même `id_lien` (UUID) :
- Permet de retrouver facilement les 2 lignes d'une même écriture
- Utile pour export, rapports, vérifications

## Export et utilisation

Les écritures converties peuvent être :
- **Exportées en Excel** : Pour import dans logiciel comptable
- **Utilisées pour analyses** : Balance, grand livre, journaux
- **Vérifiées** : Rapprochement avec documents sources

## Limitations

1. **Données source** : Qualité dépend de DiameX (garbage in, garbage out)
2. **Codes manquants** : Les entrées avec codes introuvables ne sont pas converties
3. **Pas de modification** : Une fois converties, les écritures ne sont pas synchronisées avec DiameX
4. **Reconversion** : En cas de modification de DiameX, utiliser "Reconvertir (force)"

## Conseils

1. **Avant conversion** : Vérifier via "Contrôle Conversion" et corriger les erreurs
2. **Test** : Faire un premier essai avec quelques entrées
3. **Sauvegarde** : Sauvegarder la base avant reconversion massive
4. **Vérification** : Contrôler les écritures converties avec filtres et recherche
5. **Documentation** : Noter les codes spéciaux utilisés (00BOOK, 00PERS, etc.)

## Maintenance

### Ajout de nouveaux codes spéciaux

Pour ajouter un nouveau code Cat spécial (ex: 00FND3) :

1. Modifier `views_controle_conversion.py` : Ajouter la règle de mapping
2. Modifier `views_conversion_partie_double.py` : Ajouter la même règle
3. Documenter dans CLAUDE.md et ce fichier

### Nettoyage

Pour supprimer toutes les écritures converties :

```python
from apps.accounting.models_partie_double import EcriturePartieDouble
EcriturePartieDouble.objects.all().delete()
```

Puis relancer la conversion.

## Fichiers du module

- **Modèle** : `apps/accounting/models_partie_double.py`
- **Vues** : `apps/accounting/views_conversion_partie_double.py`
- **Template** : `templates/accounting/conversion_partie_double.html`
- **URLs** : `apps/accounting/urls.py` (lignes 188-192)
- **Migration** : `apps/accounting/migrations/0019_ecriturepartiedouble.py`
