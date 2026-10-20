# Workflow Cartes Sociales - Déduction Facture Kiosquier

## 📋 Vue d'ensemble

Les consommations de cartes sociales doivent être déduites de la facture mensuelle du kiosquier (gérant du point d'eau). Ce document explique la logique de relation entre les consommations et les relevés.

## 🔗 Relation entre Consommations et Relevés

### Tables concernées

1. **`conso_cartes_sociales`** (ConsoCarteSociale)
   - `id` : UUID de la consommation
   - `carte_sociale_id` : FK vers CarteSociale
   - `date` : Date de la consommation (**décalée d'un mois en arrière**)
   - `montant_paye` : Montant à déduire
   - `point_eau_id` : FK vers PointEau (via CarteSociale)

2. **`releves`** (Releve)
   - `id` : UUID du relevé
   - `point_eau_id` : FK vers PointEau
   - `datereleve` : Date du relevé
   - `montant` : Montant de la facture

### Logique de relation

**Principe :** Une consommation carte sociale est liée à un relevé par :
- **Point d'eau** : `conso.carte_sociale.point_eau_id = releve.point_eau_id`
- **Mois** : Début du mois de `conso.date` = Début du mois de `releve.datereleve`

### Exemple concret

**Consommation carte sociale :**
- Date consommation : **2025-10-15** (décalée d'un mois en arrière)
- Point d'eau : `ca0fcf4f-c88a-4b6c-ae97-ab88ab61ddb9`
- Montant : 3,000 Ar

**Relevé correspondant :**
- Date relevé : **2025-10-20** (ou n'importe quelle date en octobre 2025)
- Point d'eau : `ca0fcf4f-c88a-4b6c-ae97-ab88ab61ddb9`
- Montant facture : 50,000 Ar

**Déduction :**
- Montant à facturer au kiosquier = 50,000 - 3,000 = **47,000 Ar**

## 🗓️ Pourquoi décaler d'un mois en arrière ?

**Date de l'impression du ticket** : Correspond au mois **suivant** la consommation réelle.

**Exemple :**
- Consommation réelle : Septembre 2025
- Ticket imprimé : **15 octobre 2025** (date_facture)
- Date enregistrée dans conso : **15 septembre 2025** (décalée d'un mois en arrière)
- Relevé associé : Septembre 2025 (pour déduire de la facture de septembre)

**Workflow chronologique :**

1. **Mi-septembre** : Le bénéficiaire consomme de l'eau avec sa carte sociale
2. **Fin septembre** : Le kiosquier fait son relevé mensuel → Facture septembre générée
3. **Début octobre** : Le bénéficiaire vient récupérer son ticket d'aide sociale
4. **Système enregistre** : date = septembre (pour déduire de la facture de septembre)
5. **Facturation kiosquier** : Montant carte sociale déduit de la facture de septembre

## 💻 Requête SQL pour la déduction

```sql
-- Récupérer les consommations à déduire pour un relevé
SELECT
    ccs.id,
    ccs.montant_paye,
    ccs.date AS date_consommation,
    cs.nom_beneficiaire
FROM conso_cartes_sociales ccs
INNER JOIN cartes_sociales cs ON ccs.carte_sociale_id = cs.id
INNER JOIN releves r ON r.point_eau_id = cs.point_eau_id
WHERE
    r.id = :releve_id
    AND DATE_TRUNC('month', ccs.date) = DATE_TRUNC('month', r.datereleve)
    AND ccs.montant_paye IS NOT NULL;
```

## 🐍 Code Python Django

```python
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from apps.billing.models import Releve, ConsoCarteSociale

def calculer_deduction_cartes_sociales(releve_id):
    """
    Calcule le montant total des cartes sociales à déduire
    de la facture d'un relevé
    """
    releve = Releve.objects.get(id=releve_id)

    # Récupérer le point d'eau et le mois du relevé
    point_eau = releve.point_eau
    mois_releve = releve.datereleve.replace(day=1)  # Début du mois

    # Filtrer les consommations du même mois et point d'eau
    consos = ConsoCarteSociale.objects.filter(
        carte_sociale__point_eau=point_eau,
        date__year=mois_releve.year,
        date__month=mois_releve.month,
        montant_paye__isnull=False
    )

    # Calculer le total à déduire
    total_deduction = consos.aggregate(
        total=Sum('montant_paye')
    )['total'] or 0

    return {
        'releve_id': releve.id,
        'point_eau': point_eau.nomabonne,
        'mois': mois_releve.strftime('%B %Y'),
        'montant_facture': releve.montant,
        'montant_cartes_sociales': total_deduction,
        'montant_net': releve.montant - total_deduction,
        'nb_consommations': consos.count(),
        'detail_consos': list(consos.values(
            'id',
            'carte_sociale__nom_beneficiaire',
            'date',
            'montant_paye'
        ))
    }
```

## 📊 Exemple d'affichage dans la facture

```
┌─────────────────────────────────────────┐
│  FACTURE KIOSQUIER - OCTOBRE 2025       │
├─────────────────────────────────────────┤
│ Point d'eau : MODEL                     │
│ Kiosquier : Jean RAKOTO                 │
├─────────────────────────────────────────┤
│ Consommation volumétrique : 45,000 Ar   │
│ Abonnement mensuel :         5,000 Ar   │
│                                          │
│ SOUS-TOTAL :                50,000 Ar   │
├─────────────────────────────────────────┤
│ DÉDUCTIONS CARTES SOCIALES :            │
│   - VOLATODY Christine :     3,000 Ar   │
│   - RAKOTO Marie :           3,000 Ar   │
│   - BAMO Florine :           3,000 Ar   │
│                                          │
│ TOTAL DÉDUCTIONS :          -9,000 Ar   │
├─────────────────────────────────────────┤
│ MONTANT NET À PAYER :       41,000 Ar   │
└─────────────────────────────────────────┘
```

## ⚠️ Points d'attention

1. **Décalage d'un mois** : Les dates des consommations sont décalées d'un mois en arrière au moment de l'enregistrement
2. **Point d'eau** : La relation se fait via le point d'eau de la carte sociale
3. **Montant NULL** : Les consommations sans montant ne sont pas déduites
4. **Début de mois** : La comparaison se fait sur le début du mois (ignorer le jour exact)

## 🔄 Cas d'usage

### Scénario 1 : Ticket imprimé le 15 octobre

```python
# Date ticket : 2025-10-15
# Enregistrement :
ConsoCarteSociale.objects.create(
    carte_sociale=carte,
    date=datetime(2025, 9, 15),  # Décalé d'un mois en arrière !
    montant_paye=3000
)

# Sera déduit du relevé de septembre 2025
```

### Scénario 2 : Relevé de septembre avec déductions

```python
# Relevé du 30 septembre 2025
releve = Releve.objects.get(
    point_eau=point_eau,
    datereleve='2025-09-30'
)

# Récupère les consos de septembre 2025
deduction = calculer_deduction_cartes_sociales(releve.id)

# Résultat :
# {
#     'montant_facture': 50000,
#     'montant_cartes_sociales': 9000,
#     'montant_net': 41000,
#     'nb_consommations': 3
# }
```

## 📝 Modification historique

**Date :** 9 novembre 2025
**Action :** Décalage de toutes les dates existantes d'un mois en arrière
**Commande :**
```bash
python manage.py shell -c "
from apps.billing.models import ConsoCarteSociale
from dateutil.relativedelta import relativedelta
consos = ConsoCarteSociale.objects.filter(date__isnull=False)
for c in consos:
    c.date = c.date - relativedelta(months=1)
    c.save()
print('6976 dates décalées')
"
```

## 🎯 Prochaines étapes suggérées

1. Créer une vue/API pour afficher les déductions par relevé
2. Ajouter un champ `montant_deductions_cs` dans le modèle Releve
3. Calculer automatiquement le montant net lors de la génération de facture
4. Créer un rapport mensuel des déductions par kiosquier
5. Export Excel des déductions pour comptabilité
