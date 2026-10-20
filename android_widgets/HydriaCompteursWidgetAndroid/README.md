# Hydria Widget (Android)

## Version 1.2 — filtres visibles et fiche ouvrage adaptative

Le périmètre sélectionné est affiché sous le titre du widget. Un toucher
sur **Ouvrages**, puis sur une commune et un ouvrage, ouvre maintenant une
fiche native avec les informations générales, la localisation, les modes de
gestion, les tarifs, les points d'eau et les équipements.

- Téléphone : la liste et la fiche ouvrage s'affichent successivement en
  plein écran, avec retour vers la liste.
- Tablette (largeur minimale 600 dp) : liste à gauche et fiche à droite. Le
  premier ouvrage est sélectionné automatiquement, puis le toucher d'une
  autre ligne remplace le détail affiché.

## Filtres par widget

Touchez le titre **Hydria** d'un widget déjà placé pour choisir son
périmètre. Les quatre filtres de la version Windows sont disponibles :

- Organisation
- Région
- District
- Commune

Les listes Région → District → Commune sont dépendantes. Le choix est
conservé séparément pour chaque widget et s'applique aux six compteurs,
aux regroupements District → Commune et aux listes détaillées.

App Widget Android classique (posé sur l'écran d'accueil, comme un
widget météo natif) affichant 6 stats Hydria : ouvrages, points d'eau,
factures non pointées, paiements forfaitaires à collecter aujourd'hui,
réparations non terminées, réparations à faire sous 7 jours.

Application **séparée** de `HydriaFloatingAndroid` (bouton flottant
actions rapides) — celle-ci n'affiche QUE des données Hydria, pas de
menu de navigation ni de météo.

Le projet est compilé et vérifié avec Gradle. L'APK debug est généré dans
`app/build/outputs/apk/debug/app-debug.apk`.

## Fonctionnement

1. À l'ajout du widget sur l'écran d'accueil, Android affiche
   automatiquement la connexion puis les quatre filtres.
2. Le token obtenu (`/widget/api/login/`) est stocké localement sur le
   téléphone.
3. Le widget se rafraîchit tout seul toutes les 30 minutes
   (`/widget/api/stats/`), et peut être rafraîchi manuellement en
   retirant/recollant le widget ou en tapant sur le titre.
4. Taper sur le titre "💧 Hydria" réouvre les filtres et permet aussi de
   changer de compte.

## Installation et compilation

Mêmes étapes que `HydriaFloatingAndroid` — voir son README pour le
détail complet (installation Android Studio, connexion téléphone USB,
etc.). Ouvrir ce dossier `HydriaWidgetAndroid` comme un projet
Android Studio indépendant.

## Ajouter le widget sur l'écran d'accueil

1. Installer l'app (compilation depuis Android Studio, ou installation
   manuelle de l'APK).
2. Appui long sur l'écran d'accueil → **Widgets**.
3. Chercher "Hydria Widget" dans la liste.
4. Glisser le widget sur l'écran d'accueil.
5. L'écran de configuration s'ouvre automatiquement — se connecter,
   choisir Organisation/Région/District/Commune, puis appliquer.
6. Le widget affiche les statistiques du périmètre choisi.

## Limitations connues

- Rafraîchissement toutes les 30 minutes minimum — c'est une
  contrainte du système Android (`updatePeriodMillis`), pas
  configurable en dessous de ce seuil pour préserver la batterie.
- Chaque statistique est cliquable et ouvre son détail. Les catégories
  géographiques utilisent le regroupement District → Commune.
- Le style visuel est volontairement simple (Android natif, pas de
  flou façon "liquid glass") — les widgets Android n'ont pas accès à
  un rendu web/CSS.
