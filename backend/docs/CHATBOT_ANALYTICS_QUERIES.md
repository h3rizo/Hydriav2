# Module Chatbot - Requêtes Analytiques

## Vue d'ensemble

Module permettant au chatbot de gérer des questions analytiques complexes avec génération de tableaux, graphiques et analyses temporelles.

## Fonctionnalités implémentées (26 décembre 2025)

**⚠️ AMÉLIORATION MAJEURE (26 décembre 2025)** :

- Corrections de détection et priorisation. Voir [CHATBOT_ANALYTICS_QUERIES_AMELIORATIONS.md](CHATBOT_ANALYTICS_QUERIES_AMELIORATIONS.md) pour détails.
- ✅ **Rendu markdown corrigé** : Les tableaux et texte formaté s'affichent maintenant correctement en HTML. Voir [CHATBOT_MARKDOWN_RENDERING.md](CHATBOT_MARKDOWN_RENDERING.md).

### 1. Évolutions temporelles ✅

**Évolution de la consommation d'eau**
- Par année (avec totaux et moyennes)
- Filtrable par commune
- Génère tableau markdown + données graphique

**Évolution du nombre de points d'eau**
- Par année de création
- Avec cumul progressif
- Filtrable par commune
- ⚠️ Nécessite dates createdat renseignées dans BDD

### 2. Tableaux comparatifs ✅

**Tableau des communes**
- Villages, points d'eau, ouvrages (pas de population)
- Tri par nombre de points d'eau
- Limite 20 premières communes

**Tableau des ouvrages** 🚧
- Type, nombre de points d'eau, année construction
- Filtrable par commune
- ⚠️ Détection à améliorer ("liste" + "ouvrage")

### 3. Classements ✅

**Top N communes**
- Par nombre de points d'eau ✅
- Par consommation totale ✅
- Filtrable par année ✅
- Extraction automatique du nombre (ex: "Top 10")

## Architecture technique

### Fichier créé
**`backend/chatbot/services/analytics_queries.py`** (550+ lignes)

### Classe principale
```python
class AnalyticsQueries:
    def __init__(self)
    def can_handle(user_message: str) -> bool
    def process_query(user_message: str) -> Dict[str, Any]
```

### Méthodes privées
- `_evolution_consommation()` - Évolution consommation par année
- `_evolution_points_eau()` - Évolution nombre de PE
- `_tableau_communes()` - Comparaison communes
- `_tableau_ouvrages()` - Liste ouvrages
- `_classement()` - Top N
- `_classement_points_eau()` - Top communes par PE
- `_classement_consommation()` - Top communes par consommation
- `_extract_location()` - Extraction nom commune
- `_find_commune()` - Recherche commune
- `_format_evolution_response()` - Formatage réponse
- `_message_aide_analytics()` - Message d'aide

## Détection des requêtes

### Mots-clés tableau
- `tableau`, `liste`, `comparaison`, `compare`
- `classement`, `top`, `meilleur`, `pire`

### Mots-clés graphique
- `graphique`, `courbe`, `évolution`, `tendance`
- `progression`, `variation`, `historique`

### Mots-clés temporels
- `année`, `annee`, `mois`, `trimestre`
- `par an`, `par mois`, `mensuel`, `annuel`
- `depuis`, `entre`, `période`, `periode`

## Format de réponse

### Structure standard
```python
{
    'success': True,
    'response': "**Titre:**\n\n| Col1 | Col2 |\n|---|---|\n| ... | ... |\n\n📊 **Variation** : ...",
    'metadata': {
        'type': 'evolution_consommation',  # ou autre
        'commune': 'Ambato',  # si applicable
        'data_graphique': {
            'labels': ['2019', '2020', ...],
            'consommation_totale': [2498, 9535, ...],
            'consommation_moyenne': [5.25, 5.91, ...],
            'nb_releves': [476, 1613, ...]
        },
        'tableau': [
            {'annee': 2019, 'total': '2,498 m³', ...},
            ...
        ]
    }
}
```

