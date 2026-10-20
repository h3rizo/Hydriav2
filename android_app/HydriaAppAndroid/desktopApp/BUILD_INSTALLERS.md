# Installateurs Hydria Opérations (Desktop)

`jpackage` **ne fait pas de cross-compilation** : chaque format doit être produit sur le système
d'exploitation cible.

| Cible | Commande | Machine | Sortie |
|---|---|---|---|
| Windows `.msi` + `.exe` | `./gradlew :desktopApp:packageDistributionForCurrentOS` | Windows | `desktopApp/build/compose/binaries/main/{msi,exe}/HydriaOperations-2.10.0.{msi,exe}` |
| Linux `.deb` | `./gradlew :desktopApp:packageDeb` | Linux (Debian/Ubuntu) | `desktopApp/build/compose/binaries/main/deb/hydria-operations_2.10.0-1_amd64.deb` |
| Image seule (test rapide, tout OS) | `./gradlew :desktopApp:createDistributable` | — | `.../binaries/main/app/HydriaOperations/` |
| Lancer sans packager | `./gradlew :desktopApp:run` | — | — |

Le **JRE est embarqué** par jpackage (jlink) : l'utilisateur final n'installe rien d'autre.

## JRE embarqué — `includeAllModules = true`

`desktopApp/build.gradle.kts` force **tous les modules** du JDK dans le runtime embarqué.
Sans ça, `jlink`/`jdeps` ne voit pas les usages par réflexion (`sqlite-jdbc` → `java.sql`,
Ktor TLS → `java.naming`…) et l'app **plante au lancement** :

```
Exception in thread "main" java.lang.NoClassDefFoundError: java/sql/DriverManager
Failed to launch JVM
```

Coût : installateur ~108 Mo → ~134 Mo. Négligeable pour un poste de travail. **Ne pas retirer**
sans re-tester chaque écran (réseau/login, base, sync).

## Prérequis

- **JDK 17** (fourni par le toolchain Gradle ; `jpackage` en fait partie).
- **Android SDK** (`compileSdk 35`) : `:desktopApp` dépend de `:shared`, qui est un module KMP
  avec cible `androidTarget()` → l'Android Gradle Plugin exige le SDK **à la configuration**,
  même pour ne construire que le `.deb`/`.msi`. Sur une machine sans Android Studio :
  ```bash
  mkdir -p ~/android-sdk/cmdline-tools && cd ~/android-sdk/cmdline-tools
  wget https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
  unzip commandlinetools-linux-*.zip && mv cmdline-tools latest
  export ANDROID_HOME=~/android-sdk
  yes | ~/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses
  ~/android-sdk/cmdline-tools/latest/bin/sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"
  ```
  puis, à la racine du projet, un `local.properties` avec `sdk.dir=/home/<user>/android-sdk`.
- **Windows** : WiX Toolset 3 — **téléchargé automatiquement** par le plugin Compose au premier
  `packageMsi` (voir la ligne `Download https://github.com/wixtoolset/wix3/...` dans les logs).
  Rien à installer à la main.
- **Linux** : `dpkg`, `fakeroot`, `binutils` (`sudo apt install dpkg fakeroot binutils`).
  Pour un `.rpm` : `rpm-build`. Pour un `.AppImage` : non couvert ici.

## Environnement Claude / cette session

- Le `.msi` (+ `.exe`) est produit et vérifié ici (machine Windows).
- Le `.deb` **ne peut pas être produit ici** (pas de machine Linux) : la config est en place
  (`desktopApp/build.gradle.kts` → `linux { ... }` + `icons/hydria.png`), à lancer sur un poste
  ou un runner Linux.

## Versionnage

`desktopApp/build.gradle.kts` :
- `packageVersion = "2.10.2"` — aligné sur l'app Android. MSI exige un premier composant 0–255.
- `windows.upgradeUuid = "5c7b1e42-..."` — **NE JAMAIS CHANGER** : c'est ce qui permet à un nouveau
  `.msi` de remplacer l'ancien en place (sinon deux installations côte à côte).

Pour une nouvelle version : incrémenter `packageVersion`, reconstruire, distribuer. Le `.msi`
détecte l'ancienne version via l'`upgradeUuid` et fait la mise à jour.

## Signature (à faire)

Non configurée — les binaires ne sont pas signés.
- **Windows** : signature Authenticode (certificat OV/EV + `signtool`) sur le `.msi` **et** le
  `.exe` embarqué, sinon SmartScreen affiche un avertissement.
- **Linux** : signature du `.deb` (`dpkg-sig` / dépôt `apt` signé GPG) si distribution via dépôt.

À traiter avec la signature de production Android (voir
`Claude outputs/consolidation-kmp-etat-20260909.md` §4.a).

## Icône

`desktopApp/icons/hydria.{ico,png}` — générées depuis `branding/hydria-vase-master.png`
(script : `python` + Pillow, cf. commit). `.ico` multi-tailles (16→256) pour Windows,
`.png` 256×256 pour Linux.
