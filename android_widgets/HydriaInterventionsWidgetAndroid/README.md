# Hydria Interventions Widget Android

Widget Android natif pour suivre la file personnelle des dernières saisies de réparations Hydria.

## Ouvrir dans Android Studio

1. `File > Open`.
2. Sélectionner le dossier `HydriaInterventionsWidgetAndroid`.
3. Attendre la synchronisation Gradle.
4. Choisir un téléphone Android connecté, puis cliquer sur **Run**.
5. Ouvrir l’application, se connecter à Hydria et choisir **Ajouter à l’écran d’accueil**.

Le widget se rafraîchit toutes les 30 minutes selon les règles Android, au toucher du bouton d’actualisation et après chaque action **J’ai vu**. Une notification est proposée lorsqu’une nouvelle saisie rejoint la file.

## Construire l’APK

Dans Android Studio : `Build > Build APK(s)`. Le fichier produit se trouve dans `app/build/outputs/apk/debug/app-debug.apk`.
