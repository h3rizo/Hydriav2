# Page d'accueil Application Launcher - Documentation

## Vue d'ensemble

La page d'accueil Application Launcher présente toutes les applications et fonctionnalités d'Hydria sous forme d'icônes cliquables organisées par catégories, similaire à un launcher d'applications mobile ou desktop.

## Accès

- **URL** : `http://localhost:8000/accueil/`
- **Menu Desktop** : Bouton "Applications" dans la navbar (dégradé bleu/violet)
- **Menu Mobile** : Premier élément "Toutes les applications" avec fond coloré
- **Permission** : Utilisateur connecté requis (`@login_required`)

## Architecture

### Fichiers créés

1. **Template** : `backend/templates/home_launcher.html` (750+ lignes)
2. **Vue** : `backend/hydria/views.py` - Fonction `home_launcher()`
3. **URL** : `backend/hydria/urls.py` - Route `/accueil/`

### Fichiers modifiés

1. **base.html** : Ajout liens menu desktop et mobile vers `/accueil/`

## Organisation des applications

Les applications sont regroupées en **12 catégories principales** :

### 1. Applications Principales
- Fil d'actualité
- Recherche
- Tableau de bord
- Carte interactive

### 2. Plannings & Terrain
- Vue liste
- Calendrier
- Vue consolidée
- Indemnités
- Retour (caissière)
- Retour Indemnités
- Retour Frais Déplacement

### 3. Suivi & Contrôle
- Inspections
- **Analyses d'eau** (nouveau)
- Réparations
- Positions GPS

### 4. Chantiers
- Demandes Villages
- Validation Sources
- Chantiers
- Kanban

### 5. Facturation
- Relevés
- Facturation
- Points d'eau
- Modalités
- Compteurs
- Fournisseurs

### 6. Gestion Volumétrique
- Analyse consommation
- Tarifs

### 7. RH & Paie
- Employés
- Postes
- Grilles de salaire
- Fiches de paie
- IRSA
- CNaPS/FMFP
- Mutuelle

### 8. Congés & Absences
- Demandes de congés
- Récupérations

### 9. Comptabilité
- Vérification
- Import DiameX
- Déclaration Communication
- Natures de déclaration
- Comptes

### 10. Infrastructure & Ouvrages
- Ouvrages
- Types d'ouvrages
- Types d'équipements
- Gestion complète

### 11. Référentiel
- Géographie
- Organisations
- Types d'activités
- Types de désignations
- Déplacements

### 12. Système
- Utilisateurs
- Qualité des données
- Architecture
- Messages (Conversations)

## Interface utilisateur

### Composants

#### 1. En-tête
- Titre : "Applications Hydria"
- Icône : `fa-th` (grille)
- Description : "Sélectionnez une application pour commencer"

#### 2. Barre de recherche
- Champ de recherche en pleine largeur
- Filtre en temps réel par nom d'application
- Icône loupe à droite

#### 3. Grilles d'applications
- Layout responsive :
  - Mobile : 2 colonnes
  - Tablette : 4 colonnes
  - Desktop : 6 colonnes
- Gap de 6 unités entre cartes

#### 4. Cartes d'application
- Icône colorée (64×64px, arrondi-xl)
- Nom de l'application en dessous
- Effet hover : Translation -1 + shadow-xl
- Effet hover sur nom : Couleur primaire

### Classes CSS personnalisées

```css
.app-card {
    /* Carte avec flex vertical, padding, bordure */
    @apply flex flex-col items-center justify-center p-4 rounded-lg
           hover:shadow-lg transition-all duration-200 cursor-pointer
           bg-base-100 border border-base-300;
}

.app-card:hover {
    /* Animation de levée */
    @apply transform -translate-y-1 shadow-xl;
}

.app-icon {
    /* Icône ronde avec fond coloré */
    @apply w-16 h-16 rounded-xl flex items-center justify-center
           text-white mb-3 shadow-md;
}

.app-name {
    /* Texte centré sous l'icône */
    @apply text-sm font-medium text-center text-base-content;
}

.app-card:hover .app-name {
    /* Changement de couleur au survol */
    @apply text-primary;
}
```

### Couleurs des icônes

Les icônes utilisent les classes de couleurs DaisyUI :
- `bg-primary` : Bleu
- `bg-info` : Cyan
- `bg-success` : Vert
- `bg-warning` : Orange
- `bg-error` : Rouge
- `bg-accent` : Violet

**Distribution équilibrée** : Les couleurs sont distribuées pour créer un visuel harmonieux dans chaque catégorie.

## JavaScript

### Fonctionnalité de recherche

```javascript
document.getElementById('search-apps').addEventListener('input', function(e) {
    const searchTerm = e.target.value.toLowerCase();
    const appCards = document.querySelectorAll('.app-card');

    appCards.forEach(card => {
        const appName = card.querySelector('.app-name').textContent.toLowerCase();
        if (appName.includes(searchTerm)) {
            card.style.display = 'flex';
        } else {
            card.style.display = 'none';
        }
    });
});
```

