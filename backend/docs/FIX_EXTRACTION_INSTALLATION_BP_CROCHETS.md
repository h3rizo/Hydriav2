# Fix Extraction Installation BP/BF - Ignorer Texte entre Crochets

**Date** : 29 décembre 2025
**Contexte** : Pages de vérification et recoupement comptable

## Problème identifié

Dans les pages de vérification comptable, certaines descriptions d'installation BP/BF contiennent du texte entre crochets qui perturbait l'extraction de l'ouvrage :

**Exemple de description problématique** :
- `Paiement pour installation BP_81_Vohipeno [facilité de paiement]`

**Symptôme** : L'ouvrage n'était pas correctement extrait à cause du texte `[facilité de paiement]` qui perturbait le découpage par underscore.

## Cause

La fonction `extraire_installation_bp_bf()` utilisait `split('_')` pour découper la description en parties :

```python
# AVANT
parts = description.split('_')
# Pour "Paiement pour installation BP_81_Vohipeno [facilité de paiement]"
# parts = ['Paiement pour installation BP', '81', 'Vohipeno [facilité de paiement]']
#                                                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#                                                   Le texte entre crochets pollue le nom de l'ouvrage
```

Le dernier élément contenait le nom de l'ouvrage **PLUS** le texte entre crochets, ce qui empêchait la recherche dans la base de données.

## Solution

Ajout d'une étape de **nettoyage préalable** pour supprimer tout texte entre crochets avant de découper la description :

```python
# APRÈS
# Nettoyer le texte entre crochets (ex: [facilité de paiement])
# Pattern: tout ce qui est entre [ et ] (inclus)
description_clean = re.sub(r'\s*\[.*?\]\s*', ' ', description).strip()

parts = description_clean.split('_')
# Pour "Paiement pour installation BP_81_Vohipeno [facilité de paiement]"
# description_clean = "Paiement pour installation BP_81_Vohipeno"
# parts = ['Paiement pour installation BP', '81', 'Vohipeno']
#                                                   ^^^^^^^^ Nom propre, sans pollution
```

### Détails du pattern regex

**Pattern** : `r'\s*\[.*?\]\s*'`

**Explication** :
- `\s*` : Zéro ou plusieurs espaces avant le crochet ouvrant
- `\[` : Crochet ouvrant littéral (échappé)
- `.*?` : N'importe quel caractère (sauf retour à la ligne), le moins possible (non-greedy)
- `\]` : Crochet fermant littéral (échappé)
- `\s*` : Zéro ou plusieurs espaces après le crochet fermant

**Remplacement** : `' '` (un espace simple)

**Effet** :
- `"Vohipeno [facilité de paiement]"` → `"Vohipeno "`
- `"Vohipeno[facilité]"` → `"Vohipeno "`
- `"Vohipeno [info1] [info2]"` → `"Vohipeno "` (tous les crochets supprimés)

Le `.strip()` final supprime les espaces en trop.

## Résultats des tests

### Test 1 : `Paiement pour installation BP_81_Vohipeno [facilité de paiement]`

✅ **Résultat** :
- Ouvrage nom : `Vohipeno`
- Ouvrage obj : `Vohipeno` (objet trouvé dans la base)
- Point eau IDXLS : `81`

### Test 2 : `Paiement demande devis installation BP_78_Vohipeno` (rétrocompatibilité)

✅ **Résultat** :
- Ouvrage nom : `Vohipeno`
- Ouvrage obj : `Vohipeno` (objet trouvé dans la base)
- Point eau IDXLS : `78`

**Note** : Le format sans crochets continue de fonctionner normalement.

### Test 3 : `_RAVAOJANAHARY Hanta_Paiement pour installation BP_01_Antsahafilo [facilité]`

✅ **Résultat** :
- Ouvrage nom : `Antsahafilo`
- Ouvrage obj : `Antsahafilo` (objet trouvé dans la base)
- Point eau IDXLS : `01`

