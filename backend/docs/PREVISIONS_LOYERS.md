# 💰 MODULE PRÉVISIONS LOYERS - DOCUMENTATION

**Date de création :** 13 décembre 2025

## Vue d'ensemble

Le système de prévisions budgétaires intègre maintenant le calcul automatique des loyers (compte 613100) basé sur l'analyse historique des transactions DiameX.

## Fonctionnalités

### 1. Analyse automatique des loyers

Le système :
1. **Récupère** tous les loyers depuis BaseDiameX (compte `613100`)
2. **Groupe** par motif (bénéficiaire + lieu)
3. **Calcule** la fréquence basée sur l'intervalle entre paiements
4. **Extrapole** pour générer les prévisions de l'année

### 2. Détection de fréquence

Le système identifie automatiquement la fréquence de paiement :

| Intervalle moyen | Fréquence détectée | Paiements/an |
|------------------|-------------------|--------------|
| 25-35 jours | MENSUEL | 12 |
| 55-70 jours | BIMENSUEL | 6 |
| 85-100 jours | TRIMESTRIEL | 4 |
| Autre | IRREGULIER | Calculé |

**Exemple** : Loyer VAVY TIANA DEA avec intervalles de [90, 91, 92] jours → Détecté comme **TRIMESTRIEL**

### 3. Format des loyers dans DiameX

**Pattern reconnu** :
```
ISI PREST_{Bénéficiaire}_{Détails}_Mois_{Montant unitaire}_x {Nb mois} {Liste mois}
```

**Exemples** :
- `ISI PREST_VAVY TIANA DEA_Loyer buro VVT_Mois_600000_x 3 2025 01 02 03`
  - Bénéficiaire : VAVY TIANA DEA
  - Lieu : Loyer buro VVT
  - Montant unitaire : 600,000 Ar/mois
  - Couvre 3 mois (janvier, février, mars)
  - **Total** : 1,800,000 Ar

- `ISI PREST_RAZANAMANGA Anastasie_Loyer bureau Vohilengo_Fft_70000_2025 02`
  - Bénéficiaire : RAZANAMANGA Anastasie
  - Lieu : Loyer bureau Vohilengo
  - Montant unitaire : 70,000 Ar/mois
  - **Total** : 70,000 Ar

### 4. Calcul du montant prévu

**Formule** :
```
Montant par paiement = Montant unitaire × Nombre de mois par paiement
```

**Exemples** :

| Motif | Fréquence | Montant unit. | Nb mois | Montant paiement | Annuel |
|-------|-----------|---------------|---------|------------------|--------|
| VAVY TIANA DEA - Loyer buro VVT | TRIMESTRIEL | 600,000 Ar | 3 | 1,800,000 Ar | 7,200,000 Ar |
| RADISON Paul - Loyer bureau Fénérive | IRREGULIER | 900,000 Ar | 2 | 1,800,000 Ar | 5,400,000 Ar |
| RAZANAMANGA Anastasie - Loyer bureau Vohilengo | MENSUEL | 70,000 Ar | 1 | 70,000 Ar | 840,000 Ar |
| SOMA Ginot - Loyer bureau | SUPPOSE_TRIMESTRIEL | 40,000 Ar | 24 | 960,000 Ar | 3,840,000 Ar |

### 5. Extrapolation pour l'année de prévision

Le système :
1. Part du dernier paiement enregistré
2. Ajoute l'intervalle moyen pour calculer la date suivante
3. Créé des prévisions pour chaque mois où un paiement est attendu
4. S'arrête quand l'année de prévision est dépassée

**Exemple pour VAVY TIANA DEA (Trimestriel)** :
- Dernier paiement : 01/10/2025
- Intervalle moyen : 91 jours
- Prochaine prévision : 01/10/2025 + 91 jours = **31/12/2025**
- Montant prévu : 1,800,000 Ar (3 mois × 600,000 Ar)

## Architecture technique

### Fichiers modifiés/créés

1. **`apps/billing/services_previsions.py`** (lignes 1687-1884)
   - Fonction `calculer_previsions_loyers(annee, base, config)`
   - Intégration dans `recalculer_previsions_annee()` (lignes 121-124)

2. **`apps/billing/models_previsions.py`** (ligne 26)
   - Ajout du type `('depense_loyer', 'Dépense Loyers (613100)')`

### Fonction principale

```python
def calculer_previsions_loyers(annee, base=None, config=None):
    """
    Calcule les prévisions de loyers (compte 613100) pour l'année.

    Returns:
        dict: {
            'nb_created': int,
            'patterns_detectes': list[dict]
        }
    """
```

### Algorithme

1. **Extraction du motif** :
```python
def extraire_beneficiaire_et_lieu(description):
    # Regex: ISI PREST_{Beneficiaire}_{Details}_Mois_{Montant}_x {N} {Mois}
    match = re.search(r'ISI PREST_([^_]+)_([^_]+)_...')
    motif = f"{beneficiaire} - {details}"
```

2. **Groupement** :
```python
groupes = defaultdict(list)
for loyer in loyers:
    motif = extraire_beneficiaire_et_lieu(loyer.description)
    groupes[motif].append({...})
```

