# Hydria Calendrier Planning Widget Android

Widget Android natif façon Google Calendar : grille calendaire mensuelle (lundi à dimanche)
des activités de planning (recouvrements forfaitaires, réparations et autres).

Navigation mois précédent/suivant directement dans le widget. Chaque jour affiche un badge
coloré indiquant le nombre d'activités : vert si toutes sont terminées, orange sinon. Toucher
un jour ouvre le détail des activités de ce jour ; toucher le titre du mois ouvre le jour
courant.

Les activités affichées sont celles déjà visibles pour l'utilisateur connecté dans Hydria
(lui-même, et ses subordonnés actifs s'il est responsable). Le bouton engrenage (⚙, à côté
d'Actualiser) ouvre un écran de filtres — personne, base, région, district, commune et
type d'activité — identique dans son fonctionnement au panneau de filtres du widget web
(page `/widget/`). Les filtres choisis sont mémorisés et s'appliquent à toutes les
instances du widget sur l'écran d'accueil ; sur Android 12 et plus, un appui long sur le
widget puis "Paramètres du widget" rouvre le même écran.

Pour les collectes de paiement, le statut "terminé" est calculé automatiquement d'après
le pointage des lignes de paiement (pas de bouton pour le forcer manuellement).

## Ouvrir dans Android Studio

1. `File > Open`.
2. Sélectionner le dossier `HydriaPlanningCalendrierWidgetAndroid`.
3. Attendre la synchronisation Gradle.
4. Choisir un téléphone Android connecté, puis cliquer sur **Run**.
5. Ouvrir l'application, se connecter à Hydria et choisir **Ajouter à l'écran d'accueil**.
   Le widget est plus grand qu'un widget classique (grille de 6 semaines) : agrandissez-le
   sur l'écran d'accueil si les jours paraissent trop petits.

## Construire l'APK

Dans Android Studio : `Build > Build APK(s)`. Le fichier produit se trouve dans
`app/build/outputs/apk/debug/app-debug.apk`.
