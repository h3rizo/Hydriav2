# Module Chatbot - Requêtes Géographiques avec Détails par Ouvrage

## Vue d'ensemble

Extension du module GeographyQueries pour permettre d'obtenir un **détail par ouvrage** lors des requêtes sur les points d'eau.

## Nouveauté : Détail par Ouvrage (26 décembre 2025)

### Problème résolu

Avant cette amélioration, le chatbot ne fournissait qu'un **compte total** :

```
Question : "Combien de points d'eau à Ambato ?"
Réponse : "💧 100 points d'eau"
```

L'utilisateur devait ensuite demander manuellement les détails, sans garantie d'obtenir une répartition par ouvrage.

### Solution implémentée

Le système détecte maintenant automatiquement si l'utilisateur demande des détails et fournit une **répartition complète par ouvrage** :

```
Question : "Combien de points d'eau à Ambato détail ?"
ou "Liste des points d'eau par ouvrage à Ambato"
ou "Donne moi les détails des points d'eau à Ambato"

Réponse :
**Points d'eau de Ambato - Détail par ouvrage :**

📊 **Total : 100** points d'eau
🏗️ **14** ouvrages

**Répartition :**
  • **Ambato (AEPG)** : 16 points d'eau
  • **Antanetibe (AEPG)** : 14 points d'eau
  • **Ankadibe (AEPG)** : 12 points d'eau
  • **Ambohimitsinjorano (AEPG)** : 11 points d'eau
  • ... (liste complète)
```

## Détection des demandes de détails

### Mots-clés détectés

Le système détecte les mots-clés suivants (insensible à la casse) :

- `détail`
- `detail`
- `par ouvrage`
- `liste`
- `tous`

**Code** (geography_queries.py ligne 599) :
```python
wants_details = any(keyword in message_lower for keyword in ['détail', 'detail', 'par ouvrage', 'liste', 'tous'])
```

### Exemples de questions acceptées

#### Questions qui déclenchent les détails

✅ "Combien de points d'eau à Ambato **détail**"
✅ "Combien de points d'eau à Ambato **detail**"
✅ "Liste des points d'eau **par ouvrage** à Ambato"
✅ "Donne moi **les détails** des points d'eau à Ambato"
✅ "Montre moi **tous** les points d'eau à Ambato"

#### Questions qui donnent le total simple

❌ "Combien de points d'eau à Ambato"
❌ "Nombre de points d'eau à Ambato"

## Architecture technique

### Optimisation des requêtes

Pour éviter le problème N+1, les relations sont pré-chargées :

```python
points_eau = PointEau.objects.filter(
    parcelle__village__fokontany__commune=commune
).select_related('ouvrage', 'ouvrage__type_ouvrage')
```

### Logique de groupement

**Étape 1** : Créer un dictionnaire avec les ouvrages comme clés

```python
ouvrages_dict = {}
for pe in points_eau:
    if pe.ouvrage:
        ouvrage_key = f"{pe.ouvrage.nom_ouvrage} ({pe.ouvrage.type_ouvrage.nom_type_ouvrage if pe.ouvrage.type_ouvrage else 'Type non renseigné'})"
        if ouvrage_key not in ouvrages_dict:
            ouvrages_dict[ouvrage_key] = 0
        ouvrages_dict[ouvrage_key] += 1
    else:
        if 'Sans ouvrage' not in ouvrages_dict:
            ouvrages_dict['Sans ouvrage'] = 0
        ouvrages_dict['Sans ouvrage'] += 1
```

**Étape 2** : Trier par nombre décroissant

```python
ouvrages_sorted = sorted(ouvrages_dict.items(), key=lambda x: x[1], reverse=True)
```

**Étape 3** : Construire la liste formatée

```python
details_list = "\n".join([
    f"  • **{ouvrage}** : {nb} point{'s' if nb > 1 else ''} d'eau"
    for ouvrage, nb in ouvrages_sorted
])
```

### Format de réponse

**Réponse simple** (metadata.type = `points_eau`) :
```json
{
  "success": true,
  "response": "**Points d'eau de Ambato :**\n\n💧 **100** points d'eau",
  "metadata": {
    "type": "points_eau",
    "location": "Ambato",
    "location_type": "commune",
    "count": 100
  }
}
```

**Réponse détaillée** (metadata.type = `points_eau_details`) :
```json
{
  "success": true,
  "response": "**Points d'eau de Ambato - Détail par ouvrage :**\n\n📊 **Total : 100** points d'eau\n🏗️ **14** ouvrages\n\n**Répartition :**\n  • **Ambato (AEPG)** : 16 points d'eau\n  • **Antanetibe (AEPG)** : 14 points d'eau\n  ...",
  "metadata": {
    "type": "points_eau_details",
    "location": "Ambato",
    "location_type": "commune",
    "count": 100,
    "ouvrages_count": 14,
    "details": {
      "Ambato (AEPG)": 16,
      "Antanetibe (AEPG)": 14,
      "Ankadibe (AEPG)": 12,
      ...
    }
  }
}
```

## Niveaux géographiques supportés

La fonctionnalité de détail est disponible pour **tous les niveaux géographiques** :

### 1. Commune

```python
if commune:
    points_eau = PointEau.objects.filter(
        parcelle__village__fokontany__commune=commune
    ).select_related('ouvrage', 'ouvrage__type_ouvrage')
```

**Exemple** : "Liste des points d'eau par ouvrage à Ambato"

### 2. Fokontany

