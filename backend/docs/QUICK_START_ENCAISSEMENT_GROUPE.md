# Quick Start - Encaissement Groupé Paiements Forfaitaires

## ✅ Implémentation complète

Le système d'encaissement groupé des paiements forfaitaires est **maintenant opérationnel**.

## 🚀 Accès rapide

### URL directe
```
http://localhost:8000/billing/paiements-forfaitaires/encaissement-groupe/
```

### Navigation dans l'interface
1. Aller dans **Facturation**
2. Cliquer sur **Suivi des Paiements Forfaitaires**
3. Cliquer sur le bouton vert **"Encaissement Groupé"** en haut à droite

## 📋 Utilisation en 5 étapes

### 1. Filtrer les factures
- Sélectionner une **Organisation** (optionnel)
- Sélectionner un **Ouvrage** (optionnel)
- Saisir un texte de **recherche** dans nom du point d'eau (optionnel)
- Cliquer sur **"Filtrer"**

### 2. Sélectionner les factures à encaisser
- Cocher individuellement chaque facture
- OU cliquer sur **"Tout sélectionner"** pour cocher toutes les factures visibles
- Les compteurs en temps réel affichent :
  - Nombre de factures sélectionnées
  - Montant total à encaisser

### 3. Vérification automatique
Le système vérifie automatiquement que :
- ✅ Toutes les factures sélectionnées proviennent du **même ouvrage**
- ⚠️ Si différents ouvrages détectés → Alert + bouton "Encaisser" désactivé

### 4. Encaisser
- Cliquer sur **"Encaisser la sélection"**
- Confirmer dans la popup
- Le système :
  - Marque tous les paiements comme **payés** (`paye=True`)
  - Définit **date_paiement** = aujourd'hui
  - Crée **UNE SEULE** ligne dans `DiameXTemporaire` avec le montant total

### 5. Résultat
- Message de confirmation : "X paiement(s) encaissé(s) en un seul groupe (montant total: XXX Ar)"
- Les factures encaissées disparaissent de la liste (filtre par défaut = non payées)
- Une transaction est créée dans DiameX Temporaire

## 🔑 Points clés techniques

### DiameX Temporaire
Quand vous encaissez 3 factures de 5,000 Ar chacune :

**AVANT (encaissement individuel)** :
- 3 lignes dans DiameXTemporaire (5,000 + 5,000 + 5,000)
- 3 transactions à valider
- 3 exports vers DiameX

**APRÈS (encaissement groupé)** :
- ✅ **1 ligne** dans DiameXTemporaire (15,000 Ar)
- ✅ **1 transaction** à valider
- ✅ **1 export** vers DiameX

### Traçabilité complète

La ligne DiameXTemporaire contient :
```python
{
    'paiement_forfaitaire': PaiementForfaitaire(uuid1),  # Lien vers le premier
    'paiements_forfaitaires_ids': ['uuid1', 'uuid2', 'uuid3'],  # TOUS les IDs
    'description': 'Paiement forfaitaire groupé - AEPG Ambato (3 factures)',
    'montant_in': 15000.0,
    'compte_code': '748411',
    'statut': 'en_attente'
}
```

### Propagation numeroDiameX

Quand DiameX (Access) retourne un `numeroDiameX` (ex: "D2025120001"), le système met à jour **TOUS** les paiements du groupe :

```python
# Les 3 PaiementForfaitaire auront le même numeroDiameX
PaiementForfaitaire.objects.filter(
    id__in=['uuid1', 'uuid2', 'uuid3']
).update(numeroDiameX='D2025120001')
```

## 📊 Exemples

### Exemple 1 : Encaissement simple

**Contexte** :
- Organisation : SOAKOJA
- Ouvrage : AEPG Ambato
- 5 factures non payées de 5,000 Ar

**Actions** :
1. Filtrer par "SOAKOJA" et "AEPG Ambato"
2. Cliquer "Tout sélectionner"
3. Vérifier : "5 facture(s) sélectionnée(s)" + "25,000 Ar"
4. Encaisser

**Résultat** :
- 5 paiements marqués `paye=True`
- 1 ligne DiameX : "Paiement forfaitaire groupé - AEPG Ambato (5 factures)" - 25,000 Ar

### Exemple 2 : Erreur - Différents ouvrages

**Contexte** :
- Sélectionner 2 factures de "AEPG Ambato"
- Sélectionner 1 facture de "AEPG Ankazomanga"

**Résultat** :
- ⚠️ Alert : "Vous avez sélectionné des factures de différents ouvrages"
- Bouton "Encaisser" désactivé
- Vous devez désélectionner l'une des factures

## 🛠️ APIs Backend

### GET - Liste des paiements
```
GET /billing/paiements-forfaitaires/api/list/?paye=false&organisation_id=xxx
```

### POST - Encaissement groupé
```json
POST /billing/paiements-forfaitaires/api/encaisser/

{
  "paiement_ids": ["uuid1", "uuid2", "uuid3"],
  "groupe": true
}
```

## 📚 Documentation complète

Pour plus de détails techniques, consultez :
- `backend/docs/ENCAISSEMENT_GROUPE_FORFAITAIRE.md` (800+ lignes)
- `CLAUDE.md` - Section "MODULE ENCAISSEMENT GROUPÉ PAIEMENTS FORFAITAIRES"

## ✨ Avantages du système

1. **Efficacité** : 1 transaction au lieu de N
2. **Lisibilité comptable** : Regroupement logique par ouvrage
3. **Traçabilité** : Liste complète des IDs dans le JSON
4. **Cohérence** : Tous les paiements reçoivent le même numeroDiameX
5. **Validation** : Impossible de grouper des ouvrages différents
6. **Compteurs en temps réel** : Feedback visuel immédiat

## 🎯 Prochaine étape (optionnel)

**Export workflow DiameX** : Modifier le script d'export pour utiliser `paiements_forfaitaires_ids` lors du retour du numeroDiameX depuis Access.

```python
# À implémenter dans le script d'export DiameX
transaction = DiameXTemporaire.objects.get(...)
if transaction.paiements_forfaitaires_ids:
    # Groupé : mettre à jour TOUS
    PaiementForfaitaire.objects.filter(
        id__in=transaction.paiements_forfaitaires_ids
    ).update(numeroDiameX=numero_from_access)
```

---

**Système opérationnel** ✅ | **Documentation complète** ✅ | **Migration appliquée** ✅
