# Documentation - Prévisions Manuelles

## Vue d'ensemble

Le système de prévisions manuelles permet aux utilisateurs de saisir directement des recettes ou dépenses "autres" qui ne sont pas calculées automatiquement par le système.

**Date de création** : 14 décembre 2025

## Fonctionnalité

### Accès

**Page** : Facturation → Prévisions Budgétaires → Bouton "Configuration" → Onglet "Prévisions Manuelles"

**URL** : `http://localhost:8000/facturation/previsions/` (modal configuration)

### Types de prévisions manuelles

- **Recette Autre** (`recette_autre`) : Recettes non calculées automatiquement
- **Dépense Autre** (`depense_autre`) : Dépenses non calculées automatiquement

### Exemples d'utilisation

**Recettes** :
- Subventions exceptionnelles
- Dons
- Produits financiers
- Autres recettes imprévues

**Dépenses** :
- Dépenses exceptionnelles
- Amendes ou pénalités
- Frais divers non récurrents
- Autres dépenses ponctuelles

## Interface utilisateur

### Modal de configuration avec tabs

Le modal de configuration a été modifié pour inclure deux onglets :

1. **Paramètres** : Configuration existante (nb PE, tarifs, etc.)
2. **Prévisions Manuelles** : Nouvelle section pour saisir des prévisions manuelles

### Section Prévisions Manuelles

**Composants** :

1. **Formulaire d'ajout**
   - Type : Recette Autre / Dépense Autre
   - Mois : Janvier à Décembre
   - Compte : Liste déroulante avec 122 comptes (codes à 5 chiffres)
   - Libellé : Description de la prévision
   - Quantité : Nombre d'unités
   - Prix unitaire : Prix par unité en Ar
   - Montant (calculé) : Quantité × Prix unitaire (lecture seule)

2. **Tableau des prévisions manuelles**
   - Type (badge coloré : vert pour recette, rouge pour dépense)
   - Mois
   - Compte
   - Libellé
   - Quantité (2 décimales)
   - Prix Unitaire (formaté avec séparateurs)
   - In (Recette) - montant en gras si > 0
   - Out (Dépense) - montant en gras si > 0
   - Montant (total)
   - Actions (bouton supprimer)

3. **Fonctionnalités**
   - Ajout instantané avec le bouton "Ajouter"
   - Calcul automatique du montant lors de la saisie
   - Suppression individuelle avec confirmation
   - Rechargement automatique après chaque action
   - Affichage "Aucune prévision manuelle" si liste vide

## Architecture technique

### Modifications fichiers

#### 1. Template HTML

**Fichier** : `backend/templates/billing/previsions_budget.html`

**Modifications** (lignes 237-395, 861-1024) :
- Modal agrandi : `max-w-5xl`
- Système de tabs avec DaisyUI
- Formulaire d'ajout complet avec 7 champs
- Dropdown dynamique des comptes (122 options depuis BDD)
- Tableau responsive avec 10 colonnes
- JavaScript pour gestion des tabs et des actions
- Fonction `calculerMontant()` pour calcul auto

#### 2. Vue API

**Fichier** : `backend/apps/billing/views_previsions.py`

**Modifications** (lignes 21, 25, 51-67, 75-108) :

1. **Import des comptes** (lignes 21, 25) :
```python
from apps.organization.models import Base, Ouvrage, Compte
import re
```

2. **Récupération des comptes à 5 chiffres** (lignes 51-67) :
```python
# Récupérer les comptes avec codes à 5 chiffres pour le dropdown
comptes = Compte.objects.all()
comptes_5_chiffres = [
    {'code': c.compte, 'libelle': c.nom_compte}
    for c in comptes
    if re.match(r'^\d{5}', c.compte)
]
comptes_5_chiffres_sorted = sorted(comptes_5_chiffres, key=lambda x: x['code'])

context = {
    # ...
    'comptes': comptes_5_chiffres_sorted,
}
```

