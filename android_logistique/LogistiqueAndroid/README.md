# Logistique Android

Application Android native autonome pour les opérations logistiques Hydria. L’API mobile est servie par `www.hydria.mg/api/mobile/v1`, indépendamment de l’identifiant et du projet Android.

## Séparation avec Hydria Terrain

- Projet Gradle indépendant : `android_logistique/LogistiqueAndroid`.
- Identifiant production : `mg.hydria.logistique`.
- Identifiant debug : `mg.hydria.logistique.debug`.
- Aucune dépendance vers `android_app/HydriaAppAndroid`.
- Aucune WebView et aucun écran HTML embarqué.

## Architecture

- `app` : point d’entrée et configuration Android/Hilt/WorkManager.
- `core:model` : valeurs décimales fixes, statuts et commandes métier.
- `core:database` : cache Room, positions, opérations, outbox et conflits.
- `core:network` : contrat Retrofit de l’API mobile JSON versionnée.
- `core:sync` : outbox et worker prêts pour le futur endpoint idempotent de mutations.
- `feature:main` : navigation Compose à cinq entrées et écrans terrain.

Le stock canonique reste produit par le serveur. Toute projection locale doit porter `estimated=true` et rester visible comme estimation jusqu’à acceptation par l’API.

## Compiler

1. Créer `local.properties` avec `sdk.dir=C:\\chemin\\vers\\Android\\Sdk`.
2. Lancer `gradlew.bat testDebugUnitTest assembleDebug` sous Windows.
3. L’APK se trouve dans `app/build/outputs/apk/debug/`.

La première connexion et le bootstrap utilisent l’API JSON `/api/mobile/v1`. Les routes web Django existantes ne sont volontairement pas consommées par l’application. Les jetons d’accès et de renouvellement sont chiffrés avec Android Keystore ; le mot de passe n’est jamais conservé.

## État actuel

Le socle compilable couvre la séparation applicative, l’authentification, le renouvellement de session, le bootstrap filtré par périmètre, le cache Room migrable, l’état réseau, l’outbox, les conflits et les cinq surfaces principales. Les mutations restent volontairement en lecture seule : leur endpoint idempotent n’est pas encore implémenté côté Django et aucun formulaire métier ne sera inventé. Voir `docs/BACKEND_AUDIT.md`, `docs/PARITY_MATRIX.md` et `docs/mobile-api-v1.yaml`.
