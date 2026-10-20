# Hydria Design System

> Statut : **RÉFÉRENCE OFFICIELLE, VERSION 1**  
> Page modèle : `/comptabilite/dashboard-paiements-volume/`  
> Template de référence : `backend/templates/accounting/dashboard_paiements_volume.html`

## Décision

Le dashboard des paiements volumétriques est la page modèle du design applicatif Hydria. Toute création ou modernisation d'une interface Hydria doit utiliser ses principes, ses proportions et ses comportements comme point de départ.

Cette décision concerne le langage d'interface. Elle n'impose pas de reproduire tous les blocs du dashboard sur des pages dont le besoin métier est différent.

## Signature de la référence

Le conteneur principal du template porte l'attribut suivant :

```html
data-hydria-design-reference="dashboard-v1"
```

Cet attribut identifie l'implémentation validée. Il ne doit pas être ajouté à une autre page. Les autres pages peuvent utiliser des composants conformes, mais seule la page modèle porte cette signature.

## Principes obligatoires

1. Donner la priorité à la décision métier et aux éléments nécessitant une action.
2. Utiliser des interfaces denses, lisibles et adaptées aux opérations B2B.
3. Conserver une hiérarchie claire entre titre, filtres, indicateurs, actions et détails.
4. Employer la couleur pour un statut, une sélection ou une action, jamais comme décoration gratuite.
5. Préserver les thèmes Hydria Dark, Winter et Hydria Glass.
6. Garder un contraste lisible et un focus clavier visible.
7. Préserver les routes, permissions, paramètres, exports, impressions et appels API pendant un redesign.
8. Maintenir un ordre visuel identique à l'ordre du DOM.
9. Respecter `prefers-reduced-motion`.
10. Concevoir d'abord pour les données réelles, les libellés longs et les états incomplets.

## Structure de page recommandée

Une page métier Hydria suit cet ordre lorsque les sections sont pertinentes :

1. En-tête compact avec contexte et actions.
2. Filtres courts, repliables et responsives.
3. Indicateurs principaux sous forme de cartes individuelles.
4. Alertes et éléments à traiter.
5. Contenu opérationnel principal.
6. Analyses et détails secondaires.
7. États vides, erreurs et aides contextuelles.

## Composants de référence

### En-tête

- Sourcil fonctionnel court.
- Titre métier clair.
- Badges pour la période et les filtres actifs.
- Une seule action visuellement principale.
- Actions secondaires en style neutre, contour ou fantôme.

### Cadres et surfaces

- Un cadre est un outil de hiérarchie, pas une décoration par défaut.
- Utiliser une surface bordée pour un dashboard dense, un workflow en étapes, un bloc repliable ou plusieurs groupes difficiles à distinguer.
- Garder l'en-tête et le contenu à plat lorsque l'espacement, le titre et la structure existante suffisent à séparer les éléments.
- Ne pas ajouter un cadre Hydria autour d'une carte déjà clairement matérialisée par son fond ou son ombre.
- Une page légère doit privilégier l'espace blanc, les alignements et les séparateurs discrets.
- Avant d'ajouter une carte, vérifier qu'elle améliore réellement le balayage visuel ou la compréhension du périmètre.

### Filtres

- Labels courts en petite taille.
- Contrôles `select-sm` ou équivalent compact.
- Largeur proportionnelle au contenu attendu.
- Retour à la ligne sans étirement excessif.
- Réinitialisation visuellement secondaire.
- Application automatique explicitement annoncée lorsqu'elle existe.

### Cartes statistiques

- Une statistique par carte.
- Coins arrondis de 12 px.
- Bordure fine, fond légèrement teinté et ombre courte.
- Valeur dominante avec chiffres tabulaires.
- Libellé court et contexte en une ligne.
- Couleur cohérente avec la fonction de la carte.
- Aucune répétition d'une information déjà présente dans un indicateur plus utile.

### Couleurs sémantiques

- `primary` : information principale, sélection et action dominante.
- `info` : indicateur informatif.
- `accent` : indicateur complémentaire actif.
- `success` : objectif atteint ou situation conforme.
- `warning` : écart ou situation à surveiller.
- `error` : anomalie critique ou donnée non affectée.
- `secondary` : pointage, score ou action secondaire.

Les couleurs doivent toujours venir des variables de thème, avec un fond faiblement teinté et un texte suffisamment contrasté.

### Tableaux

- En-têtes compacts et clairement séparés.
- Colonnes numériques alignées à droite.
- Chiffres tabulaires pour les montants et taux.
- En-tête collant sur les longues listes.
- Première colonne collante uniquement si elle facilite la comparaison.
- Regroupements utilisant explicitement `primary` et `primary-content`.
- Vue mobile dédiée lorsque le tableau ne peut pas rester lisible par simple réduction.

### États

- Chargement : hauteur stable et indicateur centré.
- Vide : explication liée au filtre ou au périmètre.
- Erreur : cause utile et prochaine action possible.
- Succès : confirmation courte près de l'action.
- Désactivé : état visible, compréhensible et non ambigu.

## Dimensions de validation

Toute page migrée doit être contrôlée aux largeurs suivantes :

- 1440 px
- 1024 px
- 768 px
- 390 px
- 360 px

Les actions tactiles courantes doivent mesurer au moins 44 px sur mobile. Les tableaux complexes doivent proposer une vue mobile en cartes ou un défilement clairement maîtrisé.

## Contrat d'accessibilité

- Contraste WCAG AA pour les textes et contrôles.
- Navigation clavier complète.
- Focus visible.
- Nom accessible pour chaque action.
- Icônes décoratives avec `aria-hidden="true"`.
- Statuts jamais transmis par la couleur seule.
- Modales avec fermeture accessible et état de chargement explicite.
- Mouvement réduit lorsque le système le demande.

## Procédure de migration d'une page

1. Inventorier sa logique, ses routes, permissions, événements et états.
2. Comparer sa hiérarchie avec la page modèle.
3. Réutiliser les motifs du modèle adaptés au besoin réel.
4. Ne pas modifier la source de vérité métier pendant le travail visuel.
5. Tester les trois thèmes et les cinq largeurs de référence.
6. Tester les états normal, vide, chargement et erreur.
7. Vérifier exports, impressions et actions asynchrones.
8. Documenter toute dérogation nécessaire.

## Critères de conformité Hydria V1

Une page est conforme lorsque :

- son contenu prioritaire est identifiable dès le premier écran ;
- ses filtres sont compacts et adaptés à leur contenu ;
- ses statistiques utilisent des cartes individuelles cohérentes ;
- ses couleurs restent lisibles dans les trois thèmes ;
- son affichage reste utilisable aux cinq largeurs de référence ;
- ses fonctionnalités existantes sont intactes ;
- ses états et interactions sont accessibles ;
- les vérifications Django et les tests concernés réussissent.

## Gouvernance

Toute évolution majeure de la page modèle doit entraîner :

1. une mise à jour de ce document ;
2. une incrémentation de la version de référence si les règles changent ;
3. une vérification des composants déjà réutilisés ailleurs ;
4. une validation sur les thèmes clair et sombre avant déploiement.

La référence actuelle reste `dashboard-v1` tant que les fondations, la hiérarchie et les composants décrits ici ne changent pas de manière incompatible.
