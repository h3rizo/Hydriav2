# Évaluation de la Saisie Comptable - Documentation (12 décembre 2025)

## Vue d'ensemble
Module d'évaluation de la qualité et de la productivité de la saisie comptable dans DiameX, basé sur l'analyse du champ `date_input` (date de saisie) comparé à `date_m` (date comptable).

## Fonctionnalités implémentées

### 1. Statistiques globales (4 cartes)
- **Total lignes saisies** : Nombre total de lignes avec `date_input` renseigné
- **Saisie conforme** : Lignes saisies dans le même mois que `date_m` (avec radial progress)
- **Saisie hors mois** : Lignes saisies dans un mois différent de `date_m` (avec radial progress)
- **Moyenne par jour** : Productivité moyenne + pic journalier

### 2. Graphiques interactifs (Chart.js)

#### Graphique 1 : Lignes saisies par jour
- **Type** : Ligne (line chart)
- **Données** :
  - Total lignes saisies par jour
  - Lignes conformes (même mois)
  - Lignes hors mois
- **Utilité** : Visualiser la productivité quotidienne et la qualité de la saisie

#### Graphique 2 : Conformité par mois comptable (avec détail du décalage)
- **Type** : Barres empilées (stacked bar chart)
- **Données** : 5 catégories empilées
  - 🟢 **Conformes** : Lignes saisies dans le même mois comptable
  - 🔵 **Décalage 1 mois** : Saisies avec 1 mois de retard
  - 🟠 **Décalage 2 mois** : Saisies avec 2 mois de retard
  - 🔴 **Décalage 3 mois** : Saisies avec 3 mois de retard
  - 🟣 **Décalage 4+ mois** : Saisies avec 4 mois ou plus de retard
- **Utilité** : Identifier les mois avec le plus de décalage ET la gravité du décalage
- **Tooltip** : Affiche le total de lignes pour chaque mois au survol

#### Graphique 3 : Délai entre date comptable et date de saisie (jours)
- **Type** : Barres (bar chart)
- **Plages** :
  - Même jour
  - J+1 à J+7
  - J+8 à J+30
  - J+31 et plus
  - Saisie en retard (date_input < date_m)
- **Utilité** : Évaluer la réactivité de la saisie en jours

#### Graphique 4 : Décalage par mois (date_rec vs date_input)
- **Type** : Barres (bar chart)
- **Plages** :
  - Même mois (0 mois)
  - 1 mois de décalage
  - 2 mois de décalage
  - 3 mois de décalage
  - 4+ mois de décalage
- **Utilité** : Analyser les non-conformités en termes de mois de retard entre la date de réception (`date_rec`) et la date de saisie (`date_input`)
- **Note** : Utilise `date_rec` au lieu de `date_m` pour identifier les saisies très décalées

### 3. Vue Calendrier par fichier source
- **Sélecteurs** : Mois et année dynamiques
- **3 cartes de statistiques** : Une par fichier source (Soakoja, Sahanala, etc.) avec total de lignes saisies pour le mois
- **3 calendriers** : Un par fichier source, affichage en grille (Lun-Dim)
- **Couleurs** :
  - ✅ **Vert** : 100+ lignes saisies
  - ⚠️ **Orange** : 50-99 lignes saisies
  - ℹ️ **Bleu** : 1-49 lignes saisies
  - ⚪ **Gris** : Aucune saisie
- **Badge sur chaque jour** : Nombre exact de lignes saisies
- **Utilité** : Visualiser la répartition temporelle de la saisie et identifier les jours sans saisie

### 4. Top 10 jours productifs
- **Tableau** : Classement des 10 jours avec le plus de lignes saisies
- **Colonnes** :
  - Rang (avec trophée pour le top 3)
  - Date
  - Total lignes
  - Lignes conformes
  - Lignes hors mois
  - Taux de conformité (badge coloré)

