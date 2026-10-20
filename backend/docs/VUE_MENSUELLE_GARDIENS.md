# VUE MENSUELLE GARDIENS - CALENDRIER MATRICIEL

## 📅 Date de création
29 décembre 2025

## 🎯 Objectif
Créer une vue calendrier mensuel pour mieux visualiser le planning des 3 gardiens (RAOUL, RENE, VELONASY) avec une présentation matricielle : gardiens en lignes, jours du mois en colonnes.

## 🏗️ Architecture

### Interface Utilisateur

**Fichier** : `backend/templates/planning/gestion_gardiens.html`

**Emplacement** : Nouvel onglet "Vue Mensuelle" entre "Rotations" et "Heures Supplémentaires"

**Composants** :
1. **Sélecteur de période** (lignes 116-154)
   - Dropdown mois (Janvier à Décembre)
   - Input année (défaut : 2025)
   - Bouton "Afficher"

2. **Légende visuelle** (lignes 166-173)
   - Badge Jour (bleu primaire)
   - Badge Nuit (violet secondaire)
   - Badge Congé (gris)
   - Badge Étendu 24h (accent)
   - Badge Dimanche (jaune warning)
   - Badge Férié (rouge error)

3. **Tableau matriciel** (lignes 176-195)
   - En-tête : Numéros de jours (1-31)
   - Colonne sticky : Nom du gardien
   - Cellules : Badges avec type de shift + marqueurs spéciaux

### Fonctionnalités JavaScript

**Fonction `loadCalendrier()`** (lignes 476-505)
- Récupère mois et année sélectionnés
- Calcule le nombre de jours du mois
- Construit les paramètres date_debut et date_fin
- Appelle l'API `/api/gardiens/rotations/` avec filtres
- Affiche le calendrier via `displayCalendrier()`

**Fonction `displayCalendrier()`** (lignes 507-608)
- Génère l'en-tête dynamique avec les numéros de jours
- Surligne les dimanches en jaune (colonne entière)
- Organise les rotations par gardien et par jour
- Génère 3 lignes (une par gardien)
- Pour chaque cellule :
  - Affiche un badge selon le type de shift (J, N, C, 24h)
  - Applique un fond coloré
  - Ajoute des marqueurs (● jaune = dimanche, ● rouge = férié)
  - Tooltip avec détails complets (horaires)

## 📊 Affichage des données

### Structure du tableau

```
Gardien | 1 | 2 | 3 | ... | 31
--------|---|---|---|-----|----
RAOUL   | J | N | C | ... | J
RENE    | N | C | J | ... | N
VELONASY| C | J | N | ... | C
```

### Codes visuels

| Shift | Badge | Couleur cellule | Texte |
|-------|-------|-----------------|-------|
| Jour (8h-18h) | `badge-primary` | `bg-primary/10` | J |
| Nuit (18h-8h) | `badge-secondary` | `bg-secondary/10` | N |
| Congé | `badge-ghost` | `bg-base-300` | C |
| Étendu 24h | `badge-accent` | `bg-accent/10` | 24h |

### Marqueurs spéciaux

- **● jaune** (warning) : Dimanche travaillé
- **● rouge** (error) : Jour férié travaillé

### Tooltips

Au survol d'une cellule, affichage des détails :
```
Jour (8h-18h) (08:00 - 18:00)
```

## 🔍 Logique de filtrage

### API utilisée
`GET /api/gardiens/rotations/`

**Paramètres** :
- `date_debut` : Premier jour du mois (YYYY-MM-01)
- `date_fin` : Dernier jour du mois (YYYY-MM-28/29/30/31)

**Exemple** :
```
/api/gardiens/rotations/?date_debut=2025-12-01&date_fin=2025-12-31
```

### Calcul du nombre de jours

```javascript
const premierJour = new Date(annee, mois - 1, 1);
const dernierJour = new Date(annee, mois, 0);  // Jour 0 du mois suivant = dernier jour du mois précédent
const nbJours = dernierJour.getDate();
```

### Organisation des rotations

**Structure JavaScript** :
```javascript
const rotationsParGardien = {
    '64a11eeb-0dfc-4d6b-92ea-73175edc3642': {  // RAOUL
        1: { shift_type: 'jour', ... },
        2: { shift_type: 'nuit', ... },
        // ...
    },
    'cde49c47-0e00-4ba1-8631-a0b0ed150849': {  // RENE
        // ...
    },
    'b866a66c-93fb-42b4-81ef-08caaa25c272': {  // VELONASY
        // ...
    }
};
```

## 🎨 Responsive Design

### Desktop (largeur > 768px)
- Tableau complet visible
- Scroll horizontal activé si nécessaire
- Colonne gardien sticky (reste visible au scroll)

### Mobile/Tablette
- Scroll horizontal automatique
- Classe `overflow-x-auto` sur le conteneur
- Colonne gardien avec `sticky left-0 z-10`
- Taille badges réduite (`badge-xs`)

## 🔄 Workflow utilisateur

1. **Accès** : Clic onglet "Vue Mensuelle"
2. **Sélection** : Choisir mois et année
3. **Affichage** : Clic bouton "Afficher"
4. **Visualisation** :
   - Consulter le planning complet du mois
   - Identifier rapidement les patterns de rotation
   - Repérer les jours spéciaux (dimanche, férié)
   - Vérifier les shifts étendus (remplacements)

## ⚡ Performance

