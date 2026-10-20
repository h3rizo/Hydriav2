# Module Chatbot - Contexte Conversationnel

## Vue d'ensemble

Système de gestion du contexte conversationnel permettant au chatbot de mémoriser les questions précédentes et de répondre à des follow-ups sans répéter les informations.

## Problème résolu (26 décembre 2025)

### Avant

L'utilisateur devait répéter l'information dans chaque question :

```
User: "Combien de points d'eau à Ambato ?"
Bot: "💧 100 points d'eau"

User: "Donne moi les détails des points d'eau à Ambato par ouvrage"
Bot: [Détails]
```

**Problème** : L'utilisateur doit répéter "à Ambato" dans la 2ème question.

### Après

Le chatbot comprend maintenant les follow-ups :

```
User: "Combien de points d'eau à Ambato ?"
Bot: "💧 100 points d'eau"

User: "Tu peux me donner les détails de ce calcul ?"
Bot: [Détails par ouvrage pour Ambato]
```

**Avantage** : Conversation naturelle sans répétition.

## Architecture technique

### 1. Stockage du contexte

Le contexte est stocké dans un dictionnaire `session_context` passé entre les appels à `process_message()` :

```python
session_context = {
    'last_query': "Combien de points d'eau à Ambato",
    'last_result': {
        'success': True,
        'response': "...",
        'metadata': {
            'type': 'points_eau',
            'location': 'Ambato',
            'count': 100
        }
    },
    'last_type': 'geography'
}
```

### 2. Détection des follow-ups

**Fonction** : `_is_followup_details_request(message, session_context)`

**Conditions pour être un follow-up** :
1. ✅ Contexte de question précédente existe (`last_query`, `last_result`, `last_type`)
2. ✅ Message contient un mot-clé de follow-up
3. ❌ Message ne contient PAS de pattern de nouvelle question

**Mots-clés de follow-up** :
- `détail` / `detail` / `détails` / `details`
- `explique` / `explication`
- `calcul` / `comment`
- `par ouvrage` / `liste` / `tous`

**Patterns de nouvelle question (exclusion)** :
- `combien de points d'eau à` / `combien de points d'eau dans`
- `liste des points d'eau à` / `liste des points d'eau dans`
- `où se trouve`
- `dans quelle commune` / `dans quel district`

**Note importante** : Les patterns ont été affinés pour être plus spécifiques. Par exemple, "donne moi les détails" est accepté comme follow-up, car il ne contient pas "donne moi les points d'eau à [lieu]".

**Logique** :

```python
def _is_followup_details_request(message, session_context):
    # 1. Vérifier contexte
    has_context = (
        session_context.get('last_query') and
        session_context.get('last_result') and
        session_context.get('last_type') == 'geography'
    )

    if not has_context:
        return False

    # 2. Vérifier mots-clés follow-up
    has_followup_keyword = any(keyword in message_lower for keyword in followup_keywords)

    # Si pas de mot-clé de follow-up, ce n'est pas un follow-up
    if not has_followup_keyword:
        return False

    # 3. Vérifier absence de nouvelle question SPÉCIFIQUE (avec lieu)
    new_question_patterns = [
        'combien de points d\'eau à',
        'combien de points d\'eau dans',
        'liste des points d\'eau à',
        'liste des points d\'eau dans',
        'où se trouve',
        'dans quelle commune',
        'dans quel district'
    ]
    has_new_question = any(pattern in message_lower for pattern in new_question_patterns)

    # 4. Décision : follow-up si mot-clé présent ET pas de nouvelle question
    return has_followup_keyword and not has_new_question
```

### 3. Traitement des follow-ups

**Fonction** : `_handle_followup_details(session_context)`

**Workflow** :

1. **Récupérer le contexte** :
   ```python
   last_query = session_context.get('last_query', '')
   last_result = session_context.get('last_result', {})
   ```

