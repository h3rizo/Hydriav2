# Améliorations Module Analytics - 26 décembre 2025

## Vue d'ensemble

Ce document résume les améliorations apportées au module de requêtes analytiques pour corriger les problèmes de détection et de traitement des requêtes complexes (tableaux, graphiques, classements).

## Problèmes identifiés et corrigés

### 1. Ordre de priorité des services (CRITICAL)

**Problème** : Les requêtes analytics étaient interceptées par le service de géographie avant d'atteindre le service analytics.

**Cause** : Dans `ai_assistant.py`, l'ordre de vérification était :
1. Geography queries
2. Infrastructure queries
3. **Analytics queries** ← Jamais atteints

**Solution** : Déplacer analytics_queries en PREMIÈRE priorité (ligne 69-79 de ai_assistant.py)

```python
# Vérifier en PRIORITÉ si c'est une demande analytique (tableaux, graphiques, évolutions)
# DOIT être avant geography_queries car plus spécifique
if self.analytics_queries.can_handle(user_message):
    result = await sync_to_async(self.analytics_queries.process_query)(user_message)
    # ... stockage contexte
    return result

# Vérifier si c'est une demande géographique (après analytics)
if self.geography_queries.can_handle(user_message):
    # ...
```

**Résultat** : ✅ Les requêtes analytics sont maintenant traitées en priorité

---

### 2. Champ population inexistant dans modèle Commune

**Problème** : `'Commune' object has no attribute 'population'`

**Code erroné** (ligne 258 de analytics_queries.py) :
```python
population = commune.population or 0  # ❌ Champ n'existe pas
```

**Solution** : Remplacer par comptage des villages

```python
# Compter les villages
nb_villages = self.Village.objects.filter(
    fokontany__commune=commune
).count()
```

**Résultat** : ✅ Tableau comparatif communes fonctionne

---

### 3. Nom de champ created_at vs createdat

**Problème** : `Cannot resolve keyword 'created_at' into field`

**Code erroné** (lignes 177, 189 de analytics_queries.py) :
```python
points_query = self.PointEau.objects.filter(
    created_at__isnull=False  # ❌ Champ s'appelle 'createdat'
)
evolution = points_query.annotate(
    annee=TruncYear('created_at')  # ❌
)
```

**Solution** : Utiliser le bon nom de champ

```python
points_query = self.PointEau.objects.filter(
    createdat__isnull=False  # ✅
)
evolution = points_query.annotate(
    annee=TruncYear('createdat')  # ✅
)
```

**Résultat** : ✅ Plus d'erreur de champ

**Note** : Aucune donnée retournée car les 3414 points d'eau n'ont pas de date createdat renseignée dans la base.

---

### 4. Détection "points d eau" sans apostrophe

**Problème** : Les requêtes "points d eau" (sans apostrophe) n'étaient pas détectées

**Code erroné** (ligne 348 de analytics_queries.py) :
```python
elif 'points d\'eau' in message_lower or 'point d\'eau' in message_lower:
    # Ne détecte que "points d'eau" avec apostrophe
```

**Solution** : Ajouter variantes sans apostrophe

```python
elif any(pattern in message_lower for pattern in [
    'points d\'eau', 'point d\'eau',
    'points d eau', 'point d eau'  # ✅ Sans apostrophe
]):
```

**Résultat** : ✅ Classement "Top 10 des communes par nombre de points d eau" fonctionne

---

### 5. Détection "evolution" sans accent

**Problème** : `can_handle()` ne détectait que "évolution" (avec accent), pas "evolution"

**Code erroné** (ligne 47 de analytics_queries.py) :
```python
graphique_keywords = [
    'graphique', 'courbe', 'évolution', 'tendance',  # ❌ Uniquement avec accent
    # ...
]
```

**Solution** : Ajouter variante sans accent

```python
graphique_keywords = [
    'graphique', 'courbe', 'évolution', 'evolution', 'tendance',  # ✅
    'progression', 'variation', 'historique'
]
```

**Résultat** : ✅ "Evolution du nombre de points d eau" détecté par analytics_queries

---

## Résultats des tests

### Tests réussis ✅

1. **Évolution consommation** : `"Montre moi l'évolution de la consommation d'eau par année"`
   - Type : `evolution_consommation`
   - Données : 7 années (2019-2025)
   - Graphique : 3 séries (total, moyenne, nb relevés)