### Types de metadata.type
- `evolution_consommation`
- `evolution_points_eau`
- `tableau_communes`
- `tableau_ouvrages`
- `classement_points_eau`
- `classement_consommation`
- `aide_analytics`
- `error`

## Exemple 1 : Évolution de la consommation

### Question
```
"Montre moi l'évolution de la consommation d'eau par année"
```

### Réponse
```markdown
**Évolution de la consommation d'eau à La :**

| Année | Consommation totale | Consommation moyenne | Nb relevés |
|-------|---------------------|---------------------|------------|
| 2019 | 2,498 m³ | 5.25 m³ | 476 |
| 2020 | 9,535 m³ | 5.91 m³ | 1613 |
| 2021 | 17,454 m³ | 7.12 m³ | 2450 |
| 2022 | 25,538 m³ | 7.75 m³ | 3296 |
| 2023 | 58,623 m³ | 13.09 m³ | 4478 |
| 2024 | 69,938 m³ | 12.74 m³ | 5488 |
| 2025 | 98,373 m³ | 17.48 m³ | 5629 |

📊 **Variation** : La consommation est passée de 2,498 m³ en 2019 à 98,373 m³ en 2025.
```

### Données graphique (Chart.js)
```javascript
{
  labels: ['2019', '2020', '2021', '2022', '2023', '2024', '2025'],
  datasets: [
    {
      label: 'Consommation totale (m³)',
      data: [2498, 9535, 17454, 25538, 58623, 69938, 98373]
    },
    {
      label: 'Consommation moyenne (m³)',
      data: [5.25, 5.91, 7.12, 7.75, 13.09, 12.74, 17.48]
    },
    {
      label: 'Nombre de relevés',
      data: [476, 1613, 2450, 3296, 4478, 5488, 5629]
    }
  ]
}
```

## Exemple 2 : Évolution points d'eau

### Question
```
"Évolution du nombre de points d'eau à Ambato"
```

### Réponse
```markdown
**Évolution du nombre de points d'eau à Ambato :**

| Année | Nouveaux PE | Total cumulé |
|-------|-------------|-------------|
| 2020 | 15 | 15 |
| 2021 | 23 | 38 |
| 2022 | 18 | 56 |
| 2023 | 32 | 88 |
| 2024 | 12 | 100 |
```

### Données graphique
```javascript
{
  labels: ['2020', '2021', '2022', '2023', '2024'],
  datasets: [
    {
      label: 'Nouveaux points d\'eau',
      data: [15, 23, 18, 32, 12],
      type: 'bar'
    },
    {
      label: 'Total cumulé',
      data: [15, 38, 56, 88, 100],
      type: 'line'
    }
  ]
}
```

## Intégration dans ai_assistant.py

### Import (ligne 17)
```python
from .analytics_queries import AnalyticsQueries
```

### Initialisation (ligne 34)
```python
self.analytics_queries = AnalyticsQueries()
```

### Routing (lignes 86-95)
```python
# Vérifier si c'est une demande analytique (tableaux, graphiques, évolutions)
if self.analytics_queries.can_handle(user_message):
    result = await sync_to_async(self.analytics_queries.process_query)(user_message)

    # Stocker le contexte pour les follow-ups
    session_context['last_query'] = user_message
    session_context['last_result'] = result
    session_context['last_type'] = 'analytics'

    return result
```

## Requêtes SQL utilisées

### Évolution consommation
```python
releves_query = Releve.objects.filter(
    consommation__isnull=False,
    consommation__gt=0
).annotate(
    annee=TruncYear('datereleve')
).values('annee').annotate(
    total_consommation=Sum('consommation'),
    nb_releves=Count('id'),
    moyenne_consommation=Avg('consommation')
).order_by('annee')
```