3. **Support POST avec nouveaux champs** (lignes 75-108) :
```python
@require_http_methods(["GET", "POST"])
def api_previsions_list(request):
    # Création d'une prévision manuelle
    if request.method == "POST":
        data = json.loads(request.body)

        # Nouveaux champs
        cat = data.get('cat')
        quantite = data.get('quantite')
        prix_unitaire = data.get('prix_unitaire')

        prevision = PrevisionBudget.objects.create(
            annee=annee,
            mois=mois,
            date=date(annee, mois, 1),
            type_prevision=type_prevision,
            cat=cat,
            libelle=libelle,
            detail=data.get('detail', libelle),
            quantite=Decimal(str(quantite)) if quantite is not None else None,
            prix_unitaire=Decimal(str(prix_unitaire)) if prix_unitaire is not None else None,
            in_amount=in_amount,
            out_amount=out_amount,
            est_calculee_auto=False,
            source_calcul='Manuel'
        )
```

### Modèle de données

**Champs clés pour prévisions manuelles** :

| Champ | Valeur |
|-------|--------|
| `type_prevision` | `'recette_autre'` ou `'depense_autre'` |
| `est_calculee_auto` | `False` |
| `source_calcul` | `'Manuel'` |
| `cat` | Code compte (ex: '626222') |
| `libelle` | Saisi par l'utilisateur |
| `quantite` | Nombre d'unités (Decimal, optionnel) |
| `prix_unitaire` | Prix par unité (Decimal, optionnel) |
| `in_amount` | > 0 si recette, sinon 0 |
| `out_amount` | > 0 si dépense, sinon 0 |

## Workflow utilisateur

### 1. Ouvrir le modal de configuration

1. Accéder à Facturation → Prévisions Budgétaires
2. Cliquer sur le bouton "Configuration"
3. Cliquer sur l'onglet "Prévisions Manuelles"

### 2. Ajouter une prévision manuelle

1. Sélectionner le type (Recette Autre ou Dépense Autre)
2. Choisir le mois
3. **Optionnel** : Sélectionner un compte dans la liste (122 comptes disponibles)
4. Saisir le libellé (ex: "Subvention exceptionnelle")
5. Saisir la quantité (ex: 1)
6. Saisir le prix unitaire (ex: 5000000)
7. Vérifier le montant calculé automatiquement
8. Cliquer "Ajouter"
9. La prévision apparaît instantanément dans le tableau

### 3. Consulter les prévisions manuelles

- Le tableau affiche toutes les prévisions manuelles de l'année
- Badge coloré indique le type (vert = recette, rouge = dépense)
- Montants formatés avec séparateurs de milliers
- Colonnes In/Out en gras si montant > 0

### 4. Supprimer une prévision manuelle

1. Cliquer sur le bouton rouge "Supprimer" de la ligne
2. Confirmer la suppression
3. La prévision disparaît du tableau et de la base de données

### 5. Visualiser dans la page principale

Les prévisions manuelles apparaissent dans :
- Le tableau principal des prévisions (filtre Type = "Recette Autre" ou "Dépense Autre")
- Les totaux et soldes
- Les exports Excel

## Liste des comptes disponibles

Le système récupère dynamiquement 122 comptes depuis la table `Compte` (apps.organization.models).

**Critère** : Codes commençant par 5 chiffres (ex: 218001, 601002, 626222, 748411)

**Exemples** :
- 218001 - Mobilier
- 601001 - Matériaux pour construction et réhabilitation locaux
- 613100 - Location bureau
- 626222 - Téléphone
- 631104 - IRI (Impôt sur revenus)
- 748411 - Vente eau (paiement forfaitaire)

## APIs REST

### 1. Créer une prévision manuelle

**Endpoint** : `POST /facturation/previsions/api/list/`

**Headers** :
```
Content-Type: application/json
X-CSRFToken: {token}
```

**Body** :
```json
{
    "annee": 2025,
    "mois": 3,
    "type_prevision": "recette_autre",
    "cat": "748411",
    "libelle": "Subvention exceptionnelle",
    "detail": "Subvention du ministère",
    "quantite": 1,
    "prix_unitaire": 5000000,
    "in_amount": 5000000,
    "out_amount": 0
}
```

**Réponse** :
```json
{
    "success": true,
    "message": "Prévision créée avec succès",
    "prevision_id": "uuid"
}
```

### 2. Lister les prévisions manuelles

**Endpoint** : `GET /facturation/previsions/api/list/?annee=2025&type=recette_autre,depense_autre&est_calculee_auto=false`

