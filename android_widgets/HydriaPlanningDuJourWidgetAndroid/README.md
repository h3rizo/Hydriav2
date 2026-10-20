# Hydria Activités du Jour Widget Android

Widget Android natif façon Google Calendar : agenda personnel des activités de planning
du jour (recouvrements forfaitaires, réparations et autres).

Les activités affichées sont celles déjà visibles pour l'utilisateur connecté dans Hydria
(lui-même, et ses subordonnés actifs s'il est responsable). Le bouton engrenage (⚙, à côté
d'Actualiser) ouvre un écran de filtres — personne, base, région, district, commune et
type d'activité — identique dans son fonctionnement au panneau de filtres du widget web
(page `/widget/`). Sur Android 12 et plus, un appui long sur le widget puis "Paramètres
du widget" rouvre le même écran pour les changer.

Un point vert indique une activité terminée, un point orange une activité en cours.
Pour les collectes de paiement, le statut "terminé" est calculé automatiquement d'après
le pointage des lignes de paiement (pas de bouton pour le forcer manuellement).

## Ouvrir dans Android Studio

1. `File > Open`.
2. Sélectionner le dossier `HydriaPlanningDuJourWidgetAndroid`.
3. Attendre la synchronisation Gradle.
4. Choisir un téléphone Android connecté, puis cliquer sur **Run**.
5. Ouvrir l'application, se connecter à Hydria et choisir **Ajouter à l'écran d'accueil**.

## Construire l'APK

Dans Android Studio : `Build > Build APK(s)`. Le fichier produit se trouve dans
`app/build/outputs/apk/debug/app-debug.apk`.