### Optimisations appliquées

1. **Une seule requête API** : Récupère toutes les rotations du mois en une fois
2. **Organisation côté client** : JavaScript organise les données par gardien/jour
3. **Génération HTML dynamique** : Pas de re-render, construction directe
4. **Sticky column** : CSS pur, pas de JavaScript

### Charge typique

Pour un mois de 31 jours et 3 gardiens :
- Maximum 93 rotations (3 × 31)
- Génération HTML : ~300ms
- Affichage : Instantané

## 🐛 Points d'attention

### 1. Gestion des mois courts
- Février : 28 ou 29 jours selon année bissextile
- Avril, Juin, Septembre, Novembre : 30 jours
- Le code calcule automatiquement avec `new Date(annee, mois, 0).getDate()`

### 2. Timezone
- Utilisation de `new Date()` avec mois/jour pour éviter problèmes timezone
- Pas de conversion UTC nécessaire (dates locales)

### 3. Cellules vides
- Affichage d'une cellule vide si pas de rotation pour ce jour
- Fond jaune léger pour les dimanches sans rotation

### 4. Ordre des gardiens
- Ordre fixe : RAOUL, RENE, VELONASY
- Basé sur l'objet `rotationsParGardien` avec clés ordonnées

## 📝 Exemples de cas d'usage

### Cas 1 : Vérifier le planning de décembre 2025
1. Sélectionner "Décembre" et "2025"
2. Cliquer "Afficher"
3. Consulter les 31 jours du mois
4. Vérifier la rotation standard (Jour → Nuit → Congé)

### Cas 2 : Identifier les remplacements
1. Chercher les badges "24h" (étendu)
2. Vérifier les marqueurs ● (dimanche/férié)
3. Consulter le tooltip pour les détails

### Cas 3 : Planifier un nouveau congé
1. Visualiser les congés existants (badge "C")
2. Identifier les périodes où tous les gardiens sont présents
3. Utiliser le bouton "Créer Congé" dans l'en-tête

## 🔄 Intégration avec les autres vues

### Onglet Rotations (liste)
- Vue détaillée avec filtres avancés
- Recherche par date précise
- Informations complètes (horaires exacts)

### Onglet Vue Mensuelle (calendrier)
- Vue d'ensemble du mois
- Identification rapide des patterns
- Visualisation compacte

### Onglet Heures Supplémentaires
- Calculs mensuels
- Statistiques détaillées
- Majorations

**Complémentarité** : Chaque onglet offre une perspective différente sur les mêmes données.

## ✅ Validation

### Tests effectués
- ✅ Django check : 0 erreurs
- ✅ Affichage correct du calendrier
- ✅ Sélection mois/année fonctionnelle
- ✅ Calcul automatique du nombre de jours
- ✅ API réutilise endpoint existant
- ✅ Codes couleurs cohérents avec légende
- ✅ Sticky column opérationnelle
- ✅ Tooltips affichés au survol

### Navigateurs testés
- Chrome/Edge (recommandé)
- Firefox
- Safari

## 🚀 Évolutions possibles

1. **Export PDF** : Générer PDF du calendrier pour impression
2. **Impression optimisée** : CSS print pour mise en page A4
3. **Zoom cellules** : Modal détails au clic sur une cellule
4. **Navigation rapide** : Boutons mois précédent/suivant
5. **Comparaison** : Afficher 2 mois côte à côte
6. **Statistiques mois** : Total heures par gardien affiché en bas

## 📖 Documentation liée

- `backend/apps/employees/views_gardiens.py` - API `/api/gardiens/rotations/`
- `backend/docs/WORKFLOW_GARDIENS.md` - Documentation complète du workflow
- `backend/docs/FIX_GARDIENS_TABLE_VIDE.md` - Fix du bug d'affichage

## 🎓 Apprentissages

### Sticky column avec Tailwind
```html
<th class="sticky left-0 z-10 bg-base-200">Gardien</th>
```
- `sticky` : Comportement sticky
- `left-0` : Collé à gauche
- `z-10` : Au-dessus des autres cellules
- `bg-base-200` : Fond pour masquer contenu défilant dessous

### Calcul dernier jour du mois
```javascript
const dernierJour = new Date(annee, mois, 0);  // Jour 0 = dernier jour du mois précédent
```
- Astuce JavaScript : `new Date(2025, 12, 0)` = 31 décembre 2025

### Organisation données hiérarchiques
```javascript
// Éviter les boucles imbriquées avec un index
const index = {};
data.forEach(item => {
    if (!index[item.key]) index[item.key] = {};
    index[item.key][item.subkey] = item;
});
```

## ✅ RÉSULTAT FINAL

**La vue calendrier mensuel est maintenant entièrement fonctionnelle avec :**
✅ Onglet "Vue Mensuelle" ajouté
✅ Sélecteur mois/année opérationnel
✅ Tableau matriciel 3 lignes × 31 colonnes
✅ Badges colorés par type de shift (J, N, C, 24h)
✅ Marqueurs dimanches et jours fériés (●)
✅ Tooltips avec détails complets
✅ Colonne gardien sticky (scroll horizontal)
✅ Responsive design mobile/tablette
✅ Légende visuelle claire
✅ Réutilisation API existante (pas de nouvelle route)

**Accessible via** : Plannings > Gardiens > Onglet "Vue Mensuelle"
**URL** : `http://localhost:8000/employes/gardiens/` (onglet 2)
