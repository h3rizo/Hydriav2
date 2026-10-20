# Documentation - Prévisions Dépenses Récurrentes

## Vue d'ensemble

Le système de prévisions de dépenses récurrentes permet de générer automatiquement des prévisions budgétaires pour l'année en cours en extrapolant les transactions du dernier mois connu pour chaque compte.

**Date de création** : 14 décembre 2025

## Comptes concernés

Le système traite les comptes suivants :

| Code Compte | Libellé | Description |
|-------------|---------|-------------|
| 602 | Achats stockés | Achats de matériaux et fournitures destinés au stock |
| 606 | Achats non stockés | Achats de matériaux et fournitures consommés immédiatement |
| 615 | Entretien et réparations | Frais d'entretien et de réparations |
| 623100 | Publicité | Dépenses de communication et publicité |
| 626222 | Téléphone | Abonnements et crédits téléphoniques |
| 626320 | Internet mobile | Crédits internet mobile |
| 626321 | Internet fixe | Abonnements internet fixe (ex: Starlink) |
| 627203 | Frais bancaires | Frais de tenue de compte |
| 627204 | Frais MVola/transferts | Frais de transactions MVola et transferts |
| 631104 | IRI | Impôt sur les Revenus Industriels |

## Méthode d'extrapolation

### Principe

Pour chaque compte :
1. Identifier le dernier mois connu avec des transactions
2. Récupérer toutes les transactions de ce mois
3. Répéter ces transactions pour **tous les mois de l'année de prévision** (12 mois)

### Exemple

**Compte 626222 - Téléphone**
- Dernier mois connu : **Novembre 2025**
- Nombre de transactions : **28**
- Montant total : **500,000 Ar**

**Prévisions générées** :
- **Janvier 2025** : 28 transactions × montants individuels = 500,000 Ar
- **Février 2025** : 28 transactions × montants individuels = 500,000 Ar
- ...
- **Décembre 2025** : 28 transactions × montants individuels = 500,000 Ar

**Total annuel prévu** : 500,000 Ar × 12 mois = **6,000,000 Ar**

## Résultats pour 2025

### Statistiques globales

- **Total prévisions créées** : 528
- **Montant annuel total** : 26,248,800 Ar

### Détail par compte

| Compte | Libellé | Dernier mois | Transactions | Prévisions | Montant annuel |
|--------|---------|--------------|--------------|------------|----------------|
| 623100 | Publicité | 2025-11 | 4 | 48 | 4,812,000 Ar |
| 626222 | Téléphone | 2025-11 | 28 | 336 | 6,000,000 Ar |
| 626320 | Internet mobile | 2025-11 | 3 | 36 | 2,504,400 Ar |
| 626321 | Internet fixe | 2025-12 | 1 | 12 | 3,264,000 Ar |
| 627203 | Frais bancaires | 2025-11 | 1 | 12 | 12,000 Ar |
| 627204 | Frais MVola | 2025-11 | 4 | 48 | 186,000 Ar |
| 631104 | IRI | 2025-11 | 3 | 36 | 9,470,400 Ar |

**Note** : Les comptes 602, 606 et 615 n'ont pas de transactions historiques pour le moment.

## Architecture technique

### Fichiers modifiés/créés

1. **`apps/billing/services_previsions.py`**
   - Fonction `calculer_previsions_depenses_recurrentes()` (lignes 1894-2022)
   - Intégration dans `recalculer_previsions_annee()` (lignes 126-129)

2. **`apps/billing/models_previsions.py`**
   - Ajout du type `depense_recurrente` dans `TYPE_CHOICES` (ligne 27)

3. **`apps/billing/views_previsions.py`**
   - `depenses_recurrentes_page()` : Page de gestion (lignes 867-895)
   - `api_depenses_recurrentes_list()` : API de listage (lignes 898-954)
   - `api_supprimer_depense_recurrente()` : API suppression individuelle (lignes 957-1004)
   - `api_supprimer_depenses_recurrentes_batch()` : API suppression en batch (lignes 1007-1040)

4. **`apps/billing/urls.py`**
   - Routes API pour la gestion des dépenses récurrentes (lignes 191-195)

5. **`templates/billing/depenses_recurrentes_management.html`**
   - Interface complète de gestion avec filtres et actions

### Modèle de données

**Type de prévision** : `depense_recurrente`

**Champs `PrevisionBudget`** :
- `cat` : Code compte (ex: '626222')
- `libelle` : Libellé du compte (ex: 'Téléphone')
- `detail` : Description de la transaction (tronquée à 100 caractères)
- `date` : Date de la prévision (1er du mois)
- `out_amount` : Montant de la dépense (Decimal)
- `type_prevision` : `'depense_recurrente'`
- `annee` : Année de prévision
- `mois` : Mois de prévision (1-12)
- `est_calculee_auto` : `True`
- `source_calcul` : `"BaseDiameX|{compte}|{dernier_mois}|T{idx}"`