**Note** : Le format avec nom de personne fonctionne également avec les crochets.

### Test 4 : `Paiement pour installation BP_81_Vohipeno [facilité] [autre info]`

✅ **Résultat** :
- Ouvrage nom : `Vohipeno`
- Ouvrage obj : `Vohipeno` (objet trouvé dans la base)
- Point eau IDXLS : `81`

**Note** : Les crochets multiples sont tous supprimés correctement.

## Impact

Cette amélioration permet de reconnaître les descriptions d'installation BP/BF même lorsqu'elles contiennent du texte informatif entre crochets (ex: `[facilité de paiement]`, `[acompte]`, etc.).

### Pages bénéficiaires

Toutes les pages qui utilisent `extraire_ouvrage_et_mois_generique()` avec le compte `748201` (Installation BP/BF) bénéficient automatiquement :

1. ✅ **Page Vérification avec ouvrage** (`/comptabilite/verification-avec-ouvrage/`)
2. ✅ **Page Recoupement relevés** (`/comptabilite/recoupement/releves/`)
3. ✅ **Dashboard paiements volume** (`/comptabilite/dashboard-paiements-volume/`)

### Cas d'usage typiques

**Textes entre crochets fréquents** :
- `[facilité de paiement]` : Paiement échelonné
- `[acompte]` : Premier versement
- `[solde]` : Dernier versement
- `[complément]` : Paiement complémentaire
- `[régularisation]` : Ajustement de compte

Tous ces cas sont maintenant gérés automatiquement.

## Fichier modifié

**Fichier** : `backend/apps/accounting/extracteurs_description.py`

**Emplacement** : Lignes 615-661

**Fonction** : `extraire_installation_bp_bf(description)`

**Changements** :
1. Ajout commentaire dans docstring : "Ignore le texte entre crochets [...]"
2. Ajout exemple avec crochets dans docstring
3. Ajout code de nettoyage (lignes 657-659)

## Tests de validation

- [x] Test format avec crochets : `Paiement pour installation BP_81_Vohipeno [facilité de paiement]`
- [x] Test format classique sans crochets (rétrocompatibilité)
- [x] Test format avec nom de personne + crochets
- [x] Test format avec crochets multiples
- [x] Django check : 0 erreurs
- [x] Extraction objet ouvrage fonctionnelle
- [x] Extraction IDXLS fonctionnelle

## Déploiement

**⚠️ Aucune migration requise** : Modification uniquement dans le code Python (fonction d'extraction).

**Étapes** :
1. Commit et push du fichier `extracteurs_description.py`
2. Redémarrer le serveur Django
3. Vérifier les pages de vérification comptable

**Commande de redémarrage** :
```bash
# Windows
Ctrl+C (arrêter le serveur actuel)
python manage.py runserver
```

## Compatibilité

**✅ Rétrocompatibilité totale** : Les descriptions sans crochets continuent de fonctionner exactement comme avant.

**✅ Pas de régression** : Le nettoyage des crochets ne perturbe pas les autres formats d'extraction.

## Documentation

**Scripts de test créés** :
- `backend/test_extraction_installation_bp_crochets.py` - Tests unitaires pour ce fix

**Documentation associée** :
- `backend/docs/FIX_EXTRACTION_NETTOYAGE_BF_SANS_MONTANT.md` - Fix précédent pour Nettoyage BF
- `backend/docs/EXTRACTION_MULTI_PAIEMENTS_AMELIORATION.md` - Extraction multi-paiements
- `backend/CLAUDE.md` - Contexte général du projet

## Prochaines améliorations possibles

1. **Extraction du texte entre crochets** : Stocker cette information pour traçabilité (facilité, acompte, etc.)
2. **Validation du format** : Vérifier que le texte entre crochets correspond à une liste prédéfinie
3. **Statistiques** : Compter combien de paiements ont des facilités de paiement
4. **Alertes** : Notifier quand un paiement avec facilité n'est pas complété
