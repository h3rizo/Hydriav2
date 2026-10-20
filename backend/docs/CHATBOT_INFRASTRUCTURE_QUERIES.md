# Module Chatbot - Requêtes sur les Infrastructures

## Vue d'ensemble

Le module `InfrastructureQueries` permet au chatbot de répondre à des questions complexes sur les infrastructures (ouvrages, équipements, points d'eau) et leurs relations.

## Architecture

### Relations entre modèles

```
Ouvrage
  ├── EquipementConstitutif (via foreign key equipement → ouvrage)
  ├── PointEau (via foreign key pointeau → ouvrage)
  └── CompteurTete (via foreign key compteur → ouvrage)
```

### Fichiers créés

1. **`backend/chatbot/services/infrastructure_queries.py`** (652 lignes)
   - Service principal pour gérer les requêtes sur les infrastructures
   - 8 handler methods pour différents types de questions
   - Détection automatique via `can_handle()`

2. **`backend/chatbot/services/ai_assistant.py`** (modifié)
   - Import de `InfrastructureQueries`
   - Initialisation dans `__init__()`
   - Routing dans `process_message()` en 2ème position (après geography)

## Types de requêtes supportées

### 1. Liste des types d'ouvrages

**Questions** :
- "Quels sont les types d'ouvrages disponibles?"
- "Liste les types d'ouvrages"

**Réponse** : Liste de 17 types d'ouvrages (AEPG, FPMH, PMH, etc.)

**Exemple de retour** :
```json
{
  "success": true,
  "response": "**Types d'ouvrages disponibles :**\n\n📊 Total : **17** types\n\n**Liste :**\n  • AEPG\n  • FPMH\n  • PMH\n  • ...",
  "metadata": {
    "type": "types_ouvrages",
    "count": 17
  }
}
```

### 2. Liste des types d'équipements

**Questions** :
- "Quels sont les types d'équipements?"
- "Liste des types d'équipements"

**Réponse** : Liste de 14 types d'équipements (Captage, Adduction, Distribution, etc.)

**Exemple de retour** :
```json
{
  "success": true,
  "response": "**Types d'équipements disponibles :**\n\n📊 Total : **14** types\n\n**Liste :**\n  • Captage\n  • Adduction\n  • Distribution\n  • ...",
  "metadata": {
    "type": "types_equipements",
    "count": 14
  }
}
```

### 3. Liste des types de points d'eau

**Questions** :
- "Liste les types de points d'eau"
- "Quels sont les types de points d'eau?"

**Réponse** : Liste de 10 types de points d'eau (BF, BI, BP, Kiosque, PMH, etc.)

**Exemple de retour** :
```json
{
  "success": true,
  "response": "**Types de points d'eau disponibles :**\n\n📊 Total : **10** types\n\n**Liste :**\n  • BF\n  • BI\n  • BP\n  • Kiosque\n  • PMH\n  • ...",
  "metadata": {
    "type": "types_points_eau",
    "count": 10
  }
}
```

### 4. Ouvrages avec compteurs de tête

**Questions** :
- "Quels ouvrages ont un compteur de tête?"
- "Liste des ouvrages avec compteur"

**Réponse** : Liste des 6 ouvrages équipés d'un compteur de tête

**Exemple de retour** :
```json
{
  "success": true,
  "response": "**Ouvrages avec compteur de tête :**\n\n📊 Total : **6** ouvrages\n\n**Liste :**\n  • Ambato (AEPG)\n  • Ankazondandy (AEPG)\n  • ...",
  "metadata": {
    "type": "ouvrages_compteur",
    "count": 6
  }
}
```

### 5. Équipements d'un ouvrage

**Questions** :
- "Quels sont les équipements de l'ouvrage [Nom] ?"
- "Liste des équipements de l'ouvrage [Nom]"

**Réponse** : Liste des équipements groupés par type

### 6. Points d'eau d'un ouvrage

**Questions** :
- "Quels sont les points d'eau de l'ouvrage [Nom] ?"
- "Liste des points d'eau de l'ouvrage [Nom]"

**Réponse** : Liste des points d'eau groupés par type

### 7. Type d'un ouvrage

**Questions** :
- "Quel est le type de l'ouvrage [Nom] ?"

**Réponse** : Le type de l'ouvrage spécifique

### 8. Modalité de gestion d'un ouvrage

**Questions** :
- "Quelle est la modalité de gestion de l'ouvrage [Nom] ?"

**Réponse** : Modalité de gestion active (gestionnaire, tarif)

## Logique de détection (can_handle)

### Priorités de détection

1. **Requêtes sur les types** (haute priorité) :
   - Contient "type" ET ("liste" OU "tous" OU "toutes" OU "quels")
   - Ex: "Liste les types de points d'eau"

2. **Mots-clés d'infrastructure** :
   - équipement, compteur, modalité, gestion, tarif
   - type ouvrage, type point, type équipement

3. **Ouvrage + infrastructure** :
   - Mentionne "ouvrage" ET ("type" OU "équipement")

### Code de détection

```python
def can_handle(self, user_message: str) -> bool:
    message_lower = user_message.lower()

    # Requêtes sur les types (haute priorité)
    is_types_query = (
        'type' in message_lower and
        ('liste' in message_lower or 'tous' in message_lower or
         'toutes' in message_lower or 'quels' in message_lower)
    )

    # Mots-clés d'infrastructure
    infra_keywords = [
        'équipement', 'equipement', 'compteur', 'modalité', 'modalite',
        'gestion', 'tarif', 'type ouvrage', 'type point', 'type équipement'
    ]
    has_infra_keyword = any(keyword in message_lower for keyword in infra_keywords)

    # Combinaisons
    has_ouvrage_ref = 'ouvrage' in message_lower
    return (is_types_query or has_infra_keyword or
            (has_ouvrage_ref and ('type' in message_lower or
                                  'équipement' in message_lower or
                                  'equipement' in message_lower)))
```

## Routage des requêtes (process_query)

### Ordre de priorité

1. **Types** (haute priorité - ligne 61)
   - "type" ET ("liste" OU "tous" OU "toutes" OU "quels")
   → `_handle_types_query()`

2. **Équipements + ouvrage** (ligne 65)
   - "équipement" ET "ouvrage"
   → `_handle_equipements_ouvrage_query()`

3. **Points d'eau + ouvrage** (ligne 69)
   - "point" ET "eau" ET "ouvrage"
   → `_handle_points_eau_ouvrage_query()`

4. **Type + ouvrage** (ligne 73)
   - "type" ET "ouvrage"
   - Si nom d'ouvrage détecté → `_handle_type_ouvrage_query()`
   - Sinon → `_handle_types_query()`

5. **Compteur de tête** (ligne 83)
   - "compteur" ET ("tête" OU "tete")
   → `_handle_ouvrages_compteur_query()`

6. **Modalité + ouvrage** (ligne 87)
   - ("modalité" OU "modalite") ET "ouvrage"
   → `_handle_modalite_ouvrage_query()`

7. **Requête générale** (ligne 92)
   → `_handle_general_infra_query()` (affiche aide)

## Extraction du nom d'ouvrage

### Patterns regex utilisés

```python
patterns = [
    r'ouvrage\s+([A-Z][a-zéèêàâôùûïëA-Z0-9\s-]+)',
    r'de\s+l\'ouvrage\s+([A-Z][a-zéèêàâôùûïëA-Z0-9\s-]+)',
    r'pour\s+l\'ouvrage\s+([A-Z][a-zéèêàâôùûïëA-Z0-9\s-]+)',
]
```

### Exemples de questions acceptées

- "Quels sont les équipements de l'ouvrage Ambanja FPMH ?"
- "Quel est le type de l'ouvrage Ankazondandy ?"
- "Points d'eau pour l'ouvrage Vohilengo AEPG"

## Correction des noms de champs

### Problème initial

Les modèles `TypeEquipement` et `TypePointEau` utilisent le champ `nom_type` et NON `nom_type_equipement` ou `nom_type_point_eau`.

### Correction appliquée

**AVANT (erreur)** :
```python
types = self.TypeEquipement.objects.all().order_by('nom_type_equipement')
types_list = "\n".join([f"  • {t.nom_type_equipement}" for t in types])
```

**APRÈS (correct)** :
```python
types = self.TypeEquipement.objects.all().order_by('nom_type')
types_list = "\n".join([f"  • {t.nom_type}" for t in types])
```

## Tests effectués

### Script de test

**Fichier** : `backend/test_infrastructure_query.py`

**Questions testées** :
1. ✅ "Quels sont les types d'ouvrages disponibles?" → 17 types retournés
2. ✅ "Liste les types de points d'eau" → 10 types retournés
3. ✅ "Quels sont les types d'équipements?" → 14 types retournés
4. ✅ "Quels ouvrages ont un compteur de tête?" → 6 ouvrages retournés

### Résultats JSON

Tous les fichiers de test se trouvent dans `backend/test_result_infra_*.json`

## Intégration dans AIAssistant

### Modifications apportées

**Fichier** : `backend/chatbot/services/ai_assistant.py`

**1. Import** (ligne 16) :
```python
from .infrastructure_queries import InfrastructureQueries
```

**2. Initialisation** (ligne 32) :
```python
def __init__(self):
    # ... autres services
    self.infrastructure_queries = InfrastructureQueries()
```

**3. Routing** (lignes 64-67) :
```python
async def process_message(self, user_message: str, session_context: Dict[str, Any] = None):
    # Après geography_queries
    if self.infrastructure_queries.can_handle(user_message):
        return await sync_to_async(self.infrastructure_queries.process_query)(user_message)
```

## Ordre de priorité des services

1. **GeographyQueries** (ligne 59-62)
2. **InfrastructureQueries** (ligne 64-67) ← NOUVEAU
3. **StatsHandler** (ligne 69-71)
4. **Intent analysis** (ligne 73+)

## Prochaines améliorations possibles

1. **Requêtes combinées** : Ex: "Combien de points d'eau de type BF sont sur des ouvrages AEPG?"
2. **Filtres géographiques** : Ex: "Quels sont les ouvrages AEPG dans la commune d'Ambanja?"
3. **Statistiques avancées** : Ex: "Moyenne d'équipements par ouvrage"
4. **Recherche par caractéristiques** : Ex: "Ouvrages avec plus de 5 points d'eau"
5. **Historique et évolution** : Ex: "Combien d'ouvrages créés cette année?"

## Points d'attention

### 1. Extraction du nom d'ouvrage

⚠️ Le nom de l'ouvrage DOIT commencer par une majuscule pour être détecté par le regex.

### 2. Champs des modèles

⚠️ Toujours vérifier les vrais noms de champs dans les modèles Django avant d'utiliser `order_by()` ou `values()`.

### 3. Routage

⚠️ L'ordre des conditions dans `process_query()` est CRITIQUE. Les requêtes plus spécifiques doivent être en premier.

### 4. can_handle()

⚠️ La fonction `can_handle()` doit être suffisamment large pour capturer toutes les requêtes pertinentes, mais pas trop pour éviter les faux positifs.

## Documentation liée

- `backend/docs/CHATBOT_GEOGRAPHY_QUERIES.md` - Requêtes géographiques
- `backend/chatbot/services/geography_queries.py` - Service géographique (pattern de référence)
- `backend/apps/organization/models.py` - Modèle Ouvrage
- `backend/apps/infrastructure/models.py` - Modèles EquipementConstitutif, TypeEquipement
- `backend/apps/billing/models.py` - Modèles PointEau, TypePointEau, CompteurTete