**Paramètres** :
- `annee` : Année de prévision
- `type` : Types séparés par virgule (`recette_autre,depense_autre`)
- `est_calculee_auto` : `false` pour les prévisions manuelles

**Réponse** :
```json
{
    "success": true,
    "previsions": [
        {
            "id": "uuid",
            "date": "2025-03-01",
            "mois": 3,
            "type_prevision": "recette_autre",
            "cat": "748411",
            "libelle": "Subvention exceptionnelle",
            "quantite": 1.0,
            "prix_unitaire": 5000000.0,
            "in_amount": 5000000.0,
            "out_amount": 0.0,
            "est_calculee_auto": false
        }
    ],
    "count": 1
}
```

### 3. Supprimer une prévision manuelle

**Endpoint** : `POST /facturation/previsions/api/{prevision_id}/delete/`

**Headers** :
```
X-CSRFToken: {token}
```

**Réponse** :
```json
{
    "success": true,
    "message": "Prévision supprimée avec succès"
}
```

## JavaScript

### Fonctions principales

**Fichier** : `backend/templates/billing/previsions_budget.html` (lignes 861-1024)

1. **`switchConfigTab(tabName)`** (lignes 862-883)
   - Gère le changement d'onglets dans le modal
   - Charge automatiquement les prévisions manuelles lors de l'ouverture de l'onglet

2. **`loadPrevisionsManuelles()`** (lignes 886-898)
   - Charge les prévisions manuelles via API
   - Filtre : `type=recette_autre,depense_autre` + `est_calculee_auto=false`

3. **`displayPrevisionsManuelles(previsions)`** (lignes 901-938)
   - Affiche les prévisions dans le tableau
   - Gère l'affichage des badges colorés
   - Formate les montants et quantités
   - Met en gras les montants In/Out si > 0

4. **`calculerMontant()`** (lignes 968-985)
   - Calcule automatiquement le montant lors de la saisie
   - Écoute les événements `input` sur Quantité et Prix unitaire
   - Formate le résultat avec séparateurs de milliers

5. **`ajouterPrevisionManuelle()`** (lignes 987-1048)
   - Valide les champs du formulaire
   - Envoie la requête POST à l'API avec tous les champs
   - Réinitialise le formulaire après succès
   - Recharge la liste

6. **`supprimerPrevisionManuelle(previsionId)`** (lignes 1051-1076)
   - Demande confirmation
   - Construit l'URL dynamiquement avec l'ID
   - Envoie la requête DELETE à l'API
   - Recharge la liste après succès

## Tests de validation

### Test 1 : Création manuelle

```bash
cd backend
python manage.py shell
```

```python
from apps.billing.models_previsions import PrevisionBudget
from datetime import date
from decimal import Decimal

# Créer une prévision manuelle
prev = PrevisionBudget.objects.create(
    annee=2025,
    mois=6,
    date=date(2025, 6, 1),
    type_prevision='recette_autre',
    cat='748411',
    libelle='Don particulier',
    detail='Don de M. X',
    quantite=Decimal('1'),
    prix_unitaire=Decimal('250000'),
    in_amount=Decimal('250000'),
    out_amount=Decimal('0'),
    est_calculee_auto=False,
    source_calcul='Manuel'
)

print(f"Créée : {prev.libelle} - {prev.in_amount} Ar (compte {prev.cat})")
```

### Test 2 : Interface utilisateur

1. Accéder à `http://localhost:8000/facturation/previsions/`
2. Cliquer "Configuration"
3. Cliquer onglet "Prévisions Manuelles"
4. Vérifier l'affichage de la prévision créée au test 1
5. Sélectionner Type "Dépense Autre"
6. Sélectionner Mois "Mars"
7. Sélectionner Compte "631104 - IRI"
8. Saisir Libellé "Amende"
9. Saisir Quantité "1"
10. Saisir Prix unitaire "50000"
11. Vérifier que Montant calculé affiche "50,000 Ar"
12. Cliquer "Ajouter"
13. Vérifier qu'elle apparaît dans le tableau avec le compte
14. Supprimer la prévision "Don particulier"
15. Vérifier qu'elle disparaît