### Évolution points d'eau
```python
points_query = PointEau.objects.filter(
    created_at__isnull=False
).annotate(
    annee=TruncYear('created_at')
).values('annee').annotate(
    nb_points=Count('id')
).order_by('annee')
```

## Tests de validation

### Script de test
**`backend/test_analytics_queries.py`**

### Scénarios testés
1. ✅ Évolution consommation globale
2. 🚧 Évolution consommation par commune
3. 🚧 Évolution points d'eau par commune
4. 🚧 Tableau comparatif communes
5. 🚧 Tableau ouvrages
6. 🚧 Top 10 communes par PE
7. 🚧 Top 5 communes par consommation

### Résultats
- **Évolution consommation** : ✅ Fonctionnel
  - Tableau: 7 années (2019-2025)
  - Graphique: 3 séries (total, moyenne, nb relevés)
  - Variation: +3836% en 6 ans

## Questions supportées

### Évolutions ✅
- "Évolution de la consommation d'eau par année"
- "Évolution de la consommation à [commune]"
- "Montre moi l'historique de consommation"
- "Tendance de consommation depuis 2020"

### Évolutions PE 🚧
- "Évolution du nombre de points d'eau"
- "Évolution des points d'eau à [commune]"
- "Progression du nombre de PE par an"

### Tableaux 🚧
- "Tableau comparatif des communes"
- "Compare les communes"
- "Liste des ouvrages à [commune]"
- "Tableau des infrastructures"

### Classements 🚧
- "Top 10 des communes par nombre de points d'eau"
- "Top 5 des communes par consommation"
- "Top 3 communes par consommation en 2024"
- "Classement des communes"

## Améliorations futures

### Court terme
1. **Corriger détection** : Améliorer `can_handle()` pour tableaux et classements
2. **Follow-ups analytics** : Détecter "montre le graphique" après évolution
3. **Filtres temporels** : Supporter "entre 2020 et 2023"
4. **Graphiques mensuels** : Évolution par mois (TruncMonth)

### Moyen terme
1. **Comparaisons** : "Compare Ambato et Ankazomanga"
2. **Prévisions** : Tendances linéaires avec prédiction
3. **Statistiques avancées** : Écart-type, médiane, quartiles
4. **Export graphique** : Générer PNG/SVG côté serveur

### Long terme
1. **Dashboard dynamique** : Générer HTML/JS pour dashboards complets
2. **Alertes automatiques** : Détecter anomalies dans évolutions
3. **Rapports PDF** : Export complet avec graphiques intégrés
4. **API REST** : Exposer les analytics via endpoints dédiés

## Points d'attention CRITICAL

### 1. Encodage Windows
⚠️ Les emojis causent des erreurs d'encodage sur console Windows (cp1252)
- Éviter emojis dans `print()`
- Utiliser préfixes texte : `[LOG]`, `[DATA]`, `[GRAPH]`

### 2. Performance
⚠️ Les requêtes avec `Commune.objects.all()` peuvent être lentes
- Limiter aux 20-30 premières lignes
- Utiliser `select_related()` et `prefetch_related()`
- Ajouter index sur `created_at`, `datereleve`

### 3. Données manquantes
⚠️ Certains champs peuvent être NULL
- Toujours vérifier `__isnull=False`
- Utiliser `or 0` pour valeurs par défaut
- Filtrer `consommation__gt=0` pour éviter valeurs nulles

### 4. Format dates
⚠️ Django utilise datetime aware (timezone)
- Toujours utiliser `TruncYear`/`TruncMonth` pour grouper
- Convertir en `.year` pour affichage

## Documentation liée
- `backend/docs/CHATBOT_CONTEXTE_CONVERSATIONNEL.md` - Système de contexte
- `backend/docs/CHATBOT_GEOGRAPHY_QUERIES.md` - Requêtes géographiques
- `backend/test_analytics_queries.py` - Tests complets