2. **Cas 1 : Déjà détaillé**
   - Si `last_result.metadata.type == 'points_eau_details'`
   - Retourner la même réponse avec préfixe "Voici à nouveau les détails :"

3. **Cas 2 : Réponse simple sur points d'eau**
   - Si `last_result.metadata.type == 'points_eau'`
   - Ajouter " détail" à la question originale
   - Relancer `geography_queries.process_query(last_query + " détail")`
   - Mettre à jour le contexte avec la nouvelle réponse

4. **Cas 3 : Autre type de question**
   - Retourner message d'erreur : "Je ne peux pas fournir plus de détails..."

**Code** :

```python
async def _handle_followup_details(session_context):
    last_query = session_context.get('last_query', '')
    last_result = session_context.get('last_result', {})

    # Cas 1: Déjà détaillé
    if last_result.get('metadata', {}).get('type') == 'points_eau_details':
        return {
            'success': True,
            'response': "Voici à nouveau les détails :\n\n" + last_result.get('response', ''),
            'metadata': last_result.get('metadata', {})
        }

    # Cas 2: Réponse simple -> Ajouter détail
    if last_result.get('metadata', {}).get('type') == 'points_eau':
        detailed_query = last_query + " détail"
        result = await sync_to_async(self.geography_queries.process_query)(detailed_query)
        session_context['last_result'] = result
        return result

    # Cas 3: Erreur
    return {
        'success': False,
        'response': "Je ne peux pas fournir plus de détails...",
        'metadata': {}
    }
```

### 4. Mise à jour du contexte

Après chaque réponse géographique, le contexte est mis à jour :

```python
if self.geography_queries.can_handle(user_message):
    result = await sync_to_async(self.geography_queries.process_query)(user_message)

    # Stocker le contexte
    session_context['last_query'] = user_message
    session_context['last_result'] = result
    session_context['last_type'] = 'geography'

    return result
```

## Exemples d'utilisation

### Exemple 1 : Demande de détails classique

```
Q1: "Combien de points d'eau à Ambato"
R1: Type: points_eau | "💧 100 points d'eau"

Q2: "Tu peux me donner les détails de ce calcul?"
R2: Type: points_eau_details | Répartition par 14 ouvrages
```

**Détection** :
- Contexte : ✅ (last_query, last_result, last_type='geography')
- Mot-clé : ✅ ("détails")
- Nouvelle question : ❌ (pas de "combien", "liste des", etc.)
- **Résultat** : Follow-up détecté

### Exemple 2 : Variante avec "explique"

```
Q1: "Combien de points d'eau à Ambato"
R1: Type: points_eau | "💧 100 points d'eau"

Q2: "Explique moi comment tu arrives à ce résultat"
R2: Type: points_eau_details | Répartition par 14 ouvrages
```

### Exemple 3 : Variante avec "par ouvrage"

```
Q1: "Combien de points d'eau à Ambato"
R1: Type: points_eau | "💧 100 points d'eau"

Q2: "Par ouvrage stp"
R2: Type: points_eau_details | Répartition par 14 ouvrages
```

### Exemple 4 : Variante avec "donne moi les détails"

```
Q1: "Combien de points d'eau à Ambato"
R1: Type: points_eau | "💧 100 points d'eau"

Q2: "donne moi les détails par ouvrage"
R2: Type: points_eau_details | Répartition par 14 ouvrages
```

**Détection** :
- Contexte : ✅ (last_query, last_result, last_type='geography')
- Mot-clé : ✅ ("détails" + "par ouvrage")
- Nouvelle question : ❌ (pas de "combien de points d'eau à" avec lieu)
- **Résultat** : Follow-up détecté

**Note** : Bien que "donne moi" soit présent, ce n'est PAS considéré comme une nouvelle question car le pattern complet "combien de points d'eau à [lieu]" est absent.

### Exemple 5 : Nouvelle question (non follow-up)