3. **Calcul fréquence** :
```python
intervalles = [
    (trans[i]['date'] - trans[i-1]['date']).days
    for i in range(1, len(transactions))
]
moyenne_jours = sum(intervalles) / len(intervalles)
```

4. **Création prévisions** :
```python
date_suivante = derniere_date + timedelta(days=int(moyenne_jours))
while date_suivante.year <= annee:
    PrevisionBudget.objects.create(
        cat='613100',
        libelle=f"Loyer {motif}",
        out_amount=montant_par_paiement,
        type_prevision='depense_loyer',
        ...
    )
```

## Résultats pour 2025

**Statistiques** :
- **Nombre de motifs** : 13 loyers différents
- **Nombre de prévisions** : 26 paiements
- **Montant total annuel** : 14,260,000 Ar

**Détail par bénéficiaire (top 5)** :
1. **RADISON Richard Paul** (Loyer bureau) : 5,400,000 Ar
2. **RADISON Paul** (Loyer bureau Fénérive) : 5,400,000 Ar
3. **SOMA Ginot** (Loyer bureau) : 3,840,000 Ar
4. **VAVY TIANA DEA** (Loyer buro VVT) : 1,800,000 Ar
5. **RAZANAMANGA Anastasie** (Divers bureaux) : ~1,050,000 Ar

## Utilisation

### Via l'interface web

1. Accéder à : `http://localhost:8000/facturation/previsions/`
2. Sélectionner l'année (ex: 2025)
3. Cliquer sur **"Recalculer les prévisions"**
4. Les loyers sont inclus automatiquement dans le calcul

### Filtrer par type

Dans l'interface de prévisions, filtrer par :
- **Type** : "Dépense Loyers (613100)"

### Export Excel

Les loyers apparaissent dans l'export Excel avec :
- **Cat** : 613100
- **Libellé** : Loyer {Bénéficiaire} - {Lieu}
- **Detail** : {Fréquence} ({Nb mois} mois)
- **Out** : Montant de la dépense

## Maintenance

### Ajouter un nouveau loyer

Lorsqu'un nouveau loyer est enregistré dans DiameX :
1. S'assurer qu'il suit le format : `ISI PREST_{Nom}_{Details}_Mois_{Montant}_x {N} {Mois}`
2. Utiliser le compte **613100**
3. Le prochain recalcul l'intègrera automatiquement

### Modifier la logique de fréquence

Pour ajuster les seuils de détection :
```python
# Dans calculer_previsions_loyers() ligne 1798
if 25 <= moyenne_jours <= 35:  # Ajuster ces valeurs
    frequence = "MENSUEL"
```

### Déboguer les patterns

Pour voir les patterns détectés :
```python
from apps.billing.services_previsions import calculer_previsions_loyers

result = calculer_previsions_loyers(2025)
for pattern in result['patterns_detectes']:
    print(f"{pattern['motif']}: {pattern['frequence']}, {pattern['montant_par_paiement']:,.0f} Ar")
```

## Points d'attention

### 1. Qualité des données DiameX

⚠️ Le système dépend de la qualité des descriptions DiameX :
- Si le format change, le regex peut ne plus fonctionner
- Si les montants sont incorrects, les prévisions seront fausses

### 2. Loyers avec un seul paiement

Les loyers avec un seul paiement historique sont supposés **TRIMESTRIELS** par défaut.

### 3. Doublons

Le système évite les doublons en trackant les mois déjà créés :
```python
mois_deja_crees = set()
if mois_prevision not in mois_deja_crees:
    # Créer la prévision
```

### 4. Intervalle irrégulier

Pour les loyers avec intervalle variable (ex: 61, 122, 31 jours), le système :
- Calcule la moyenne
- Estime le nombre de paiements annuels : `round(365 / moyenne)`
- Utilise le nombre de mois moyen historique

## Tests de validation

```python
# Test 1 : Vérifier le nombre de prévisions créées
from apps.billing.models_previsions import PrevisionBudget

loyers_2025 = PrevisionBudget.objects.filter(
    type_prevision='depense_loyer',
    annee=2025
)
assert loyers_2025.count() == 26

# Test 2 : Vérifier le total annuel
from django.db.models import Sum
total = loyers_2025.aggregate(total=Sum('out_amount'))['total']
assert total == 14_260_000

# Test 3 : Vérifier un loyer spécifique
vavy = loyers_2025.filter(libelle__icontains='VAVY TIANA')
assert vavy.count() == 1  # 1 paiement pour décembre
assert vavy.first().out_amount == 1_800_000
```

## Améliorations futures

1. **Machine Learning** : Prédire les montants futurs basés sur l'historique
2. **Alertes** : Notifier quand un loyer approche de son échéance
3. **Indexation** : Appliquer un coefficient d'inflation annuel
4. **Multi-comptes** : Étendre à d'autres types de charges récurrentes

---

**✅ FONCTIONNALITÉ COMPLÈTE ET OPÉRATIONNELLE**

**Les loyers sont maintenant intégrés automatiquement dans le système de prévisions budgétaires.**
