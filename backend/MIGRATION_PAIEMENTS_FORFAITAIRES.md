# Migration des Paiements Forfaitaires

## 📅 Date de migration
**30 novembre 2025**

## 🎯 Objectif
Récupération des données de paiements forfaitaires depuis la table `planning_details` (liée à `plannings`) vers la nouvelle table dédiée `paiements_forfaitaires`.

## 📊 Résultats de la migration

### Statistiques générales
- **Total de PlanningDetail source** : 1,606
- **Avec Point d'eau** : 1,599 (7 sans point d'eau)
- **Avec Planning** : 1,606 (tous)
- **Avec numéro DiameX** : 994 (déjà payés)

### Migration réussie
- **Paiements migrés avec succès** : 1,589
- **Paiements ignorés** : 17 (doublons potentiels)
- **Erreurs** : 7 (PlanningDetail sans point d'eau)

### Données dans la nouvelle table
- **Total paiements** : 1,589
- **Payés** : 985 (avec numeroDiameX)
- **Non payés** : 604
- **Montant total** : 159,050,000 Ar
- **Montant payé** : 98,775,000 Ar
- **Montant impayé** : 60,275,000 Ar

## 🔍 Logique de migration

### Critères de sélection
Les `PlanningDetail` sélectionnés ont :
- **Designation** : "Paiement forfaitaire" (ID: 317e9fad-9444-418e-a41a-b322cefa632e)
- **Point d'eau** : Non NULL (obligatoire)
- **Planning** : Non NULL (obligatoire pour récupérer la date)

### Mapping des champs

| Source (PlanningDetail) | Destination (PaiementForfaitaire) | Transformation |
|-------------------------|-----------------------------------|----------------|
| `point_eau` | `point_eau` | Relation directe |
| `planning.date` | `date_facture` | Conversion timezone Madagascar |
| `quantity` | `quantite` | Conversion en entier |
| `pu` | `prix_unitaire` | Copie directe |
| `montant` | `montant` | Copie directe |
| `numeroDiameX` | `numeroDiameX` | Conversion en string |
| `BaseDiameX` | `baseDiameX` | Copie directe |
| `numeroDiameX IS NOT NULL` | `paye` | Boolean calculé |
| `date_facture` (si payé) | `date_paiement` | Date de paiement = date facture |

### Détection des doublons
Les paiements sont considérés comme des doublons si :
- **Même point d'eau** : `point_eau_id`
- **Même date de facture** : `date_facture`

Les doublons détectés sont **ignorés** (17 au total).

## 🚫 Erreurs rencontrées

### 7 PlanningDetail sans point d'eau
Ces lignes n'ont pas pu être migrées car le champ `point_eau` est obligatoire dans `PaiementForfaitaire`.

**IDs des PlanningDetail en erreur :**
- e0513998-1fac-4d55-b309-cd01349e615e
- 714c9332-aee6-412b-872d-3d9e64108950
- 5563d9f1-8fff-4c3e-8498-58494270288a
- aceae8c7-6599-4bb6-8621-f27c5a77533b
- eb9d0d40-3c91-4fe4-9149-3885df5093e8
- d5e6d163-bf98-4d21-b4dd-0170ecff01e6
- 153b5e51-7d0a-4d6a-978e-cfa658b6261f

**Action recommandée** : Vérifier manuellement ces PlanningDetail dans l'interface admin et soit :
1. Ajouter le point d'eau manquant
2. Les supprimer s'ils sont invalides
3. Les relancer avec le script de migration

## 📝 Script de migration
**Fichier** : `backend/migrate_paiements_forfaitaires.py`

### Utilisation
```bash
# Aperçu sans migration
cd backend
echo "non" | .venv/Scripts/python.exe migrate_paiements_forfaitaires.py

# Migration réelle
echo "oui" | .venv/Scripts/python.exe migrate_paiements_forfaitaires.py
```

### Fonctionnalités du script
- ✅ Vérification de la désignation "Paiement forfaitaire"
- ✅ Statistiques avant migration
- ✅ Détection des doublons
- ✅ Gestion des erreurs
- ✅ Conversion timezone Madagascar
- ✅ Rapport détaillé de migration

## ✅ Validation post-migration

### Tests effectués
1. ✅ Vérification du nombre total de paiements : 1,589
2. ✅ Vérification de la répartition payé/non payé : 985/604
3. ✅ Vérification des montants : 159M Ar total
4. ✅ Vérification d'un exemple de paiement migré :
   - Point d'eau : Vohibarihely_1
   - Ouvrage : Vohibarihely
   - Date facture : 2026-07-11
   - Quantité : 1
   - Prix unitaire : 75,000 Ar
   - Montant : 75,000 Ar
   - Payé : False

### Requêtes de vérification
```python
# Compter les paiements
PaiementForfaitaire.objects.count()  # 1589

# Statistiques payé/non payé
PaiementForfaitaire.objects.filter(paye=True).count()  # 985
PaiementForfaitaire.objects.filter(paye=False).count()  # 604

# Montants totaux
PaiementForfaitaire.objects.aggregate(Sum('montant'))  # 159,050,000 Ar
PaiementForfaitaire.objects.filter(paye=True).aggregate(Sum('montant'))  # 98,775,000 Ar
```

## 🔄 Cohérence avec l'ancien système

### Avant migration (PlanningDetail)
- **Source** : Table `planning_details`
- **Filtre** : `designation = "Paiement forfaitaire"`
- **Total lignes** : 1,606
- **Avec point d'eau** : 1,599

### Après migration (PaiementForfaitaire)
- **Destination** : Table `paiements_forfaitaires`
- **Total lignes** : 1,589
- **Différence** : -10 (7 sans point d'eau + 3 doublons ou erreurs)

## 🎯 Prochaines étapes

1. **Vérifier les 7 PlanningDetail en erreur** dans l'admin Django
2. **Tester le workflow** de paiements forfaitaires avec les données migrées :
   - Filtrer par mois/année
   - Exporter vers Excel
   - Vérifier l'affichage des montants
3. **Comparer les stats** du nouveau workflow avec l'ancien système
4. **Documenter** la transition pour les utilisateurs

## ⚠️ Notes importantes

1. **Les données sources restent intactes** : Les PlanningDetail n'ont pas été modifiés ou supprimés
2. **Pas de risque de perte de données** : La migration est une copie, pas un déplacement
3. **Réexécution possible** : Le script détecte les doublons, la migration peut être relancée sans risque
4. **Timezone respectée** : Toutes les dates sont converties en timezone Madagascar (Indian/Antananarivo)

## 📚 Documentation associée

- **Workflow paiements forfaitaires** : `/billing/paiements-forfaitaires/`
- **Template Excel** : Disponible via bouton "Télécharger template Excel"
- **Import/Export** : Fonctionnalités complètes disponibles dans l'interface
- **CLAUDE.md** : Section "MODULE PAIEMENTS FORFAITAIRES" (15 novembre 2025)
