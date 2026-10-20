# Bien-être Hydria — Android

Application Android native de la plateforme Bien-être Hydria. La Phase 1 fournit une
verticale d'authentification compilable contre l'API Django v1, sans modifier le parcours
Web existant.

## Prérequis

- Android Studio compatible AGP 9.3
- Android SDK 37
- JDK 17 ou plus récent pris en charge par Gradle 9.5

## Ouvrir et compiler

Ouvrir le dossier `bienetre/android` dans Android Studio, puis synchroniser Gradle.

En ligne de commande sous Windows :

```powershell
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
.\gradlew.bat assembleDebug testDebugUnitTest lintDebug
```

L'APK de développement est produit dans
`app/build/outputs/apk/debug/app-debug.apk`.

## Environnements API

L'URL par défaut est `https://bienetre.hydria.mg/`. Elle peut être remplacée sans
modifier le code source :

```powershell
.\gradlew.bat assembleDebug -PBIENETRE_API_BASE_URL=http://10.0.2.2:8000/
```

Le trafic HTTP clair reste bloqué par la configuration Android. Pour tester un serveur
local HTTP, utiliser un tunnel HTTPS ou une configuration de débogage locale non suivie
par Git. Aucun secret ne doit être placé dans `gradle.properties` ou `local.properties`.

## Modules Phase 1

- `app` : point d'entrée, navigation protégée et écran de session authentifiée ;
- `core:model` : modèles métier de session et de capacités ;
- `core:network` : DTO, Retrofit, renouvellement JWT, dépôt d'authentification et coffre de jetons ;
- `core:designsystem` : couleurs, typographie et thèmes clair/sombre ;
- `feature:auth` : connexion, inscription, validation et états d'écran.

Les modules métier suivants seront ajoutés avec leur première fonctionnalité réelle,
plutôt que sous forme de coquilles vides.

## Sécurité de la session

- accès JWT court et refresh rotatif côté Django ;
- jetons chiffrés en AES-GCM par une clé non exportable d'Android Keystore ;
- refresh effectué par un client Retrofit séparé pour éviter les boucles ;
- un seul refresh simultané grâce à un mutex ;
- en-tête `Authorization` masqué dans les logs et aucun corps HTTP journalisé ;
- révocation serveur tentée avant l'effacement local à la déconnexion ;
- trafic clair désactivé et sauvegarde Android des données de l'application désactivée.

## Backend requis

La version du backend contenant `/api/v1/mobile/auth/` doit être déployée avant un test
contre la production. Le frontend Nuxt et son authentification par session restent
compatibles et indépendants.

