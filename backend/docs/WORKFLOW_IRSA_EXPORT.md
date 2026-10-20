# Workflow d'Export IRSA vers DiameX

## Vue d'ensemble

Ce document décrit le workflow complet d'export des paiements IRSA vers le système comptable DiameX, implémenté le 15 novembre 2025.

## Architecture

### Modèles

**PaiementIRSA** (`apps.employees.models`)
- `facture_imprimee` : Boolean (default False)
- `date_impression` : DateTime (nullable)
- Relations : `details` (PaiementIRSADetail)

**PaiementIRSADetail** (`apps.employees.models`)
- `paiement_irsa` : ForeignKey vers PaiementIRSA
- `salaire` : ForeignKey vers Salaire
- `employe_nom_complet` : CharField (dénormalisé)
- `montant_irsa` : DecimalField

**DiameXTemporaire** (`apps.accounting.models`)
- `paiement_irsa` : ForeignKey vers PaiementIRSA
- `type_transaction` : 'depense'
- `description` : Format spécifique (voir ci-dessous)
- `compte_code` : Compte IRSA du poste
- `detail` : Surnom de l'employé
- `activ` : Volet de l'employé
- `montant_out` : Montant IRSA exact (SANS arrondi)
- `date_m` : Date de paiement
- `info` : 'Hydria IRSA'
- `statut` : 'en_attente'

### Format d'export

**Description DiameX** :
```
_{préfixe_poste} {nom_complet}_IRSA_{année} {mois:02d}
```

**Exemples** :
- `_RESP Jean DUPONT_IRSA_2025 11`
- `_TECH Marie MARTIN_IRSA_2025 11`

**Compte (Cat)** : `Poste.compte_irsa.compte`

**Détail** : `Employe.surnom` ou `Employe.prenom` si surnom vide

**ACTIV** : `Employe.volet`

**Montant** : Montant exact SANS arrondi (contrairement aux salaires)
```python
montant_irsa = detail.montant_irsa  # Montant exact, pas d'arrondi
```

## Workflow Utilisateur

### Étape 1 : Création du paiement IRSA

1. Accéder à `/paiements-irsa/`
2. Cliquer sur "Nouveau paiement IRSA"
3. Sélectionner mois, année, date de paiement
4. Choisir les employés concernés
5. Le système calcule automatiquement les montants IRSA
6. Sauvegarder (statut = "brouillon")

### Étape 2 : Validation du paiement

1. Vérifier les montants dans la liste
2. Cliquer sur "Voir détails" pour vérifier employé par employé
3. Cliquer sur "Valider" (statut = "validé")

### Étape 3 : Génération de la facture

1. Cliquer sur "Générer facture" dans le menu Actions
2. Le système génère un fichier Excel avec :
   - En-tête : Organisation, période, date de paiement
   - Tableau : Liste des employés avec salaire brut, base imposable, IRSA
   - Totaux : Sommes par colonne
3. Le fichier est téléchargé automatiquement
4. Badge "Facture" passe à "Générée" (vert)

### Étape 4 : Impression et export (NOUVEAU)

1. **Imprimer la facture Excel** (étape manuelle utilisateur)
2. Retourner sur la page `/paiements-irsa/`
3. Cliquer sur "Marquer imprimée + Export" dans le menu Actions
   - ⚠️ Ce bouton n'apparaît que si :
     - `facture_generee = True`
     - `facture_imprimee = False`
4. Confirmer l'action dans le popup d'avertissement
5. Le système :
   - Marque `facture_imprimee = True`
   - Enregistre `date_impression = now()`
   - Pour chaque employé dans PaiementIRSADetail :
     - Récupère le poste via Salaire → GrilleSalaire → Contrat → Employe → Poste
     - Vérifie que le poste a un `compte_irsa` défini
     - Crée une ligne dans DiameXTemporaire avec le format ci-dessus
6. Affiche un message de confirmation :
   - Nombre de factures marquées
   - Nombre de lignes exportées
   - Liste des erreurs (si applicable)
7. Badge "Imprimée" passe à "Imprimée" (vert)

### Étape 5 : Validation et export final