### 5. Filtres dynamiques
- **Date début saisie** : Filtrer par `date_input >= date_debut`
- **Date fin saisie** : Filtrer par `date_input <= date_fin`
- **Fichier source** : Filtrer par base DiameX spécifique
- **Bouton Actualiser** : Recharger toutes les données avec les nouveaux filtres
- **Note** : Les filtres s'appliquent aux graphiques et statistiques, mais PAS au calendrier (qui a ses propres sélecteurs mois/année)

## Architecture technique

### Backend : `apps/accounting/views_evaluation_saisie.py`

**9 APIs REST créées** :

1. **`evaluation_saisie(request)`** - Vue principale
   - Retourne la page HTML avec contexte minimal

2. **`api_stats_saisie_globales(request)`** - Statistiques globales
   - Total lignes, conformes, hors mois, sans date_m
   - Taux conformité, taux hors mois
   - Jours de saisie, moyenne par jour
   - Jour le plus productif

3. **`api_saisie_par_jour(request)`** - Données graphique jour
   - Groupement par `date_input`
   - Compteurs : total, conformes, hors mois

4. **`api_saisie_par_mois_compta(request)`** - Données graphique mois
   - Groupement par `TruncMonth('date_m')`
   - Analyse du décalage de saisie par mois comptable

5. **`api_delai_saisie(request)`** - Données graphique délai (jours)
   - Calcul du délai : `date_input - date_m`
   - Catégorisation en 5 plages (jours)

6. **`api_fichiers_sources(request)`** - Liste des fichiers sources
   - Retourne fichiers distincts avec compteur
   - Pour alimenter le filtre

7. **`api_top_jours_productifs(request)`** - Top 10
   - Jours triés par nombre de lignes (DESC)
   - Avec stats de conformité

8. **`api_decalage_par_mois(request)`** - ✨ NOUVEAU - Décalage en mois
   - Calcul différence en mois : `date_input.year/month - date_rec.year/month`
   - Catégorisation : 0 mois, 1 mois, 2 mois, 3 mois, 4+ mois
   - Utilise `iterator(chunk_size=1000)` pour performance
   - Utilise `date_rec` (date de réception) au lieu de `date_m`

9. **`api_calendrier_saisie(request)`** - ✨ NOUVEAU - Calendrier mensuel
   - Paramètres : `mois` et `annee`
   - Retourne données pour chaque fichier source
   - Format : `{ fichiers: { nom, jours: { '2025-12-01': 150, ... }, total_mois } }`
   - Utilisé pour afficher les 3 calendriers par fichier source

### Frontend : `templates/accounting/evaluation_saisie.html`

**Composants DaisyUI utilisés** :
- `stat` : Cartes de statistiques avec radial-progress
- `card` : Conteneurs pour graphiques
- `form-control`, `input`, `select` : Filtres
- `table` : Top 10 jours productifs
- `badge` : Indicateurs colorés (rang, taux)
- `alert` : Information sur les délais

**Chart.js 4.4.0** :
- CDN : `https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js`
- Configuration responsive avec `maintainAspectRatio: false`
- Tooltips interactifs avec formatage français

**JavaScript** :
- `chargerFichiersSources()` : Charge liste déroulante
- `chargerStatistiquesGlobales()` : Met à jour les 4 cartes
- `chargerGraphiqueParJour()` : Crée/détruit Chart.js ligne
- `chargerGraphiqueParMois()` : Crée/détruit Chart.js empilé
- `chargerGraphiqueDelais()` : Crée/détruit Chart.js barres (délais en jours)
- `chargerGraphiqueDecalageMois()` : ✨ NOUVEAU - Crée/détruit Chart.js barres (décalage en mois)
- `chargerTopJours()` : Remplit tableau dynamiquement
- `chargerCalendrier()` : ✨ NOUVEAU - Génère calendriers HTML pour chaque fichier source
- `appliquerFiltres()` : Recharge toutes les données (sauf calendrier)