```
Q1: "Combien de points d'eau à Ambato"
R1: Type: points_eau | "💧 100 points d'eau"

Q2: "Combien de points d'eau à Ankazomanga détail"
R2: Type: points_eau_details | Nouvelle requête (Ankazomanga)
```

**Détection** :
- Contexte : ✅
- Mot-clé : ✅ ("détail")
- Nouvelle question : ✅ ("combien")
- **Résultat** : NOUVELLE question (pas un follow-up)

## Intégration dans le code

### Fichier : `ai_assistant.py`

**Ligne 54-77** : Méthode `process_message()` modifiée

```python
async def process_message(self, user_message: str, session_context: Dict[str, Any] = None):
    # Initialiser contexte
    if session_context is None:
        session_context = {}

    # Vérifier si follow-up
    if self._is_followup_details_request(user_message, session_context):
        return await self._handle_followup_details(session_context)

    # Traiter normalement et stocker contexte
    if self.geography_queries.can_handle(user_message):
        result = await sync_to_async(self.geography_queries.process_query)(user_message)

        session_context['last_query'] = user_message
        session_context['last_result'] = result
        session_context['last_type'] = 'geography'

        return result
```

**Ligne 429-465** : Méthode `_is_followup_details_request()`

**Ligne 467-500** : Méthode `_handle_followup_details()`

## Tests de validation

### Script : `test_contexte_conversationnel.py`

**Scénarios testés** :

1. ✅ "Tu peux me donner les détails de ce calcul?" → Détails affichés
2. ✅ "Explique moi comment tu arrives à ce résultat" → Détails affichés
3. ✅ "Par ouvrage stp" → Détails affichés

**Résultats** :

```
[TEST] Scenario 1: Question simple puis demande de details
[Q1] Combien de points d'eau à Ambato
[OK] Success: True
[OK] Type: points_eau

[Q2] Tu peux me donner les détails de ce calcul?
[OK] Success: True
[OK] Type: points_eau_details
[OK] Nombre d'ouvrages: 14
```

## Points d'attention CRITICAL

### 1. Session context partagé

⚠️ Le `session_context` doit être partagé entre les appels à `process_message()`

**Bon code** :
```python
ai_assistant = AIAssistant()
session_context = {}

# Premier message
result1 = await ai_assistant.process_message("Combien de points d'eau à Ambato", session_context)

# Deuxième message (même contexte !)
result2 = await ai_assistant.process_message("Détails ?", session_context)
```

**Mauvais code** :
```python
# ❌ Nouveau contexte à chaque fois = perte de mémoire
result1 = await ai_assistant.process_message("Combien de points d'eau à Ambato", {})
result2 = await ai_assistant.process_message("Détails ?", {})  # Contexte vide !
```

### 2. Éviter accès DB synchrone dans détection

⚠️ Ne PAS utiliser `Commune.objects.all()` dans `_is_followup_details_request()`

**Raison** : `process_message()` est async, l'accès DB doit utiliser `sync_to_async()`

**Solution** : Utiliser des patterns de texte au lieu de requêtes DB

### 3. Limitation actuelle

⚠️ Le contexte ne fonctionne que pour les requêtes géographiques (`last_type='geography'`)

**Future amélioration** : Étendre aux requêtes infrastructure, statistiques, etc.

## Prochaines améliorations possibles

1. **Contexte multi-type** : Follow-up sur infrastructure, stats, etc.
2. **Historique complet** : Mémoriser les 5-10 dernières questions
3. **Références relatives** : "La commune précédente", "le même ouvrage"
4. **Clarification** : "Ambato ou Ankazomanga ?" si ambiguïté
5. **Persistance** : Sauvegarder contexte en base de données
6. **Timeout** : Expirer le contexte après X minutes d'inactivité

## Documentation liée

- `backend/docs/CHATBOT_GEOGRAPHY_QUERIES_DETAILS.md` - Détails par ouvrage
- `backend/chatbot/services/ai_assistant.py` - Code source
- `backend/test_contexte_conversationnel.py` - Tests
