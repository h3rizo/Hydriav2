# ANALYSES D'EAU - LOGIQUE PAR PACKS

**Date :** 24 décembre 2025
**Version :** 5.0
**Fichiers impactés :**
- `apps/inspections/views_analyse_eau_packs.py` (NOUVEAU)
- `apps/inspections/urls.py`
- `static/js/analyses_eau_v4.js` (réécriture complète)
- `templates/inspections/analyses_eau_list.html`

## 📋 Vue d'ensemble

### Concept clé : Pack d'analyse

**Définition :** Un **pack** = toutes les analyses effectuées le même jour (groupées par `date_analyse`).

### Objectif métier

Les analyses d'eau sont réalisées en **groupe** (pack) pour valider la qualité du processus d'analyse lui-même. Chaque pack doit contenir :
- **Des témoins** : Échantillons dont on connaît le résultat attendu
- **Des échantillons réels** : Points d'eau et équipements à analyser

## 🎯 Logique de validation des packs

### Types de prélèvement

| Type | Code | Rôle dans le pack |
|------|------|-------------------|
| **Point d'eau traditionnel** | `point_eau_traditionnel` | 🔬 **TEMOIN POSITIF** - Doit contenir des coliformes |
| **Point d'eau** | `point_eau` | 🚰 Échantillon réel - Ne doit PAS contenir de coliformes |
| **Équipement** | `equipement` | ⚙️ Échantillon réel - Ne doit PAS contenir de coliformes |
| **Bouteille** | `bouteille` | 🧪 **TEMOIN NEGATIF** - Ne doit JAMAIS contenir de coliformes |
| **Autre** | `autre` | ❓ Non pris en compte dans validation |

### Règles de statut du pack

#### ✅ **VALIDE**
Le pack est considéré VALIDE si :
- ✅ Au moins un témoin positif (coliformes sur `point_eau_traditionnel`)
- ❌ AUCUNE contamination de bouteille
- ❌ AUCUN coliforme sur équipement ou point d'eau

**Interprétation :** Le processus d'analyse est fiable, les résultats négatifs sur équipements/points d'eau sont crédibles.

#### ⚠️ **PROBLEMATIQUE**
Le pack est considéré PROBLEMATIQUE si :
- ✅ Coliformes trouvés sur `equipement` OU `point_eau`
- ❌ Pas de contamination de bouteille

**Interprétation :** Les équipements/points d'eau testés ont réellement un problème de contamination. Nécessite intervention.

#### ❌ **CONTAMINE**
Le pack est considéré CONTAMINE si :
- ❌ Coliformes trouvés sur `bouteille`

**Interprétation :** Le processus d'analyse lui-même est contaminé. **TOUS les résultats du pack sont invalides** (y compris les positifs sur équipements). Il faut refaire l'analyse complète.

#### ❓ **INDETERMINE**
Le pack est INDETERMINE si :
- ❌ Aucun témoin positif trouvé
- ❌ Pas de contamination bouteille

**Interprétation :** On ne peut pas valider la fiabilité du pack car aucun témoin positif n'a été inclus.

## 📊 Nouvelles statistiques affichées

### Carte 1 : Total Packs
- **Valeur** : Nombre de jours d'analyse différents
- **Description** : X analyses

### Carte 2 : ✅ Validés
- **Valeur** : Nombre de packs avec statut VALIDE
- **Description** : Témoin positif

### Carte 3 : ⚠️ Problématiques
- **Valeur** : Nombre de packs avec statut PROBLEMATIQUE
- **Description** : Coliformes anormaux

### Carte 4 : ❌ Contaminés
- **Valeur** : Nombre de packs avec statut CONTAMINE
- **Description** : Bouteille positive

### Carte 5 : Total Analyses
- **Valeur** : Nombre total d'analyses (tous types)
- **Description** : Tous prélèvements

## 📑 Tableau modifié

### Nouvelles colonnes

1. **Statut Pack** (1ère colonne)
   - ✅ Badge vert : Pack validé
   - ⚠️ Badge jaune : Pack problématique
   - ❌ Badge rouge : Pack contaminé
   - ? Badge gris : Indéterminé

