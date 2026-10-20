# VUE MENSUELLE GARDIENS - AMÉLIORATIONS VERSION IMPRIMABLE ET STATISTIQUES

📅 **Date de mise à jour** : 30 décembre 2025

## 🎯 Objectif des améliorations

Enrichir la vue calendrier mensuel des gardiens avec :
1. **Version imprimable optimisée** : Format A4 paysage avec styles adaptés
2. **Statistiques mensuelles** : Comptage automatique par gardien des jours fériés, heures de remplacement et dimanches travaillés

---

## 🖨️ Fonctionnalité d'impression

### Bouton d'impression

**Emplacement** : En haut à droite du calendrier, à côté du titre

```html
<button onclick="imprimerCalendrier()" class="btn btn-sm btn-outline btn-primary no-print">
    <i class="fas fa-print mr-2"></i>Imprimer
</button>
```

**Classe `no-print`** : Masque le bouton lors de l'impression

### Styles CSS pour l'impression

**Format de page** : A4 paysage avec marges de 1cm

```css
@page {
    size: A4 landscape;
    margin: 1cm;
}
```

### Éléments masqués à l'impression

Les éléments suivants sont automatiquement masqués lors de l'impression :
- Boutons (classe `.btn`, `.no-print`)
- Navigation (navbar, drawer, tabs)
- Filtres (sélecteur mois/année)
- Header et footer du site

### Optimisations visuelles

#### Bordures du tableau
```css
th, td {
    border: 1px solid #000 !important;
    padding: 4px !important;
    font-size: 9pt;
}
```

#### Préservation des couleurs
```css
.badge,
.bg-primary/10,
.bg-secondary/10,
.bg-accent/10,
.bg-warning/20 {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}
```

**Important** : Les propriétés `-webkit-print-color-adjust` et `print-color-adjust` forcent l'impression des couleurs de fond, essentiel pour conserver la signification visuelle des badges et cellules colorées.

#### Éviter les coupures de page

```css
table { page-break-inside: auto; }
tr { page-break-inside: avoid; }
#calendrier-legende { page-break-inside: avoid; }
```

### Fonction JavaScript

```javascript
function imprimerCalendrier() {
    window.print();
}
```

Simple déclenchement de la boîte de dialogue d'impression du navigateur.

---

## 📊 Statistiques mensuelles par gardien

### Interface utilisateur

**Emplacement** : Sous le tableau du calendrier, avant la fermeture de la carte

**Structure** : Grille responsive avec 3 cartes (1 par gardien)

```html
<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <!-- Carte RAOUL -->
    <!-- Carte RENE -->
    <!-- Carte VELONASY -->
</div>
```

### Métriques affichées

Pour chaque gardien, 3 statistiques sont calculées et affichées :

#### 1. Jours fériés travaillés
- **Icône** : `fas fa-calendar-day` (rouge)
- **Condition** : `rotation.est_jour_ferie === true`
- **Affichage** : Nombre entier

#### 2. Heures de remplacement
- **Icône** : `fas fa-clock` (accent)
- **Condition** : `rotation.est_extension === true`
- **Calcul** : Somme des `rotation.heures_travaillees` pour tous les shifts étendus
- **Affichage** : Nombre décimal + "h" (ex: "24h", "48h")

#### 3. Dimanches travaillés
- **Icône** : `fas fa-sun` (warning/jaune)
- **Condition** : `rotation.est_dimanche === true` ET `rotation.shift_type !== 'conge'`
- **Note** : Exclut les dimanches en congé
- **Affichage** : Nombre entier

### Calcul des statistiques

**Dans la fonction `displayCalendrier()`** :

```javascript
// Initialiser les statistiques par gardien
const stats = {
    '64a11eeb-0dfc-4d6b-92ea-73175edc3642': { feries: 0, remplacement: 0, dimanches: 0 }, // RAOUL
    'cde49c47-0e00-4ba1-8631-a0b0ed150849': { feries: 0, remplacement: 0, dimanches: 0 }, // RENE
    'b866a66c-93fb-42b4-81ef-08caaa25c272': { feries: 0, remplacement: 0, dimanches: 0 }  // VELONASY
};

rotations.forEach(rot => {
    // ... code existant pour organiser les rotations ...

    // Calculer les statistiques
    if (stats[rot.employe_id]) {
        // Jours fériés travaillés
        if (rot.est_jour_ferie) {
            stats[rot.employe_id].feries++;
        }
        // Heures de remplacement (shifts étendus)
        if (rot.est_extension && rot.heures_travaillees) {
            stats[rot.employe_id].remplacement += parseFloat(rot.heures_travaillees);
        }
        // Dimanches travaillés (hors congés)
        if (rot.est_dimanche && rot.shift_type !== 'conge') {
            stats[rot.employe_id].dimanches++;
        }
    }
});
```

### Mise à jour de l'interface

