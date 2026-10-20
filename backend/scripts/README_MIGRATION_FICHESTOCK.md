# Script de Migration FicheStock: product -> designation

## 📋 Contexte

Ce script a été créé suite à une correction du système de gestion des fiches de stock. Initialement, les fiches créées lors d'achats et de transferts utilisaient le champ `product`, mais la vue de consultation filtrait par `designation`. Cela causait l'invisibilité des achats et transferts dans les fiches de stock.

## 🔧 Corrections apportées

### Modèle (apps/inventory/models.py)
- ✅ Ajout du champ `reference` à FicheStock pour traçabilité

### Signals (apps/inventory/signals.py)
- ✅ Signal `create_fiche_stock_from_purchase`: Utilise `designation` au lieu de `product`
- ✅ Signal `create_fiche_stock_from_transfert`: Utilise `designation` au lieu de `product`
- ✅ Ajout du champ `reference` avec numéro de bon/transfert

### Vue (apps/inventory/views.py)
- ✅ Utilisation directe du champ `reference` au lieu de `getattr()`

## 🚀 Utilisation du script de migration

### Quand utiliser ce script?

Si vous avez des **anciennes fiches de stock** créées **AVANT** la correction des signals (16 novembre 2025), elles utilisaient `product` au lieu de `designation` et ne sont donc pas visibles dans la page fiches de stock.

### Comment exécuter le script?

```bash
cd backend
.venv\Scripts\python.exe scripts\migrate_fichestock_product_to_designation.py
```

Le script vous demandera confirmation avant de procéder.

### Que fait le script?

1. **Recherche** toutes les FicheStock avec:
   - `operation_type` = 'achat' ET `product` non null ET `designation` null
   - `operation_type` = 'transfert_*' ET `product` non null ET `designation` null

2. **Pour chaque fiche trouvée**:
   - Récupère l'item d'achat ou de transfert correspondant
   - Extrait la `designation` depuis cet item
   - Met à jour la fiche avec la `designation`
   - Ajoute la `reference` (numéro de bon) si elle est vide

3. **Affiche un rapport**:
   - Nombre de fiches migrées
   - Nombre d'erreurs
   - Statistiques finales

### Exemple de sortie

```
============================================================
Script de migration FicheStock: product -> designation
============================================================

Voulez-vous lancer la migration? (oui/non): oui

=== Migration des FicheStock Achats ===
Trouvé 15 fiche(s) d'achat à migrer
[OK] Migré fiche abc-123 - Tuyau PVC 32mm
[OK] Migré fiche def-456 - Robinet 1/2"
...
Résumé Achats: 15 migrées, 0 erreurs

=== Migration des FicheStock Transferts ===
Trouvé 8 fiche(s) de transfert à migrer
[OK] Migré fiche ghi-789 - Coude PVC 90° (transfert_entree)
...
Résumé Transferts: 8 migrées, 0 erreurs

=== Vérification de la migration ===

Achats:
  - Avec designation: 15
  - Restant à migrer: 0

Transferts:
  - Avec designation: 8
  - Restant à migrer: 0

[SUCCESS] Migration complete! Toutes les fiches ont été migrées.

============================================================
Migration terminée: 23 fiche(s) migrée(s)
============================================================
```

## ⚠️ Points d'attention

1. **Transaction atomique**: Chaque fiche est migrée dans une transaction séparée. Si une échoue, les autres continuent.

2. **Vérification**: Le script vérifie l'existence de la `designation` dans les items d'achat/transfert avant de migrer.

3. **Idempotent**: Le script peut être exécuté plusieurs fois sans risque. Il ignore les fiches déjà migrées.

4. **Sauvegarde recommandée**: Bien que le script soit sûr, il est recommandé de faire une sauvegarde de la base de données avant toute migration.

## 📊 Résultat attendu

Après la migration:
- Les achats apparaissent dans les fiches de stock avec `operation_type='achat'`
- Les transferts apparaissent avec `operation_type='transfert_entree'` ou `'transfert_sortie'`
- La colonne "Référence" affiche le numéro de bon d'achat ou de transfert
- Le stock cumulé est correctement calculé en incluant les achats et transferts

## 🔄 Pour les futurs achats/transferts

Les **nouveaux** achats et transferts créés **après** la correction des signals (16 novembre 2025) utilisent automatiquement `designation` et n'ont **pas besoin** de migration.

## 📝 Date de création

**16 novembre 2025** - Correction des signals et création du script de migration

## 👤 Auteur

Script créé suite à la demande de correction du workflow des fiches de stock.