2. **Date Analyse** (au lieu de "Date prélèvement")
   - En gras et couleur primaire
   - Correspond à la date du pack
   - Format : DD/MM/YYYY HH:MM

3. **Date Résultat** (nouvelle colonne)
   - Date de disponibilité du résultat
   - Format : DD/MM/YYYY HH:MM

## 🔌 Architecture technique

### API créée : `/inspections/analyses-eau/api/packs/stats/`

**Méthode** : GET
**Paramètres** :
- `annee` : Année de filtrage (optionnel)
- `commune_id` : UUID de commune (optionnel)

**Réponse JSON** :
```json
{
  "success": true,
  "packs": [
    {
      "date_analyse": "2024-12-24",
      "date_analyse_fr": "24/12/2024",
      "nb_analyses": 5,
      "nb_equipements": 2,
      "nb_points_eau": 1,
      "nb_traditionnels": 1,
      "nb_bouteilles": 1,
      "nb_autres": 0,
      "statut": "valide",
      "statut_label": "Validé",
      "statut_badge": "success",
      "has_temoin_positif": true,
      "has_contamination": false,
      "analyses_problematiques": []
    }
  ],
  "stats": {
    "total_packs": 10,
    "packs_valides": 8,
    "packs_problematiques": 1,
    "packs_contamines": 1,
    "total_analyses": 50
  }
}
```

### API créée : `/inspections/analyses-eau/api/packs/<date_analyse>/`

**Méthode** : GET
**Paramètres** :
- `date_analyse` : Date ISO (YYYY-MM-DD)

**Réponse JSON** :
```json
{
  "success": true,
  "date_analyse": "2024-12-24",
  "total": 5,
  "analyses": [
    {
      "id": "uuid",
      "type_prelevement": "point_eau_traditionnel",
      "lieu": "Rivière Mandraka",
      "nombre_pour_100ml": 15,
      "est_positif": true
    }
  ]
}
```

## 🔄 Workflow JavaScript

### Fonction loadAnalyses()

1. Construit 2 URLs :
   - `/inspections/analyses-eau/api/list/` (liste des analyses)
   - `/inspections/analyses-eau/api/packs/stats/` (stats des packs)

2. Charge les 2 APIs en **parallèle** avec `Promise.all()`

3. Crée un index des packs par date : `packsData[date_iso] = pack`

4. Appelle `displayAnalyses()` avec les données d'analyses

5. Appelle `updatePacksStats()` avec les stats

### Fonction displayAnalyses()

Pour chaque analyse :
1. Extrait la date d'analyse (DD/MM/YYYY → YYYY-MM-DD)
2. Recherche le pack correspondant dans `packsData`
3. Affiche le badge de statut selon `pack.statut`
4. Génère la ligne HTML avec toutes les colonnes

### Fonction updatePacksStats()

Met à jour les 5 cartes de statistiques avec les données de `stats` :
- `stat-total-packs`
- `stat-packs-valides`
- `stat-packs-problematiques`
- `stat-packs-contamines`
- `stat-total-analyses`

## 📝 Exemples de cas d'usage

### Cas 1 : Pack validé (idéal)

**Analyses du 24/12/2024 :**
- 1× Point d'eau traditionnel : **15 coliformes/100mL** ✅ (témoin positif)
- 1× Bouteille Eau Vive : **0 coliforme** ✅ (témoin négatif)
- 3× Points d'eau FPMH : **0 coliforme** ✅ (échantillons réels)
- 2× Équipements robinet : **0 coliforme** ✅ (échantillons réels)

**Statut pack** : ✅ **VALIDE**
**Action** : Les points d'eau et équipements sont conformes, aucune action requise.

### Cas 2 : Pack problématique (intervention nécessaire)