**Contrainte unique** : `(type_prevision, annee, mois, source_calcul)`

### Algorithme

```python
def calculer_previsions_depenses_recurrentes(annee, base=None, config=None):
    comptes = ['602', '606', '615', '623100', '626222', '626320', '626321', '627203', '627204', '631104']

    for compte in comptes:
        # 1. Récupérer toutes les transactions
        transactions = BaseDiameX.objects.filter(compte_code=compte, montant_out__gt=0)

        # 2. Trouver le dernier mois connu
        derniere_date = transactions.aggregate(Max('date_m'))['date_m__max']

        # 3. Récupérer les transactions du dernier mois
        transactions_dernier_mois = transactions.filter(
            date_m__month=derniere_date.month,
            date_m__year=derniere_date.year
        )

        # 4. Pour chaque mois de l'année de prévision
        for mois in range(1, 13):
            # 5. Dupliquer chaque transaction du dernier mois
            for idx, trans in enumerate(transactions_dernier_mois, start=1):
                PrevisionBudget.objects.create(
                    cat=compte,
                    detail=trans.description[:100],
                    date=date(annee, mois, 1),
                    out_amount=trans.montant_out,
                    type_prevision='depense_recurrente',
                    source_calcul=f"BaseDiameX|{compte}|{derniere_date:%Y-%m}|T{idx}"
                )
```

## Interface utilisateur

### Page de gestion

**URL** : `http://localhost:8000/facturation/previsions/depenses-recurrentes/`

**Fonctionnalités** :

1. **Filtres**
   - Mois (1-12)
   - Compte (602, 606, 615, etc.)

2. **Statistiques**
   - Total prévisions affichées
   - Montant total de la sélection
   - Nombre de prévisions sélectionnées

3. **Actions**
   - Sélection individuelle ou globale (checkbox)
   - Suppression individuelle (bouton rouge par ligne)
   - Suppression en batch (bouton "Supprimer la sélection")

4. **Tableau**
   - Date (mois formaté)
   - Compte (badge)
   - Libellé
   - Description (tronquée avec tooltip)
   - Montant (formaté avec séparateurs)
   - Source (source_calcul)
   - Actions (bouton supprimer)

### APIs disponibles

#### 1. Liste des prévisions

**Endpoint** : `GET /facturation/previsions/api/depenses-recurrentes/list/`

**Paramètres** :
- `annee` (int) : Année de prévision
- `mois` (int, optionnel) : Filtre par mois
- `compte` (str, optionnel) : Filtre par compte

**Réponse** :
```json
{
    "success": true,
    "previsions": [
        {
            "id": "uuid",
            "date": "2025-01-01",
            "mois": 1,
            "compte": "626222",
            "libelle": "Téléphone",
            "detail": "NIF_SHOP TELMA_Crédit téléphone...",
            "montant": 15000.0,
            "source_calcul": "BaseDiameX|626222|2025-11|T1"
        }
    ],
    "stats": {
        "total_previsions": 528,
        "montant_total": 26248800.0
    }
}
```

#### 2. Suppression individuelle

**Endpoint** : `POST /facturation/previsions/api/depenses-recurrentes/delete/`

**Body** :
```json
{
    "prevision_id": "uuid"
}
```

**Réponse** :
```json
{
    "success": true,
    "message": "Prévision supprimée : Téléphone (Compte 626222) - Mois 1 - 15,000 Ar"
}
```

#### 3. Suppression en batch

**Endpoint** : `POST /facturation/previsions/api/depenses-recurrentes/delete-batch/`

**Body** :
```json
{
    "prevision_ids": ["uuid1", "uuid2", "uuid3"]
}
```

**Réponse** :
```json
{
    "success": true,
    "message": "3 prévision(s) supprimée(s)",
    "nb_deleted": 3
}
```

## Workflow d'utilisation

### 1. Recalcul automatique

Lorsque l'utilisateur lance un recalcul des prévisions (bouton "Recalculer") :

1. Suppression de toutes les prévisions auto-calculées existantes
2. Calcul des recettes forfaitaires
3. Calcul des recettes volumétriques
4. ... (autres types)
5. **Calcul des loyers (compte 613100)**
6. **Calcul des dépenses récurrentes (comptes 602, 606, 615, 623100, 626222, 626320, 626321, 627203, 627204, 631104)** ← NOUVEAU
7. Affichage des résultats

**Fichier** : `apps/billing/services_previsions.py`, lignes 126-129

### 2. Gestion manuelle

Si l'utilisateur souhaite supprimer certaines prévisions générées automatiquement :

