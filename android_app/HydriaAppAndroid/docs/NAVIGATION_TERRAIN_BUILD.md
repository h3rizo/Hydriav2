# Navigation terrain — compilation et validation

Projet : `C:\Users\Dir Soakoja\Desktop\HydriaAppAndroid`

## Compiler et exécuter les tests

```powershell
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
.\gradlew.bat testDebugUnitTest assembleDebug '-Pandroid.injected.testOnly=false'
```

APK généré : `app\build\outputs\apk\debug\app-debug.apk`.

## Installer sans perdre les données locales

```powershell
adb install -r ".\app\build\outputs\apk\debug\app-debug.apk"
```

L’option `-r` remplace l’application en conservant sa base SQLite, son snapshot et sa file de synchronisation.

## Comportement hors ligne

- La carte neutre, les entités déjà synchronisées, le GPS, le cap et la navigation directe restent disponibles.
- Les créations, déplacements et archivages sont enregistrés localement avant d’être placés dans `sync_queue`.
- Un conflit HTTP 409 conserve l’action et marque l’entité `conflict` ; aucune donnée serveur n’écrase silencieusement la saisie locale.
- La synchronisation dédiée utilise un curseur persistant et des pages de 500 éléments.

## Compatibilité SQLite

La recherche géographique utilise des index B-tree latitude/longitude puis une distance Haversine exacte. Cette stratégie remplace RTree, absent de certaines versions constructeur de SQLite Android, notamment sur le DOOGEE Blade20 testé.

## Vérification minimale sur appareil

1. Ouvrir Hydria et vérifier que l’accueil reste actif.
2. Ouvrir **Terrain > Navigation terrain**.
3. Accepter ou refuser le GPS : aucun choix ne doit fermer l’application.
4. Vérifier la carte neutre et le bouton **Sync**.
5. Créer un repère hors ligne, fermer et rouvrir l’application, puis vérifier sa présence.