2. **Tableau comparatif communes** : `"Tableau comparatif des communes"`
   - Type : `tableau_communes`
   - Données : 70 communes avec villages, points d'eau, ouvrages
   - Tri : Par nombre de points d'eau (décroissant)

3. **Classement Top 10** : `"Top 10 des communes par nombre de points d eau"`
   - Type : `classement_points_eau`
   - Données : 10 communes classées
   - Ex : Ankazondandy (298 PE), Vohilengo (255 PE), etc.

4. **Classement Top 5 consommation** : `"Top 5 des communes par consommation en 2024"`
   - Type : `classement_consommation`
   - Données : 5 communes avec consommation totale
   - Ex : Avaratsena (21,990 m³), Vohilengo (12,589 m³), etc.

5. **Évolution points d'eau** : `"Evolution du nombre de points d eau a Ambato"`
   - Type : `evolution_points_eau` ✅ (détection correcte)
   - Données : Aucune (createdat non renseigné dans BDD) ⚠️

### Tests non résolus 🚧

1. **Tableau ouvrages** : `"Liste des ouvrages à Ambato"`
   - Détecté comme : `aide_analytics` (pas de pattern spécifique "liste" + "ouvrage")
   - À améliorer : Ajouter "liste" comme mot-clé tableau

---

## Fichiers modifiés

1. **backend/chatbot/services/ai_assistant.py** (lignes 69-96)
   - Déplacement analytics_queries AVANT geography_queries
   - Commentaire explicatif sur l'ordre de priorité

2. **backend/chatbot/services/analytics_queries.py** (6 corrections)
   - Ligne 47 : Ajout "evolution" sans accent
   - Ligne 75 : Ajout patterns "points d eau" sans apostrophe
   - Lignes 177, 189 : Correction `created_at` → `createdat`
   - Lignes 257-267 : Remplacement population par nb_villages
   - Ligne 348 : Ajout patterns "points d eau" sans apostrophe

3. **backend/docs/CHATBOT_ANALYTICS_QUERIES_AMELIORATIONS.md** (ce fichier)
   - Documentation complète des corrections

---

## Prochaines améliorations suggérées

### Court terme

1. **Ajouter "liste" comme mot-clé tableau** pour détecter "Liste des ouvrages"
2. **Améliorer message quand pas de données** : Au lieu de tableau vide, dire "Aucune donnée disponible pour cette période"
3. **Ajouter variations** : "montrer", "afficher", "donner" comme synonymes de "liste"

### Moyen terme

1. **Évolution mensuelle** : Support de `TruncMonth` pour analyses plus fines
2. **Comparaisons** : "Compare Ambato et Ankazomanga" (2 communes)
3. **Filtres temporels** : "entre 2020 et 2023", "depuis 2022"
4. **Statistiques avancées** : Écart-type, médiane, quartiles

### Long terme

1. **Prévisions** : Tendances linéaires avec prédiction
2. **Export graphique** : Génération PNG/SVG côté serveur
3. **Dashboard dynamique** : HTML/JS complet pour dashboards
4. **Alertes** : Détection automatique d'anomalies dans évolutions

---

## Métriques de succès

**Avant corrections** :
- Évolution consommation : ✅
- Évolution points d'eau : ❌ (détecté comme géographie)
- Tableau communes : ❌ (erreur champ population)
- Classement Top 10 : ❌ (détecté comme géographie)
- Classement Top 5 : ❌ (détecté comme géographie)

**Après corrections** :
- Évolution consommation : ✅
- Évolution points d'eau : ✅ (détection correcte)
- Tableau communes : ✅
- Classement Top 10 : ✅
- Classement Top 5 : ✅

**Taux de réussite** : 5/5 (100%) pour détection + 4/5 (80%) pour données réelles

---

## Conclusion

Les requêtes analytiques complexes (tableaux, graphiques, évolutions, classements) fonctionnent maintenant correctement grâce aux corrections suivantes :

1. ✅ Ordre de priorité corrigé (analytics AVANT geography)
2. ✅ Champs modèles corrigés (population → nb_villages, created_at → createdat)
3. ✅ Détection améliorée (variations sans accent/apostrophe)
4. ✅ Tests validés pour 5 types de requêtes

**La base du système d'analytics est maintenant solide et prête pour des fonctionnalités avancées.**
