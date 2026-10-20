# Hydria Planning Widget Android

Widget Android natif combinant les deux anciens widgets « Calendrier planning » et
« Activités du jour » en un seul : une grille calendaire mensuelle (lundi à dimanche)
en haut, et l'agenda détaillé du jour touché juste en dessous.

## Fonctionnement

- Navigation mois précédent/suivant directement dans le widget.
- Chaque jour de la grille affiche un badge coloré indiquant le nombre d'activités :
  vert si toutes sont terminées, orange sinon.
- **Toucher un jour de la grille met à jour l'agenda en dessous** (sans changer
  d'écran) : le jour touché est surligné, et la liste de ses activités remplace
  celle du jour précédemment affiché.
- Au chargement (ou après un changement de mois), l'agenda affiche par défaut
  **aujourd'hui** si le mois courant est affiché, sinon le 1er jour du mois affiché.
- Toucher le titre du mois, l'en-tête de l'agenda, ou « voir tout » ouvre le détail
  plein écran du jour actuellement affiché dans l'agenda (utile si plus de 4
  activités ce jour-là).

Les activités affichées sont celles déjà visibles pour l'utilisateur connecté dans
Hydria (lui-même, et ses subordonnés actifs s'il est responsable). Le bouton
engrenage (⚙, à côté d'Actualiser) ouvre un écran de filtres — personne, base,
région, district, commune et type d'activité — identique dans son fonctionnement
au panneau de filtres du widget web (page `/widget/`). Les filtres choisis sont
mémorisés et s'appliquent à toutes les instances du widget sur l'écran d'accueil ;
sur Android 12 et plus, un appui long sur le widget puis "Paramètres du widget"
rouvre le même écran.

Pour les collectes de paiement, le statut "terminé" est calculé automatiquement
d'après le pointage des lignes de paiement (pas de bouton pour le forcer
manuellement).

## Architecture technique

Une seule requête réseau par rafraîchissement (`fetchActivites` sur les 42 jours
de la grille visible) alimente à la fois les compteurs de la grille et l'agenda
du jour sélectionné — toucher un jour ne déclenche donc pas de nouvel appel
réseau, juste un nouveau rendu à partir des données déjà chargées.

## Ouvrir dans Android Studio

1. `File > Open`.
2. Sélectionner le dossier `HydriaPlanningWidgetAndroid`.
3. Attendre la synchronisation Gradle.
4. Choisir un téléphone Android connecté, puis cliquer sur **Run**.
5. Ouvrir l'application, se connecter à Hydria et choisir **Ajouter à l'écran
   d'accueil**. Le widget est plus grand qu'un widget classique (grille de 6
   semaines + agenda) : agrandissez-le sur l'écran d'accueil si le contenu
   paraît trop petit.

## Construire l'APK

Dans Android Studio : `Build > Build APK(s)`. Le fichier produit se trouve dans
`app/build/outputs/apk/debug/app-debug.apk`.
