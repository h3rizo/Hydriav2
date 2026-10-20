# 📄 RAPPEL DES IMPAYÉS - DOCUMENTATION

**Date de modification :** 13 décembre 2025

## Vue d'ensemble

Les tickets et factures de facturation volumétrique affichent maintenant les impayés antérieurs **à titre de rappel uniquement**, séparés du montant à payer.

## Modifications appliquées

### 1. Filtrage des impayés (Backend)

**Fichier :** `backend/apps/billing/views_facturation.py` (lignes 111-127)

**Règles de filtrage :**
- ✅ Montant calculé (`montant__isnull=False`)
- ✅ Non payé (`numeroDiameX__isnull=True`)
- ✅ Antérieur au relevé actuel (`datereleve__lt=releve.datereleve`)
- ✅ **Année 2025+ uniquement** (`datereleve__year__gte=2025`)

**Raison :** Les factures avant 2025 appartiennent à un ancien système comptable non vérifiable.

```python
factures_impayees = Releve.objects.filter(
    point_eau=releve.point_eau,
    montant__isnull=False,
    numeroDiameX__isnull=True,
    datereleve__lt=releve.datereleve,
    datereleve__year__gte=2025  # FILTRE ANNÉE
).order_by('datereleve')
```

### 2. Affichage séparé - Workflow Volumétrique

**Fichier :** `backend/static/js/print_all_tickets.js`

#### A. Ticket 80mm (lignes 139-166)

**AVANT :**
```
VOLA ALOHA: 5,100 Ar
+ TROSA TALOHA: 5,500 Ar
TOTAL: 10,600 Ar
```

**APRÈS :**
```
╔═══════════════════════════╗
║ VOLA ALOHA: 5,100 Ar      ║
╚═══════════════════════════╝

╔═══════════════════════════╗ (bordure rouge pointillée)
║ 📢 FAMPAHAFANTARANA       ║
║ Manana trosa tsy voaloa   ║
║ TROSA TALOHA: 5,500 Ar    ║
║ Tsy tafiditra amin'ny     ║
║ faktiora ankehitriny      ║
╚═══════════════════════════╝
```

#### B. Récapitulatif A4 (lignes 306-458)

**Colonnes du tableau :**
- ✅ "Montant (Ar)" : Montant de la facture du mois
- ✅ "Rappel Impayés (Ar)" : Impayés à titre informatif
- ❌ ~~"Total (Ar)"~~ : Colonne supprimée

**Footer :**
- Total Général : Somme des montants du mois uniquement
- Total Rappel Impayés : Affiché séparément

**Note explicative :**
```
⚠️ NOTE IMPORTANTE :
La colonne "Rappel Impayés" affiche les dettes antérieures
(depuis 2025) à titre informatif uniquement. Ces montants
ne sont PAS inclus dans le Total Général à encaisser aujourd'hui.
```

### 3. Affichage séparé - Workflow Terrain

**Fichier :** `backend/templates/billing/releves_workflow.html`

#### A. Interface web (lignes 2210-2243)

**AVANT :**
```javascript
Facture du mois: 5,100 Ar
+ Impayés: 5,500 Ar
TOTAL À PAYER: 10,600 Ar
```

**APRÈS :**
```javascript
╔═════════════════════════╗
║ TOTAL À PAYER: 5,100 Ar ║
╚═════════════════════════╝

┌─────────────────────────┐ (alerte rouge)
│ 📢 RAPPEL - Factures    │
│ impayées antérieures    │
│                         │
│ Ces montants ne sont    │
│ PAS inclus ci-dessus    │
│                         │
│ Septembre 2025: 2,500 Ar│
│ Novembre 2025: 3,000 Ar │
│ ─────────────────────── │
│ Total rappel: 5,500 Ar  │
└─────────────────────────┘
```

#### B. Ticket imprimé - Tableau des impayés (lignes 2497-2532)

**Modifications :**
- Bordure changée de solide → **pointillée rouge**
- Titre : "📢 FAMPAHAFANTARANA / RAPPEL"
- Sous-titre : "Manana trosa tsy voaloa ianao"
- Footer : "Tsy tafiditra amin'ny faktiora ankehitriny"

#### C. Ticket imprimé - Section total (lignes 2530-2553)

**AVANT :**
```
VOLA IRAY VOLANA: 5,100 Ar
+ TROSA TALOHA: 5,500 Ar
TOTALIN'NY VOLA: 10,600 Ar
```

**APRÈS :**
```
╔════════════════════════════╗
║ VOLA IRAY VOLANA: 5,100 Ar ║
╚════════════════════════════╝

┌────────────────────────────┐ (bordure pointillée rouge)
│ 📢 FAMPAHAFANTARANA        │
│ Manana trosa tsy voaloa    │
│ TROSA TALOHA: 5,500 Ar     │
│ Tsy tafiditra amin'ny      │
│ faktiora ankehitriny       │
└────────────────────────────┘
```

## Codes couleurs et styles

**Design visuel uniforme :**
- 🔴 **Bordure :** `2px dashed #dc2626` (rouge pointillé)
- 🌸 **Fond :** `#fff5f5` (rose très clair)
- 📢 **Icône :** Emoji cloche pour attirer l'attention
- 🔤 **Texte bilingue :** Malagasy / Français

## Objectif

✅ **Informer** le client de ses dettes antérieures
✅ **Séparer** clairement du montant à payer aujourd'hui
✅ **Éviter** toute confusion sur le montant à encaisser
✅ **Faciliter** le suivi des arriérés sans compliquer la transaction

## Exemples de cas d'usage

### Cas 1 : Client sans impayés
```
TOTAL À PAYER: 5,100 Ar
(pas de section rappel)
```

### Cas 2 : Client avec impayés 2025
```
TOTAL À PAYER: 5,100 Ar

┌─ RAPPEL ─────────────────┐
│ Impayés: 8,500 Ar        │
│ (non inclus ci-dessus)   │
└──────────────────────────┘
```

### Cas 3 : Client avec impayés pré-2025
```
TOTAL À PAYER: 5,100 Ar
(pas de section rappel - ignorés)
```

## Tests de validation

**Page volumétrique :** http://localhost:8000/facturation/facturation/
**Page terrain :** http://localhost:8000/facturation/releves/

**Scénarios testés :**
1. ✅ Kiosque CSB Ambanja - Relevé novembre 2024 : 0 impayés (pré-2025 exclus)
2. ✅ Kiosque CSB Ambanja - Relevé novembre 2025 : 2 impayés (5,500 Ar total)
3. ✅ Séparation visuelle claire entre total et rappel
4. ✅ Messages bilingues présents
5. ✅ Pas d'addition des impayés au total

## Maintenance future

**Pour modifier la limite d'année :**
```python
# Dans views_facturation.py ligne 120
datereleve__year__gte=2026  # Changer l'année si nécessaire
```

**Pour modifier le style visuel :**
```javascript
// Dans print_all_tickets.js et releves_workflow.html
border: 2px dashed #dc2626;  // Bordure
background-color: #fff5f5;   // Fond
```

## Fichiers modifiés

1. `backend/apps/billing/views_facturation.py` (lignes 116, 120)
2. `backend/static/js/print_all_tickets.js` (lignes 139-166, 306-458)
3. `backend/templates/billing/releves_workflow.html` (lignes 2210-2243, 2497-2553)

---

**✅ Modifications validées le 13 décembre 2025**
**📋 Documentation complète disponible**