**Fonctionnement** :
1. Écoute les changements dans le champ de recherche
2. Récupère le texte saisi (en minuscules)
3. Parcourt toutes les cartes d'application
4. Compare le nom avec le terme de recherche
5. Affiche/masque les cartes selon correspondance

## Avantages

### Pour les utilisateurs
1. **Vue d'ensemble complète** : Toutes les fonctionnalités visibles d'un coup d'œil
2. **Recherche rapide** : Trouver une application par son nom
3. **Accès direct** : Un clic vers l'application souhaitée
4. **Organisation logique** : Regroupement par catégories métier
5. **Design moderne** : Interface type launcher mobile/desktop

### Pour les développeurs
1. **Centralisation** : Toutes les URLs en un seul endroit
2. **Maintenance** : Facile d'ajouter/retirer des applications
3. **Documentation** : Les catégories documentent l'architecture
4. **Cohérence** : Même présentation pour toutes les applications

## Maintenance

### Ajouter une nouvelle application

1. **Identifier la catégorie** appropriée (ou créer une nouvelle)
2. **Ajouter la carte** dans le template :

```html
<a href="{% url 'mon_app:ma_vue' %}" class="app-card">
    <div class="app-icon bg-primary">
        <i class="fas fa-mon-icone fa-2x"></i>
    </div>
    <div class="app-name">Mon Application</div>
</a>
```

3. **Choisir l'icône** depuis Font Awesome
4. **Choisir la couleur** de fond (primary/info/success/warning/error/accent)

### Créer une nouvelle catégorie

```html
<div class="mb-12">
    <h2 class="text-2xl font-bold mb-6 flex items-center">
        <i class="fas fa-mon-icone text-primary mr-3"></i>
        Ma Nouvelle Catégorie
    </h2>
    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-6">
        <!-- Cartes d'applications -->
    </div>
</div>
```

### Modifier les icônes

Font Awesome est utilisé pour toutes les icônes :
- Référence : https://fontawesome.com/icons
- Format : `<i class="fas fa-nom-icone fa-2x"></i>`
- Taille : `fa-2x` (2 fois la taille normale)

## Responsive Design

### Mobile (< 768px)
- Grille : 2 colonnes
- Icônes : 64×64px
- Padding réduit

### Tablette (768px - 1024px)
- Grille : 4 colonnes
- Espacement optimal

### Desktop (> 1024px)
- Grille : 6 colonnes
- Pleine utilisation de l'écran

## Intégration au menu

### Menu Desktop (navbar)
- Bouton coloré avec dégradé : `bg-gradient-to-r from-primary to-accent`
- Position : Premier élément du menu central
- Texte : "Applications"
- Icône : `fa-th`

### Menu Mobile (hamburger)
- Fond coloré pour visibilité : `bg-gradient-to-r from-primary/20 to-accent/20`
- Position : Premier élément du menu déroulant
- Texte : "Toutes les applications"
- Icône : `fa-th`

## Améliorations futures possibles

1. **Favoris** : Permettre aux utilisateurs d'épingler leurs apps favorites
2. **Historique** : Afficher les applications récemment utilisées
3. **Badges** : Notifications sur les icônes (ex: 5 nouvelles factures)
4. **Drag & Drop** : Personnaliser l'ordre des applications
5. **Thèmes** : Différents thèmes de couleurs pour les catégories
6. **Raccourcis clavier** : Accès rapide par touches (ex: Alt+1)
7. **Applications externes** : Intégration avec systèmes tiers
8. **Statistiques** : Afficher nombre d'éléments sous chaque app (ex: "15 relevés")

## Tests de validation

- [x] Django check sans erreur
- [x] URL reverse fonctionne (`/accueil/`)
- [x] Template se charge correctement
- [x] Recherche d'applications fonctionnelle
- [x] Liens desktop et mobile visibles
- [x] Toutes les URLs sont valides
- [x] Responsive sur mobile/tablette/desktop
- [x] Effets hover fonctionnent

## Performance

- **Poids de la page** : Léger (HTML + CSS inline, pas de JS lourd)
- **Chargement** : Rapide (pas d'appels API)
- **SEO** : Pas applicable (page authentifiée)
- **Accessibilité** : Utilise les balises sémantiques HTML5

## Sécurité

- **Authentification** : Décorateur `@login_required` appliqué
- **Permissions** : Basées sur les URLs sous-jacentes
- **XSS** : Protection Django automatique (template escaping)
- **CSRF** : Non applicable (pas de formulaires)

---

**Date de création** : 23 décembre 2025
**Dernière modification** : 23 décembre 2025
**Auteur** : Claude Code (Assistant IA)
**Version** : 1.0