### Test 3 : Intégration dans le tableau principal

1. Fermer le modal
2. Filtrer par Type = "Recette Autre"
3. Vérifier que la prévision apparaît dans le tableau principal
4. Vérifier que le compte s'affiche dans la colonne "Compte"
5. Vérifier que le total inclut le montant

## Points d'attention CRITICAL

### 1. Ne pas mélanger avec les prévisions auto

Les prévisions manuelles ont `est_calculee_auto=False` et ne sont **JAMAIS** supprimées lors du recalcul automatique.

**Code de protection** dans `services_previsions.py` :
```python
# Supprimer uniquement les prévisions auto-calculées
PrevisionBudget.objects.filter(
    annee=annee,
    est_calculee_auto=True  # Ne supprime PAS les manuelles
).delete()
```

### 2. Validation des montants

- Une recette doit avoir `in_amount > 0` et `out_amount = 0`
- Une dépense doit avoir `out_amount > 0` et `in_amount = 0`

Cette logique est gérée côté frontend lors de la soumission.

### 3. Types autorisés

Seuls `recette_autre` et `depense_autre` doivent être utilisés pour les prévisions manuelles. Les autres types sont réservés aux calculs automatiques.

### 4. Comptes disponibles

Le système utilise les comptes de la table `Compte` (apps.organization.models) avec codes commençant par 5 chiffres.

**Vérifier les comptes disponibles** :
```python
from apps.organization.models import Compte
import re

comptes = Compte.objects.all()
comptes_5_chiffres = [c for c in comptes if re.match(r'^\d{5}', c.compte)]
print(f"Total : {len(comptes_5_chiffres)}")
```

## Statistiques

**Test sur base de données (14 décembre 2025)** :

```python
# Total prévisions manuelles
manuelles = PrevisionBudget.objects.filter(
    est_calculee_auto=False,
    annee=2025
)
print(f"Total : {manuelles.count()}")

# Par type
recettes = manuelles.filter(type_prevision='recette_autre')
depenses = manuelles.filter(type_prevision='depense_autre')
print(f"Recettes : {recettes.count()}")
print(f"Dépenses : {depenses.count()}")

# Montants
from django.db.models import Sum
totaux = manuelles.aggregate(Sum('in_amount'), Sum('out_amount'))
print(f"Total recettes : {totaux['in_amount__sum']} Ar")
print(f"Total dépenses : {totaux['out_amount__sum']} Ar")
```

## Améliorations futures possibles

1. **Modification en ligne**
   - Permettre l'édition du libellé et du montant sans supprimer/recréer
   - Modal d'édition avec préremplissage

2. **Import Excel**
   - Template Excel pour importer plusieurs prévisions manuelles d'un coup
   - Validation et feedback détaillé

3. **Copie vers autre année**
   - Bouton pour dupliquer les prévisions manuelles d'une année vers une autre
   - Utile pour les recettes/dépenses récurrentes non calculées automatiquement

4. **Catégorisation**
   - Ajouter un champ `categorie` optionnel pour regrouper les prévisions manuelles
   - Filtres par catégorie dans l'interface

5. **Historique**
   - Table de log pour tracer qui a créé/modifié/supprimé chaque prévision manuelle
   - Affichage de l'historique dans le modal de détails

6. **Notifications**
   - Alertes quand une prévision manuelle importante approche de sa date
   - Rappels pour les recettes attendues

## Changelog

### 14 décembre 2025 - Création initiale

- ✅ Ajout système de tabs dans modal de configuration
- ✅ Formulaire d'ajout de prévisions manuelles avec 7 champs
- ✅ Dropdown dynamique des comptes (122 comptes depuis BDD)
- ✅ Calcul automatique du montant (Quantité × Prix unitaire)
- ✅ Tableau d'affichage avec 10 colonnes
- ✅ Badges colorés et montants en gras
- ✅ Support POST dans `api_previsions_list` pour création
- ✅ Récupération des comptes à 5 chiffres depuis table Compte
- ✅ JavaScript complet pour gestion des tabs et actions
- ✅ Documentation complète

**Résultat** : Les utilisateurs peuvent maintenant saisir des recettes et dépenses "autres" directement dans l'interface, avec choix du compte parmi 122 options.