1. Accéder à la page : **Facturation → Prévisions → Dépenses Récurrentes**
2. Utiliser les filtres (mois, compte) pour cibler les prévisions
3. **Option 1** : Cliquer sur le bouton rouge "Supprimer" d'une ligne
4. **Option 2** : Sélectionner plusieurs lignes (checkbox) puis cliquer "Supprimer la sélection"
5. Confirmer la suppression
6. Les prévisions sont supprimées de la base de données

**Note** : Les prévisions supprimées manuellement seront **recréées** lors du prochain recalcul automatique.

## Tests de validation

### Test 1 : Calcul des prévisions

```bash
cd backend
python manage.py shell
```

```python
from apps.billing.services_previsions import calculer_previsions_depenses_recurrentes

result = calculer_previsions_depenses_recurrentes(2025)

print(f"Prévisions créées: {result['nb_created']}")
for compte, details in result['details_par_compte'].items():
    print(f"  {compte}: {details['nb_previsions_creees']} prévisions")
```

**Résultat attendu** : 528 prévisions créées

### Test 2 : Interface de gestion

1. Accéder à `http://localhost:8000/facturation/previsions/depenses-recurrentes/`
2. Vérifier l'affichage du tableau (528 lignes)
3. Filtrer par compte "626222" (Téléphone)
4. Vérifier : 336 prévisions affichées (28 trans × 12 mois)
5. Filtrer par mois "1" (Janvier)
6. Vérifier : Prévisions de tous les comptes pour janvier uniquement
7. Sélectionner 2-3 lignes et supprimer en batch
8. Vérifier le message de confirmation
9. Vérifier que les lignes disparaissent du tableau

### Test 3 : APIs

**Liste** :
```bash
curl "http://localhost:8000/facturation/previsions/api/depenses-recurrentes/list/?annee=2025&compte=626222"
```

**Suppression** :
```bash
curl -X POST "http://localhost:8000/facturation/previsions/api/depenses-recurrentes/delete/" \
  -H "Content-Type: application/json" \
  -d '{"prevision_id":"uuid-ici"}'
```

## Points d'attention CRITICAL

### 1. Source de calcul unique

Pour éviter les doublons lors de la création, le champ `source_calcul` est construit avec un index unique :

```python
source_calcul = f"BaseDiameX|{compte}|{dernier_mois}|T{idx}"
```

**Exemple** : `BaseDiameX|626222|2025-11|T1`

La contrainte unique `(type_prevision, annee, mois, source_calcul)` empêche la création de doublons.

### 2. Recréation au recalcul

Les prévisions supprimées manuellement seront **automatiquement recréées** lors du prochain recalcul.

Si certaines prévisions ne doivent jamais être créées, il faut :
- Soit modifier la fonction `calculer_previsions_depenses_recurrentes()` pour exclure certains comptes
- Soit créer une table de configuration pour désactiver certains comptes

### 3. Performance

Avec 528 prévisions créées pour 2025 (7 comptes × 44 transactions × 12 mois), le temps de calcul est négligeable (<1 seconde).

Si le nombre de comptes augmente ou si certains comptes ont beaucoup de transactions mensuelles, envisager un batch insert avec `bulk_create()`.

### 4. Limite de 100 caractères

Le champ `detail` est tronqué à 100 caractères pour éviter des descriptions trop longues :

```python
description = trans.description[:97] + "..."
```

## Améliorations futures possibles

1. **Configuration par compte**
   - Table pour activer/désactiver le calcul par compte
   - Possibilité de modifier le nombre de mois à extrapoler

2. **Exclusion permanente**
   - Table pour marquer certaines prévisions comme "à ne pas recréer"
   - Filtre dans `calculer_previsions_depenses_recurrentes()` pour les exclure

3. **Ajustement manuel**
   - Permettre la modification du montant d'une prévision sans la supprimer
   - Marquer comme "ajustée manuellement" pour éviter l'écrasement au recalcul

4. **Historique**
   - Table de log pour tracer les suppressions manuelles
   - Possibilité de restaurer des prévisions supprimées

5. **Export Excel**
   - Bouton pour exporter les prévisions affichées vers Excel
   - Colonnes : Date, Compte, Libellé, Description, Montant, Source

## Changelog

### 14 décembre 2025 - Création initiale

- ✅ Fonction `calculer_previsions_depenses_recurrentes()` créée
- ✅ Intégration dans le workflow de recalcul
- ✅ Type `depense_recurrente` ajouté au modèle
- ✅ Page de gestion avec filtres et actions
- ✅ 3 APIs REST (liste, suppression individuelle, suppression batch)
- ✅ Documentation complète

**Comptes traités** : 602, 606, 615, 623100, 626222, 626320, 626321, 627203, 627204, 631104

**Résultat 2025** : 528 prévisions créées pour un montant annuel de 26,248,800 Ar