## Requêtes SQL importantes

### Détection saisie hors mois
```python
BaseDiameX.objects.filter(
    Q(date_m__isnull=False) &
    (
        ~Q(date_input__month=F('date_m__month')) |
        ~Q(date_input__year=F('date_m__year'))
    )
)
```

### Calcul du délai (exemple J+1 à J+7)
```python
BaseDiameX.objects.filter(
    date_input__gt=F('date_m'),
    date_input__lte=F('date_m') + timedelta(days=7)
)
```

### Groupement par mois comptable
```python
BaseDiameX.objects.annotate(
    mois_compta=TruncMonth('date_m')
).values('mois_compta').annotate(
    total=Count('id'),
    conformes=Count('id', filter=Q(...)),
    hors_mois=Count('id', filter=Q(...))
)
```

### ✨ NOUVEAU - Calcul du décalage en mois (date_rec vs date_input)
```python
from dateutil.relativedelta import relativedelta

qs = BaseDiameX.objects.filter(
    date_input__isnull=False,
    date_rec__isnull=False
)

stats = {
    'decalage_0': 0,  # Même mois
    'decalage_1': 0,  # 1 mois de décalage
    'decalage_2': 0,  # 2 mois
    'decalage_3': 0,  # 3 mois
    'decalage_4_plus': 0,  # 4+ mois
}

for entry in qs.iterator(chunk_size=1000):
    diff_mois = (entry.date_input.year - entry.date_rec.year) * 12 + \
                (entry.date_input.month - entry.date_rec.month)
    diff_mois = abs(diff_mois)

    if diff_mois == 0:
        stats['decalage_0'] += 1
    elif diff_mois == 1:
        stats['decalage_1'] += 1
    elif diff_mois == 2:
        stats['decalage_2'] += 1
    elif diff_mois == 3:
        stats['decalage_3'] += 1
    else:  # 4+ mois
        stats['decalage_4_plus'] += 1
```

### ✨ NOUVEAU - Génération du calendrier par fichier source
```python
from calendar import monthrange

annee = 2025
mois = 12
nb_jours = monthrange(int(annee), int(mois))[1]
date_debut = f"{annee}-{str(mois).zfill(2)}-01"
date_fin = f"{annee}-{str(mois).zfill(2)}-{nb_jours}"

# Récupérer les fichiers sources
fichiers = BaseDiameX.objects.filter(
    date_input__isnull=False
).values_list('fichier_source', flat=True).distinct()

# Pour chaque fichier source
for fichier in fichiers:
    saisies_jour = BaseDiameX.objects.filter(
        date_input__gte=date_debut,
        date_input__lte=date_fin,
        fichier_source=fichier
    ).values('date_input').annotate(
        total=Count('id')
    ).order_by('date_input')

    # Créer dictionnaire date -> count
    jours_data = {
        item['date_input'].strftime('%Y-%m-%d'): item['total']
        for item in saisies_jour
    }
```

## Cas d'usage

### 1. Évaluer la productivité mensuelle
**Action** : Filtrer par mois (ex: date_debut=2025-11-01, date_fin=2025-11-30)
**Résultat** :
- Total lignes saisies en novembre
- Moyenne par jour de saisie
- Identification des jours les plus productifs

### 2. Identifier les problèmes de décalage
**Symptôme** : Taux conformité < 80%
**Analyse** :
- Graphique "Conformité par mois comptable" montre les mois problématiques
- Graphique "Délai" indique si le problème vient d'une saisie tardive ou anticipée

### 3. Comparer les bases DiameX
**Action** : Changer le filtre "Fichier source"
**Résultat** : Comparer la qualité de saisie entre les 3 bases (Soakoja, Sahanala, etc.)

### 4. Audit de conformité
**Objectif** : Vérifier que les lignes sont saisies dans les 7 jours
**Méthode** : Graphique "Délai" → Somme des barres "Même jour" + "J+1 à J+7"