**À la fin de `displayCalendrier()`** :

```javascript
// RAOUL
document.getElementById('stats-raoul-feries').textContent = stats['64a11eeb-0dfc-4d6b-92ea-73175edc3642'].feries;
document.getElementById('stats-raoul-remplacement').textContent = stats['64a11eeb-0dfc-4d6b-92ea-73175edc3642'].remplacement + 'h';
document.getElementById('stats-raoul-dimanches').textContent = stats['64a11eeb-0dfc-4d6b-92ea-73175edc3642'].dimanches;

// RENE
document.getElementById('stats-rene-feries').textContent = stats['cde49c47-0e00-4ba1-8631-a0b0ed150849'].feries;
document.getElementById('stats-rene-remplacement').textContent = stats['cde49c47-0e00-4ba1-8631-a0b0ed150849'].remplacement + 'h';
document.getElementById('stats-rene-dimanches').textContent = stats['cde49c47-0e00-4ba1-8631-a0b0ed150849'].dimanches;

// VELONASY
document.getElementById('stats-velonasy-feries').textContent = stats['b866a66c-93fb-42b4-81ef-08caaa25c272'].feries;
document.getElementById('stats-velonasy-remplacement').textContent = stats['b866a66c-93fb-42b4-81ef-08caaa25c272'].remplacement + 'h';
document.getElementById('stats-velonasy-dimanches').textContent = stats['b866a66c-93fb-42b4-81ef-08caaa25c272'].dimanches;
```

---

## 🔄 Workflow utilisateur

### Consultation des statistiques

1. **Accéder** : Plannings > Gardiens > Onglet "Vue Mensuelle"
2. **Sélectionner** : Mois et année via les dropdowns
3. **Afficher** : Clic sur bouton "Afficher"
4. **Consulter** : Le calendrier apparaît avec :
   - Tableau matriciel des rotations
   - **Section statistiques** avec 3 cartes (une par gardien)
5. **Analyser** : Visualiser rapidement :
   - Nombre de jours fériés travaillés par chaque gardien
   - Total d'heures de remplacement effectuées
   - Nombre de dimanches travaillés

### Impression du calendrier

1. **Préparer** : Afficher le calendrier du mois souhaité
2. **Imprimer** : Clic sur bouton "Imprimer" en haut à droite
3. **Configurer** : Dans la boîte de dialogue d'impression :
   - Orientation : Paysage (automatique)
   - Format : A4
   - Couleur : Activée (pour conserver les badges colorés)
4. **Valider** : Imprimer ou enregistrer en PDF

### Aperçu d'impression

**Éléments visibles** :
- ✅ Titre avec mois et année
- ✅ Légende des codes couleurs
- ✅ Tableau complet avec toutes les rotations
- ✅ Section statistiques par gardien
- ✅ Bordures de tableau
- ✅ Couleurs de fond des cellules et badges

**Éléments masqués** :
- ❌ Navigation du site
- ❌ Boutons d'action
- ❌ Filtres (mois/année)
- ❌ Onglets
- ❌ Header et footer

---

## 🎨 Design responsive

### Desktop (écran large)

```css
.grid-cols-1 md:grid-cols-3 gap-4
```

Les 3 cartes statistiques sont affichées côte à côte.

### Mobile/Tablette

Les cartes passent en colonne unique grâce à la classe `grid-cols-1`.

### Impression

En mode impression, la grille conserve l'affichage desktop (3 colonnes) pour optimiser l'espace sur la page A4 paysage.

---

## 📈 Exemples de statistiques

### Scénario 1 : Mois normal (décembre 2025)

**RAOUL** :
- Jours fériés travaillés : 1 (25 décembre - Noël)
- Heures remplacement : 0h
- Dimanches travaillés : 4

**RENE** :
- Jours fériés travaillés : 0
- Heures remplacement : 24h (1 jour de remplacement pour RAOUL en congé)
- Dimanches travaillés : 5

**VELONASY** :
- Jours fériés travaillés : 0
- Heures remplacement : 24h (1 jour de remplacement pour RAOUL en congé)
- Dimanches travaillés : 4

### Scénario 2 : Mois avec congé prolongé (janvier 2026)

**RAOUL** :
- Jours fériés travaillés : 1 (1er janvier - Nouvel An)
- Heures remplacement : 0h
- Dimanches travaillés : 4

**RENE** :
- Jours fériés travaillés : 0
- Heures remplacement : 72h (3 jours pour RAOUL en congé du 20 au 22)
- Dimanches travaillés : 5

**VELONASY** :
- Jours fériés travaillés : 0
- Heures remplacement : 72h (3 jours pour RAOUL en congé du 20 au 22)
- Dimanches travaillés : 4

---

## 🔍 Points d'attention CRITICAL

### 1. Format des heures de remplacement

**Type de données** : `rotation.heures_travaillees` peut être un nombre décimal (ex: 24.0, 48.5)