**Analyses du 25/12/2024 :**
- 1× Point d'eau traditionnel : **20 coliformes/100mL** ✅ (témoin positif)
- 1× Bouteille Eau Vive : **0 coliforme** ✅ (témoin négatif)
- 1× Point d'eau FPMH Ambanja : **8 coliformes/100mL** ❌ **PROBLEME**
- 2× Autres points d'eau : **0 coliforme** ✅

**Statut pack** : ⚠️ **PROBLEMATIQUE**
**Action** : Intervention urgente sur le FPMH Ambanja (contamination réelle).

### Cas 3 : Pack contaminé (refaire analyse)

**Analyses du 26/12/2024 :**
- 1× Point d'eau traditionnel : **25 coliformes/100mL** ✅
- 1× Bouteille Eau Vive : **3 coliformes/100mL** ❌ **CONTAMINATION**
- 3× Points d'eau : **0, 0, 5 coliformes/100mL**
- 1× Équipement : **2 coliformes/100mL**

**Statut pack** : ❌ **CONTAMINE**
**Action** : **Invalider TOUS les résultats**. Refaire l'analyse complète avec nouveau matériel stérile. Les 5 et 2 coliformes trouvés ne sont probablement pas réels mais dus à la contamination du processus.

### Cas 4 : Pack indéterminé (témoin manquant)

**Analyses du 27/12/2024 :**
- 1× Bouteille Eau Vive : **0 coliforme** ✅
- 4× Points d'eau : **0 coliforme** ✅
- Aucun témoin positif ❌

**Statut pack** : ❓ **INDETERMINE**
**Action** : Résultats suspects car aucun témoin positif. Recommandé de refaire avec témoin traditionnel.

## ⚠️ Points d'attention

### Pour les analystes terrain

1. **Toujours inclure un témoin positif** (point d'eau traditionnel) dans chaque pack
2. **Toujours inclure un témoin négatif** (bouteille cachetée neuve) dans chaque pack
3. Si bouteille contaminée → **TOUT ARRETER** et refaire avec matériel stérile
4. Noter la date d'analyse (pas seulement la date de prélèvement)

### Pour les gestionnaires

1. Les stats affichées sont **PAR PACK** (par jour d'analyse), pas par analyse individuelle
2. Un pack contaminé invalide toutes ses analyses, même si certaines montraient des problèmes réels
3. Filtrer par type "point_eau_traditionnel" permet de voir tous les témoins positifs
4. La colonne "Statut Pack" permet de repérer rapidement les problèmes de processus

## 🔍 Dépannage

### Le statut pack n'apparaît pas

**Cause** : L'API `/api/packs/stats/` ne retourne pas de données

**Solution** :
1. Vérifier dans la console : `[INFO] Packs reçus: true packs: X`
2. Si 0 packs : Aucune analyse pour les filtres sélectionnés
3. Si erreur API : Vérifier les logs Django backend

### Les badges sont tous "?"

**Cause** : La conversion de date DD/MM/YYYY → YYYY-MM-DD échoue

**Solution** :
1. Vérifier le format de `date_analyse` retourné par l'API
2. Doit être "DD/MM/YYYY HH:MM" (ex: "24/12/2024 14:30")
3. Vérifier dans la console : `packsData` doit contenir des clés au format "2024-12-24"

### Les statistiques restent à 0

**Cause** : Les éléments DOM n'existent pas ou ont changé d'ID

**Solution** :
1. Vérifier que les IDs existent dans le template :
   - `stat-total-packs`
   - `stat-packs-valides`
   - `stat-packs-problematiques`
   - `stat-packs-contamines`
   - `stat-total-analyses`

## 📚 Références

- **Modèle** : `apps/inspections/models_analyse_eau.py`
- **Vues packs** : `apps/inspections/views_analyse_eau_packs.py`
- **JavaScript** : `static/js/analyses_eau_v4.js`
- **Template** : `templates/inspections/analyses_eau_list.html`
- **URLs** : `apps/inspections/urls.py` (lignes 194-196)

---

**Leçon clé** : L'analyse d'eau n'est pas seulement une mesure individuelle, mais un **processus validé** par des témoins. Un pack contaminé invalide TOUT, même les résultats qui semblaient problématiques.