1. Les lignes DiameXTemporaire sont en statut `'en_attente'`
2. L'administrateur peut les consulter dans l'interface de gestion DiameX
3. Après validation, les lignes sont exportées vers le système DiameX externe
4. (À implémenter : script d'export automatique ou manuel)

## Sécurité et Validations

### Contrôles côté serveur

1. **Vérification du compte IRSA** :
   - Si `Poste.compte_irsa` est NULL → Erreur
   - Message : `"{nom_employe}: Pas de compte IRSA défini pour le poste"`
   - La facture est quand même marquée comme imprimée
   - L'erreur est retournée dans la réponse

2. **Vérification des relations** :
   - Salaire → GrilleSalaire → Contrat → Employe doivent exister
   - Si chaîne incomplète → Erreur : "Données salariales incomplètes"

3. **Irréversibilité** :
   - Une fois `facture_imprimee = True`, impossible de modifier
   - Pas de bouton "Annuler l'impression" dans l'interface
   - Modification manuelle en base de données requise si nécessaire

### Filtrage des paiements

L'API filtre automatiquement par :
- Organisation de l'utilisateur (sécurité)
- Année, mois, statut (filtres utilisateur)

## APIs

### POST `/api/marquer-irsa-imprime/`

**Request Body** :
```json
{
    "paiement_ids": ["uuid1", "uuid2"],
    "mois": 11,
    "annee": 2025
}
```

**Response Success** :
```json
{
    "success": true,
    "message": "1 facture(s) marquée(s) comme imprimée(s), 15 ligne(s) exportée(s) vers DiameX",
    "nb_imprimes": 1,
    "nb_exportes": 15,
    "erreurs": []
}
```

**Response Partial Success** :
```json
{
    "success": true,
    "message": "1 facture(s) marquée(s) comme imprimée(s), 13 ligne(s) exportée(s) vers DiameX (2 erreur(s))",
    "nb_imprimes": 1,
    "nb_exportes": 13,
    "erreurs": [
        "Jean DUPONT: Pas de compte IRSA défini pour le poste",
        "Marie MARTIN: Données salariales incomplètes"
    ]
}
```

**Response Error** :
```json
{
    "success": false,
    "error": "Aucun paiement IRSA fourni"
}
```

### GET `/api/paiements-irsa-list/`

**Query Parameters** :
- `annee` : Année (ex: 2025)
- `mois` : Mois (1-12)
- `statut` : brouillon, valide, paye, all
- `organisation_id` : UUID de l'organisation

**Response** :
```json
{
    "success": true,
    "paiements": [
        {
            "id": "uuid",
            "organisation": "SOAKOJA",
            "mois": 11,
            "annee": 2025,
            "periode": "11/2025",
            "date_paiement": "2025-11-01",
            "nb_employes": 15,
            "montant_total_irsa": 1500000.00,
            "statut": "valide",
            "statut_display": "Validé",
            "facture_generee": true,
            "date_generation": "2025-11-15 10:30",
            "facture_imprimee": false,
            "date_impression": null
        }
    ],
    "total": 1
}
```

## Fichiers Modifiés/Créés

### Backend

**Modèles** :
- `backend/apps/employees/models.py` (lignes 466-477)
  - Ajout champs `facture_imprimee` et `date_impression` à PaiementIRSA

- `backend/apps/accounting/models.py` (lignes 42-50)
  - Ajout champ `paiement_irsa` à DiameXTemporaire

**Migrations** :
- `backend/apps/employees/migrations/0025_add_irsa_impression_fields.py`
- `backend/apps/accounting/migrations/0012_add_paiement_irsa_link.py`

**Vues** :
- `backend/apps/employees/views_irsa.py` (lignes 105-106)
  - Ajout champs dans api_paiements_irsa_list

- `backend/apps/employees/views_irsa_impression.py` (NOUVEAU)
  - Fonction `api_marquer_irsa_imprime()`

**URLs** :
- `backend/apps/employees/urls.py` (lignes 12, 128)
  - Import views_irsa_impression
  - Route api_marquer_irsa_imprime

### Frontend

**Template** :
- `backend/templates/employees/paiements_irsa_list.html`
  - Ligne 91 : Colonne "Imprimée" dans tableau
  - Lignes 308-312 : Badge "Imprimée" avec icône
  - Lignes 322-324 : Bouton "Marquer imprimée + Export"
  - Lignes 666-707 : Fonction JavaScript `marquerImprime()`

### Documentation

- `backend/docs/WORKFLOW_IRSA_EXPORT.md` (NOUVEAU)
  - Ce fichier

## Tests de Validation

### Checklist de tests

- [ ] Créer un paiement IRSA avec 2 employés
- [ ] Valider le paiement
- [ ] Générer la facture Excel
- [ ] Vérifier le badge "Facture" = "Générée"
- [ ] Vérifier l'apparition du bouton "Marquer imprimée + Export"
- [ ] Cliquer sur "Marquer imprimée + Export"
- [ ] Confirmer l'action dans le popup
- [ ] Vérifier le message de succès (2 lignes exportées)
- [ ] Vérifier le badge "Imprimée" = "Imprimée"
- [ ] Vérifier la disparition du bouton "Marquer imprimée + Export"
- [ ] Vérifier les 2 lignes dans DiameXTemporaire :
  - `type_transaction = 'depense'`
  - `description` = format correct
  - `compte_code` = compte IRSA du poste
  - `detail` = surnom employé
  - `activ` = volet employé
  - `montant_out` = montant exact (SANS arrondi)
  - `info = 'Hydria IRSA'`
  - `statut = 'en_attente'`

### Tests d'erreur

- [ ] Tester avec employé sans compte IRSA :
  - Vérifier message d'erreur dans la réponse
  - Vérifier que la facture est quand même marquée imprimée
  - Vérifier que les autres employés sont exportés

- [ ] Tester tentative de double marquage :
  - Vérifier que le bouton disparaît après premier marquage
  - Vérifier que l'API retourne 0 factures imprimées si relancée

## Différences avec le Workflow Salaires

| Aspect | Salaires | IRSA |
|--------|----------|------|
| **Modèle source** | Salaire | PaiementIRSADetail |
| **Label dans Description** | `_Salaire_` | `_IRSA_` |
| **Compte DiameX** | `Poste.compte_salaire` | `Poste.compte_irsa` |
| **Champ Info** | `'Hydria Salaires'` | `'Hydria IRSA'` |
| **Montant** | `Salaire.salaire_net_paye` | `PaiementIRSADetail.montant_irsa` |
| **Arrondi montant** | Oui (100 Ar près) | **NON - Montant exact** |
| **Lien DiameXTemporaire** | `salaire` | `paiement_irsa` |
| **Prorata suffix** | Oui (si est_prorata) | Non |

## Prochaines Étapes Suggérées

1. **Script d'export DiameX** : Créer un script pour envoyer les lignes `en_attente` vers DiameX
2. **Annulation d'impression** : Interface admin pour réinitialiser `facture_imprimee`
3. **Notification email** : Alerter le comptable quand nouvelles lignes en attente
4. **Validation par lot** : Marquer plusieurs paiements en une seule fois
5. **Rapport Excel** : Export des lignes DiameXTemporaire en Excel pour vérification
6. **Historique des exports** : Table dédiée pour tracer tous les exports avec date/utilisateur

## Points d'Attention

### ⚠️ CRITICAL

1. **Compte IRSA obligatoire** : Tous les postes doivent avoir un `compte_irsa` défini AVANT l'export
2. **Irréversible** : Une fois imprimée, la facture ne peut plus être modifiée (sauf intervention manuelle en base)
3. **SANS Arrondi** : Les montants IRSA sont exportés EXACTEMENT comme calculés (contrairement aux salaires qui sont arrondis)
4. **Format Description** : Doit commencer par `_` pour cohérence avec les salaires

### 🔍 À Vérifier Régulièrement

1. **Lignes en attente** : Consulter DiameXTemporaire pour voir les exports non validés
2. **Comptes IRSA** : S'assurer que tous les nouveaux postes ont un compte IRSA défini
3. **Montants** : Vérifier que les montants exacts (SANS arrondi) correspondent aux factures IRSA imprimées

## Références

- **Code source salaires** : `backend/apps/employees/views_fiches_impression.py`
- **CLAUDE.md** : Section "MODULE FICHES DE PAIE - IMPRESSION ET EXPORT DIAMEX"
- **Modèles** : `backend/apps/employees/models.py`, `backend/apps/accounting/models.py`