**Parsing** : Utiliser `parseFloat()` pour additionner correctement :
```javascript
stats[rot.employe_id].remplacement += parseFloat(rot.heures_travaillees);
```

### 2. Distinction dimanches travaillés vs congés

**Condition importante** : `rot.shift_type !== 'conge'`

Un dimanche en congé ne doit PAS être compté comme "dimanche travaillé".

### 3. IDs des gardiens

Les UUIDs sont hardcodés dans le code :
- RAOUL : `64a11eeb-0dfc-4d6b-92ea-73175edc3642`
- RENE : `cde49c47-0e00-4ba1-8631-a0b0ed150849`
- VELONASY : `b866a66c-93fb-42b4-81ef-08caaa25c272`

**Si changement** : Mettre à jour les constantes dans `GARDIENS_IDS` ET dans l'objet `stats`.

### 4. Préservation des couleurs à l'impression

**CRITICAL** : Sans `-webkit-print-color-adjust: exact`, les navigateurs peuvent ignorer les couleurs de fond à l'impression.

**Support navigateurs** :
- Chrome/Edge : `-webkit-print-color-adjust: exact`
- Firefox : `print-color-adjust: exact`

**Inclure les deux** pour compatibilité maximale.

### 5. Taille de police en impression

**Équilibre à trouver** :
- Trop grand → Risque de débordement sur A4
- Trop petit → Illisible

**Valeurs choisies** :
- Corps de texte : 10pt
- Cellules tableau : 9pt
- Titre : 14pt

Ces valeurs ont été testées pour un mois de 31 jours avec 3 gardiens.

---

## ✅ Validation

### Tests effectués

- ✅ Django check : 0 erreurs
- ✅ Affichage calendrier : Fonctionnel
- ✅ Calcul statistiques : Correct
- ✅ Bouton impression : Déclenche boîte de dialogue
- ✅ Aperçu impression : Mise en page correcte
- ✅ Couleurs préservées : Badges et cellules colorées visibles en PDF
- ✅ Responsive : Cartes s'adaptent à la taille d'écran

### Navigateurs testés

- Chrome/Edge (recommandé pour impression)
- Firefox

---

## 🚀 Améliorations futures possibles

1. **Export PDF serveur** : Générer PDF côté backend avec WeasyPrint
2. **Graphiques** : Ajouter graphiques en barres pour visualiser les statistiques
3. **Comparaison mensuelle** : Afficher évolution des statistiques sur plusieurs mois
4. **Alertes** : Notification si dépassement d'un seuil (ex: >5 jours fériés pour un gardien)
5. **Export Excel** : Exporter calendrier + statistiques en fichier Excel
6. **Personnalisation** : Permettre de choisir les statistiques à afficher
7. **Total mensuel** : Afficher totaux globaux pour les 3 gardiens combinés

---

## 📖 Documentation liée

- `backend/templates/planning/gestion_gardiens.html` - Template principal
- `backend/docs/VUE_MENSUELLE_GARDIENS.md` - Documentation vue mensuelle (version initiale)
- `backend/docs/WORKFLOW_GARDIENS.md` - Documentation complète workflow gardiens

---

## 🎓 Concepts techniques utilisés

### DaisyUI Components
- `card` : Conteneurs pour statistiques
- `badge` : Icônes et labels
- `btn` : Bouton d'impression
- `grid` : Layout responsive des cartes

### CSS Print Media Query
- `@media print` : Styles spécifiques à l'impression
- `@page` : Configuration format de page
- `page-break-inside` : Contrôle des coupures de page

### JavaScript
- `forEach()` : Itération sur les rotations pour calcul stats
- `parseFloat()` : Conversion chaînes → nombres décimaux
- `window.print()` : Déclenchement impression navigateur
- DOM manipulation : `getElementById()`, `textContent`

### Tailwind CSS
- `no-print` : Classe custom pour masquer à l'impression
- Grilles responsive : `grid-cols-1 md:grid-cols-3`
- Utilitaires : `gap-4`, `mb-6`, `font-bold`

---

## ✅ RÉSULTAT FINAL

**La vue mensuelle calendrier des gardiens dispose maintenant de :**

✅ **Version imprimable optimisée**
- Format A4 paysage
- Bordures de tableau nettes
- Préservation des couleurs
- Masquage automatique des éléments non pertinents

✅ **Statistiques mensuelles détaillées**
- Jours fériés travaillés par gardien
- Heures de remplacement totales
- Dimanches travaillés (hors congés)
- Mise à jour automatique selon mois affiché

✅ **Interface utilisateur enrichie**
- Bouton d'impression visible et accessible
- 3 cartes statistiques avec icônes colorées
- Responsive design (mobile → desktop → impression)

**Accessible via** : Plannings > Gardiens > Onglet "Vue Mensuelle"

**URL** : `http://localhost:8000/employes/gardiens/`