```python
if fokontany:
    points_eau = PointEau.objects.filter(
        parcelle__village__fokontany=fokontany
    ).select_related('ouvrage', 'ouvrage__type_ouvrage')
```

**Exemple** : "Détail des points d'eau à Ambohimanarina"

### 3. Village

```python
if village:
    points_eau = PointEau.objects.filter(
        parcelle__village=village
    ).select_related('ouvrage', 'ouvrage__type_ouvrage')
```

**Exemple** : "Tous les points d'eau par ouvrage à Ankazomanga"

## Tests effectués

### Script de test

**Fichier** : `backend/test_points_eau_details_simple.py`

**Questions testées** :
1. ✅ "Combien de points d'eau à Ambato" → Type `points_eau` (simple)
2. ✅ "Combien de points d'eau à Ambato détail" → Type `points_eau_details` (14 ouvrages)
3. ✅ "Liste des points d'eau par ouvrage à Ambato" → Type `points_eau_details` (14 ouvrages)
4. ✅ "Donne moi les détails des points d'eau à Ambato" → Type `points_eau_details` (14 ouvrages)

### Résultats de validation

**Commune Ambato** :
- Total : 100 points d'eau
- Ouvrages : 14
- Ouvrage principal : Ambato (AEPG) avec 16 points d'eau
- Tri : Ordre décroissant (16, 14, 12, 11, 8, ...)

### Fichiers de résultats

Les résultats JSON sont sauvegardés dans :
- `test_result_pe_Question_simple.json` - Réponse simple
- `test_result_pe_Avec_'détail'.json` - Réponse détaillée
- `test_result_pe_Avec_'par_ouvrage'.json` - Réponse détaillée
- `test_result_pe_Avec_'détails'.json` - Réponse détaillée

## Workflow utilisateur

### Scénario 1 : Question simple

1. **Utilisateur** : "Combien de points d'eau à Ambato ?"
2. **Chatbot** : "💧 **100** points d'eau"

### Scénario 2 : Question avec détails

1. **Utilisateur** : "Combien de points d'eau à Ambato ?"
2. **Chatbot** : "💧 **100** points d'eau"
3. **Utilisateur** : "Tu peux me donner les détails de ce calcul ?"
4. **Chatbot** : Détection du mot-clé "détails" → Affiche répartition par ouvrage

### Scénario 3 : Demande directe de détails

1. **Utilisateur** : "Liste des points d'eau par ouvrage à Ambato"
2. **Chatbot** : Détection du mot-clé "par ouvrage" → Affiche directement la répartition

## Points d'attention CRITICAL

### 1. Tri par nombre décroissant

⚠️ Les ouvrages sont TOUJOURS triés par nombre de points d'eau (ordre décroissant)

**Raison** : Mettre en évidence les ouvrages principaux en premier

### 2. Gestion des ouvrages sans type

⚠️ Si `ouvrage.type_ouvrage` est NULL, afficher "Type non renseigné"

```python
ouvrage_key = f"{pe.ouvrage.nom_ouvrage} ({pe.ouvrage.type_ouvrage.nom_type_ouvrage if pe.ouvrage.type_ouvrage else 'Type non renseigné'})"
```

### 3. Gestion des points d'eau sans ouvrage

⚠️ Si `point_eau.ouvrage` est NULL, grouper sous "Sans ouvrage"

```python
else:
    if 'Sans ouvrage' not in ouvrages_dict:
        ouvrages_dict['Sans ouvrage'] = 0
    ouvrages_dict['Sans ouvrage'] += 1
```

### 4. Pluriel conditionnel

⚠️ Gérer le pluriel de "point d'eau" et "ouvrage"

```python
f"{nb} point{'s' if nb > 1 else ''} d'eau"
f"{len(ouvrages_sorted)} ouvrage{'s' if len(ouvrages_sorted) > 1 else ''}"
```

## Fichiers modifiés

### 1. `backend/chatbot/services/geography_queries.py`

**Lignes 597-669** : Section Commune avec détails
```python
# Vérifier si l'utilisateur demande les détails
message_lower = message.lower()
wants_details = any(keyword in message_lower for keyword in ['détail', 'detail', 'par ouvrage', 'liste', 'tous'])

if commune:
    points_eau = PointEau.objects.filter(...).select_related('ouvrage', 'ouvrage__type_ouvrage')

    if wants_details:
        # Logique de groupement
        ...
        return {
            'success': True,
            'response': f"**Points d'eau de {commune.nom_commune} - Détail par ouvrage :**\n\n...",
            'metadata': {
                'type': 'points_eau_details',
                'ouvrages_count': len(ouvrages_sorted),
                'details': dict(ouvrages_sorted)
            }
        }
```

**Lignes 671-737** : Section Fokontany avec détails (même logique)

**Lignes 739-809** : Section Village avec détails (même logique)

## Prochaines améliorations possibles

1. **Filtrage par type d'ouvrage** : "Liste des AEPG à Ambato"
2. **Statistiques avancées** : Moyenne, médiane, écart-type
3. **Export Excel** : Générer fichier avec répartition
4. **Visualisation graphique** : Diagramme en barres ou camembert
5. **Comparaison** : "Compare les points d'eau entre Ambato et Ankazomanga"
6. **Historique** : "Évolution des points d'eau à Ambato sur 2024"

## Documentation liée

- `backend/docs/CHATBOT_GEOGRAPHY_QUERIES.md` - Documentation principale du module
- `backend/chatbot/services/geography_queries.py` - Code source
- `backend/test_points_eau_details_simple.py` - Script de test