## Interprétation des indicateurs

### Taux de conformité
- **90-100%** : ✅ Excellent - Saisie rigoureuse
- **70-89%** : ⚠️ Acceptable - Quelques décalages
- **< 70%** : ❌ Problématique - Processus à revoir

### Délai de saisie
- **Même jour** : Idéal pour traçabilité
- **J+1 à J+7** : Acceptable (délai raisonnable)
- **J+8 à J+30** : Attention (impact sur clôture mensuelle)
- **J+31+** : Problème grave (comptabilité décalée)
- **Retard** : Anomalie (saisie antidatée)

### Moyenne par jour
- **< 50 lignes/jour** : Productivité faible
- **50-150 lignes/jour** : Productivité normale
- **> 150 lignes/jour** : Productivité élevée (ou régularisation)

## URLs et routes

**Page principale** : `/comptabilite/evaluation-saisie/`
**APIs** :
- `/comptabilite/api/evaluation-saisie/stats-globales/`
- `/comptabilite/api/evaluation-saisie/par-jour/`
- `/comptabilite/api/evaluation-saisie/par-mois-compta/`
- `/comptabilite/api/evaluation-saisie/delai/`
- `/comptabilite/api/evaluation-saisie/fichiers-sources/`
- `/comptabilite/api/evaluation-saisie/top-jours/`
- `/comptabilite/api/evaluation-saisie/decalage-mois/` ✨ NOUVEAU
- `/comptabilite/api/evaluation-saisie/calendrier/?mois=12&annee=2025` ✨ NOUVEAU

**Menu** : Comptabilité > Évaluation > Évaluation Saisie

## Fichiers créés/modifiés

**Créés** :
1. `backend/apps/accounting/views_evaluation_saisie.py` (439 lignes) - 9 APIs (2 nouvelles ajoutées)
2. `backend/templates/accounting/evaluation_saisie.html` (784 lignes) - Interface complète avec calendriers
3. `backend/docs/EVALUATION_SAISIE_COMPTABLE.md` (ce fichier) - Documentation

**Modifiés** :
1. `backend/apps/accounting/urls.py` (lignes 19, 137-146) - Import + 9 routes (2 nouvelles)
2. `backend/templates/base.html` (lignes 336-337, 636-637) - Liens menu (mobile + desktop)

**✨ Nouveautés 12 décembre 2025** :
1. Graphique "Décalage par mois" (date_rec vs date_input)
2. Vue calendrier avec 3 cartes par fichier source
3. Génération dynamique de calendriers mensuels
4. Code couleur selon nombre de lignes saisies
5. Sélecteurs mois/année indépendants des filtres principaux

## Prochaines améliorations possibles

1. **Export Excel** : Télécharger les données brutes pour analyse externe
2. **Alertes automatiques** : Email si taux conformité < seuil
3. **Comparaison périodes** : Comparer novembre 2024 vs novembre 2025
4. **Analyse par utilisateur** : Si champ `user_input` existe dans BaseDiameX
5. **Dashboard temps réel** : Refresh auto toutes les 5 minutes
6. **Prévisions** : ML pour prédire la charge de saisie

## Tests de validation

- [ ] Affichage page sans erreur
- [ ] Statistiques globales correctes
- [ ] Graphiques s'affichent (Chart.js chargé)
- [ ] Filtres fonctionnels (date, fichier source)
- [ ] Top 10 affiché avec données réelles
- [ ] Responsive (mobile/tablette/desktop)
- [ ] Performance acceptable (< 3s chargement)

---

**Date création** : 12 décembre 2025
**Modèle utilisé** : BaseDiameX (table `base_diamex`)
**Champs critiques** : `date_input`, `date_m`, `fichier_source`
**Impact utilisateur** : ✅ Outil stratégique pour piloter la qualité de la saisie comptable
