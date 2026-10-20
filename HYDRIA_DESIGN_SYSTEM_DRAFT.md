# Hydria Design System, historique du pilote

> Statut : **ARCHIVÉ**. Le pilote a été validé. La référence officielle est désormais `HYDRIA_DESIGN_SYSTEM.md`.

## 1. Intention

Hydria est un outil métier B2B destiné au suivi opérationnel et financier de services d'eau. L'interface doit permettre de comprendre une situation, repérer un écart et lancer une action sans détour.

Réglages du pilote :

- `DESIGN_VARIANCE: 3`, cohérence forte et variations limitées
- `MOTION_INTENSITY: 2`, retours d'état discrets uniquement
- `VISUAL_DENSITY: 9`, données nombreuses, espacements courts et lisibles

## 2. Principes

1. Prioriser la décision : taux, payé, prévu, écart, puis les éléments à traiter.
2. Garder les filtres proches du contexte sans masquer le contenu principal.
3. Utiliser la couleur pour un statut ou une action, pas pour décorer chaque bloc.
4. Afficher les nombres financiers avec des chiffres tabulaires et une unité explicite.
5. Conserver un vocabulaire identique entre cartes, tableaux, exports et impressions.
6. Préserver les routes, paramètres, permissions et interactions lors d'un redesign.

## 3. Fondations visuelles

### Couleurs

La source de vérité reste les thèmes DaisyUI Hydria existants :

- `primary` : navigation, action principale, sélection et information active
- `success` : résultat conforme ou recouvrement atteint
- `warning` : situation à surveiller ou valeur inhabituelle
- `error` : anomalie bloquante, écart critique ou donnée non affectée
- `base-100`, `base-200`, `base-300`, `base-content` : surfaces, séparateurs et texte

Une vue courante ne doit pas multiplier les fonds colorés. Préférer un fond neutre avec un texte, une bordure ou un badge sémantique.

### Typographie

- Police d'interface : pile système actuelle de Tailwind
- Titres de page : 23 à 32 px, graisse 700 à 800, interlettrage légèrement resserré
- Titres de section : 16 px, graisse 700
- Corps : 14 px
- Libellés et métadonnées : 11 à 12 px
- Montants, taux et identifiants : chiffres tabulaires, police monospace seulement dans les tableaux très techniques

### Espacement et formes

- Échelle principale : 4, 8, 12, 16, 24 px
- Rayon de panneau : 12 px
- Rayon de contrôle : celui fourni par DaisyUI, environ 8 px
- Ombre standard : une ombre courte de 1 à 2 px
- Séparateur : bordure `base-300` de 1 px

## 4. Architecture d'un dashboard

Ordre recommandé :

1. En-tête avec nom du module, période et actions
2. Filtres repliables, ouverts par défaut sur écran large
3. Indicateurs de synthèse
4. File d'attention et anomalies
5. Analyse principale et tableau opérationnel
6. Analyses secondaires, graphiques et détails

Le premier écran doit répondre à trois questions : quel est le taux, quel est l'écart, où faut-il agir ?

## 5. Composants du pilote

### En-tête de page

- Sourcil fonctionnel en capitales
- Titre court orienté métier
- Badges de période et de filtres actifs
- Une action principale maximum, les actions secondaires sont neutres ou en contour

### Panneau de filtres

- Élément `details` natif avec résumé compréhensible
- Labels toujours visibles
- Grille auto-adaptative avec largeur minimale de 168 px par contrôle
- Application automatique annoncée dans le résumé
- Réinitialisation visuellement secondaire

### Indicateur clé

- Libellé court en haut
- Valeur dominante avec chiffres tabulaires
- Contexte ou dénominateur en une ligne courte
- Bordure ou teinte légère pour le statut, sans grande surface saturée
- Un indicateur cliquable doit exposer son état avec `aria-pressed`

### Section analytique

- Titre, aide courte et contrôles sur une même ligne lorsque la largeur le permet
- Surface neutre, bordure et ombre minimale
- Contenu horizontalement défilable uniquement pour les tableaux complexes
- En-tête collant pour les longues listes

### Tableau

- En-têtes en 11 px, graisse 800 et capitales visuelles
- Cellules compactes, 9 px vertical et 10 px horizontal environ
- Colonnes numériques alignées à droite
- Première colonne collante seulement lorsque cela aide réellement la comparaison
- Survol discret et focus visible sur les lignes ou cellules interactives

### États

- Chargement : zone stable, fond neutre et indicateur centré
- Vide : message explicite lié aux filtres et action de réinitialisation si possible
- Erreur : message lisible, cause utile et prochaine action
- Succès : confirmation courte près de l'action concernée

## 6. Responsive

- 1440 px : quatre KPI par ligne, tableaux complets et actions alignées
- 1024 px : deux à quatre KPI selon le contenu, tableaux techniques défilables
- 768 px : deux KPI par ligne, filtres auto-adaptatifs
- 390 et 360 px : un KPI par ligne, actions pleine largeur, vue mensuelle en cartes
- Taille tactile minimale : 44 px pour une action courante sur mobile

Le dashboard volumétrique conserve sa vue mobile dédiée pour le suivi mensuel. Il ne faut pas réduire le tableau desktop jusqu'à rendre ses cellules illisibles.

## 7. Accessibilité

- Contraste WCAG AA pour texte et contrôles
- Focus visible sur liens, boutons, listes et champs
- Icônes décoratives avec `aria-hidden="true"`
- Nom accessible pour tout bouton icône seul
- Ordre visuel identique à l'ordre du DOM
- Navigation au clavier complète dans les panneaux, tableaux interactifs et modales
- Respect de `prefers-reduced-motion`
- Ne jamais transmettre un statut uniquement par la couleur

## 8. Règles de migration

Avant de migrer une autre page :

1. Inventorier routes, paramètres, permissions, identifiants DOM et appels API.
2. Repérer les composants réutilisables dans le pilote.
3. Conserver les calculs et la source de vérité métier.
4. Tester les thèmes Hydria Dark, Winter et Hydria Glass.
5. Tester 1440, 1024, 768, 390 et 360 px.
6. Tester au minimum les états normal, vide, chargement et erreur.
7. Comparer les exports et impressions avant et après la migration.

## 9. Points à valider avant version 1

- Palette sémantique définitive avec les utilisateurs financiers
- Seuils visuels des taux et écarts
- Format monétaire unique, notamment `Ar` et milliers `K`
- Comportement par défaut des panneaux analytiques repliables
- Terminologie définitive pour `non pointé`, `hors recouvrement` et `écart`
- Extension éventuelle des composants dans des includes Django partagés
