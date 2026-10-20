# 📚 Guide d'entraînement du Chatbot Hydria

## 🎯 Vue d'ensemble

Le chatbot Hydria peut maintenant répondre aux demandes de statistiques et comptages en utilisant les APIs de dashboard existantes. Ce guide explique comment le système fonctionne et comment l'entraîner pour de nouvelles fonctionnalités.

## 🏗️ Architecture du système

```
User Question
     ↓
AIAssistant (chatbot/services/ai_assistant.py)
     ↓
StatsHandler (chatbot/services/stats_handler.py)
     ↓
Dashboard API (/api/dashboard/)
     ↓
Response formatée
```

## 🔧 Fichiers créés/modifiés

### 1. **StatsHandler** (`chatbot/services/stats_handler.py`)
Gestionnaire principal pour les demandes de statistiques.

**Fonctionnalités :**
- Détection automatique des demandes de comptage
- Extraction des entités (ouvrages, points d'eau, équipements, etc.)
- Extraction des filtres géographiques (région, district, commune)
- Extraction des filtres temporels (année)
- Appel à l'API dashboard
- Formatage des réponses

### 2. **AIAssistant modifié** (`chatbot/services/ai_assistant.py`)
Intégration du StatsHandler dans le flux principal.

**Modification :**
```python
# Vérifier d'abord si c'est une demande de statistiques
if self.stats_handler.can_handle(user_message):
    return self.stats_handler.generate_response(user_message)
```

### 3. **Données d'entraînement** (`chatbot/training_data/stats_examples.json`)
Exemples de questions et patterns pour l'entraînement.

## 📖 Exemples de questions supportées

### Comptages simples
```
"Combien d'ouvrages ?"
"Nombre de points d'eau"
"Total des équipements"
"Combien y a-t-il de compteurs de tête ?"
```

### Avec filtres géographiques
```
"Combien d'ouvrages dans la région Fitovinany ?"
"Nombre de points d'eau dans le district de Manakara"
"Total des habitants dans la commune de Vohipeno"
```

### Avec filtres temporels
```
"Combien d'ouvrages en 2023 ?"
"Nombre de points d'eau pour l'année 2024"
"Statistiques pour 2024"
```

### Filtres combinés
```
"Combien d'ouvrages dans la région Fitovinany en 2023 ?"
"Nombre de points d'eau dans le district de Manakara pour 2024"
```

### Questions multiples
```
"Combien d'ouvrages et de points d'eau ?"
"Statistiques sur les équipements et compteurs"
"Donne moi les statistiques"  (résumé complet)
```

### Comparaisons
```
"Combien de points d'eau privés vs publics ?"
"Répartition des points d'eau"
```

## 🎓 Comment entraîner pour de nouvelles entités

### Étape 1 : Ajouter l'entité dans `StatsHandler`

Éditez `chatbot/services/stats_handler.py` :

```python
self.entity_mappings = {
    # ... entités existantes ...
    'nouvelle_entite': ['variation1', 'variation2', 'variation3'],
}
```

### Étape 2 : Mapper vers l'API

Ajoutez le mapping dans la méthode `generate_response()` :

```python
entity_to_api_key = {
    # ... mappings existants ...
    'nouvelle_entite': ('cle_api', 'nom d\'affichage'),
}
```

### Étape 3 : Tester

Exemples de questions à tester :
```
"Combien de [nouvelle_entite] ?"
"Nombre de [variation1]"
"Total des [variation2]"
```

## 🔍 Comment ajouter de nouveaux filtres

### Exemple : Ajouter un filtre "organisation"

1. **Ajouter le pattern de détection** dans `StatsHandler.__init__()` :
```python
self.filter_patterns = {
    # ... patterns existants ...
    'organisation': r'(?:dans|en|pour|de)\s+(?:l\')?organisation\s+(.+?)(?:\s|$|,)',
}
```

2. **Modifier `get_dashboard_stats()`** pour passer le filtre à l'API :
```python
if 'organisation_id' in filters:
    params.append(f"organisation_id={filters['organisation_id']}")
```

3. **Ajouter dans les exemples d'entraînement** (`stats_examples.json`) :
```json
{
  "category": "Filtres organisation",
  "questions": [
    "Combien d'ouvrages pour l'organisation X ?",
    "Points d'eau de l'organisation Y"
  ],
  "expected_filters": ["organisation"]
}
```

## 🧪 Tests recommandés

### Test 1 : Questions simples
```python
questions = [
    "Combien d'ouvrages ?",
    "Nombre de points d'eau",
    "Total des équipements"
]
```

**Résultat attendu :** Nombre formaté avec l'entité demandée

### Test 2 : Avec filtres
```python
questions = [
    "Combien d'ouvrages dans la région Fitovinany ?",
    "Points d'eau en 2023"
]
```

**Résultat attendu :** Nombre + mention des filtres appliqués

### Test 3 : Questions multiples
```python
question = "Combien d'ouvrages et de points d'eau ?"
```

**Résultat attendu :** Liste à puces avec chaque comptage

### Test 4 : Résumé général
```python
question = "Donne moi les statistiques"
```

**Résultat attendu :** Résumé complet avec ouvrages, points d'eau, habitants

## 🎨 Personnalisation des réponses

### Modifier le formatage

Éditez `StatsHandler.generate_response()` pour changer le format des réponses :

```python
# Format actuel
response_parts.append(f"• **{self.format_number(count)}** {display_name}")

# Format personnalisé
response_parts.append(f"✓ {display_name}: {self.format_number(count)}")
```

### Ajouter des emojis

```python
entity_emojis = {
    'ouvrage': '🏭',
    'point_eau': '💧',
    'equipement': '⚙️',
    'compteur_tete': '📊',
    # ...
}

response_parts.append(f"{entity_emojis[entity]} **{count}** {display_name}")
```

## 🔗 Intégration avec d'autres APIs

### Exemple : Ajouter support pour les graphiques

1. **Détecter la demande de graphique** :
```python
if any(word in message.lower() for word in ['graphique', 'chart', 'visualisation']):
    # Générer graphique
```

2. **Appeler l'API de graphique** :
```python
response = requests.get('http://localhost:8000/api/dashboard/ouvrages-par-annee/')
chart_data = response.json()
```

3. **Retourner les données dans metadata** :
```python
return {
    'content': response_text,
    'metadata': {
        'chart_data': chart_data,
        'chart_type': 'bar'
    },
    'success': True
}
```

## 📊 Métriques et monitoring

### Log des questions

Ajoutez du logging pour analyser les questions :

```python
logger.info(f"Question reçue: {message}")
logger.info(f"Entités détectées: {entities}")
logger.info(f"Filtres détectés: {filters}")
```

### Taux de succès

Suivez les réponses réussies vs échouées :

```python
if stats:
    logger.info(f"Réponse générée avec succès")
else:
    logger.warning(f"Échec de récupération des stats")
```

## 🚀 Prochaines évolutions possibles

1. **Support des graphiques** : Générer automatiquement des graphiques pour les réponses
2. **Historique** : "Évolution des ouvrages sur les 5 dernières années"
3. **Comparaisons** : "Comparer région Fitovinany vs région X"
4. **Prédictions** : "Estimation pour l'année prochaine"
5. **Alertes** : "Points d'eau coupés dans la dernière semaine"
6. **Export** : "Exporte moi ces statistiques en Excel"

## 📝 Checklist pour ajouter une nouvelle fonctionnalité

- [ ] Identifier le type de question (comptage, graphique, rapport, etc.)
- [ ] Créer les patterns de détection dans `StatsHandler`
- [ ] Mapper vers les APIs existantes ou créer de nouvelles APIs
- [ ] Ajouter des exemples dans `stats_examples.json`
- [ ] Tester avec différentes formulations
- [ ] Documenter les exemples de questions supportées
- [ ] Ajouter du logging pour le monitoring
- [ ] Mettre à jour ce guide

## 🆘 Dépannage

### Le chatbot ne détecte pas ma question

**Solution :** Vérifier que les mots-clés sont dans `count_patterns` ou `entity_mappings`

### Les filtres ne sont pas appliqués

**Solution :** Vérifier les patterns regex dans `filter_patterns`

### L'API retourne une erreur

**Solution :** Vérifier que l'URL et les paramètres sont corrects dans `get_dashboard_stats()`

### Les nombres ne sont pas formatés

**Solution :** Utiliser `self.format_number(count)` pour tous les nombres

## 📞 Support

Pour toute question sur l'entraînement du chatbot :
- Consulter `chatbot/training_data/stats_examples.json` pour les exemples
- Vérifier les logs dans la console Django
- Tester les APIs directement : `http://localhost:8000/api/dashboard/`

---

**Dernière mise à jour :** Octobre 2025
**Version :** 1.0
