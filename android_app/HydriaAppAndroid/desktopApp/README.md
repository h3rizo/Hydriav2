# :desktopApp — Hydria Opérations (poste de travail)

Client Desktop (Windows / Linux) en **Compose Multiplatform**, bâti sur le module `:shared`
de la migration KMP. Voir `../Claude outputs/consolidation-kmp-etat-20260909.md` §3.

## État (squelette — 9 sept. 2026)

| Élément | État |
|---|---|
| Module Gradle `:desktopApp`, fenêtre + `NavigationRail` 5 modules | ✅ |
| Écran **Calculatrice** — câblé sur `shared/calculator/CalculatorEngine` | ✅ fonctionnel |
| Écran **Recherche** + login — **parité Android** : 14 catégories (onglet Tout), type + statut (Personnes), région/district/commune/employé responsable (Ouvrages) ; Ktor CIO + cache SQLDelight + repli snapshot | ✅ fonctionnel |
| Écran **Relevés** — périmètre + saisie (cartes sociales) + **mode correction** + file hors-ligne + drain | ✅ fonctionnel (sans GPS) |
| Écran **Réparations** — liste + « Marquer terminée » + **création / édition** (file hors-ligne) + drain | ✅ fonctionnel |
| Écran **Planning** — agenda par date (bande de jours + cartes) + **création / édition** + drain | ✅ fonctionnel |
| Écran **Navigation** — dégradé (sans carte/GPS) : téléchargement périmètre + liste/filtre/distance | ✅ fonctionnel |
| Installateur Windows `.msi` + `.exe` (icône, upgrade en place, JRE embarqué **tous modules**) | ✅ produit + lancé/vérifié (base créée) |
| Installateur Linux `.deb` | ⏳ config prête, à builder sur Linux |
| `DesktopPaths` — dossier de données local par OS | ✅ |
| Base SQLDelight Desktop (`hydria.db`), façades `:shared` partagées | ✅ (`HydriaDesktopDatabase`) |
| Préférences / session (`preferences.json`) | ✅ (`DesktopPrefs` / `DesktopSession`) |
| Client réseau Ktor (engine CIO desktop, déjà dans `:shared`) | ✅ branché (Recherche + login) |
| Installateurs `.msi` / `.exe` / `.deb` via jpackage | config posée, non testée |

## Lancer en dev

```
export JAVA_TOOL_OPTIONS="-Djdk.net.unixdomain.tmpdir=./work/no-unix-sockets"   # environnement Claude uniquement
./gradlew :desktopApp:run
```

## Construire un installateur

```
./gradlew :desktopApp:packageDistributionForCurrentOS
# Windows -> desktopApp/build/compose/binaries/main/{msi,exe}/HydriaOperations-2.10.2.{msi,exe}
# Linux   -> ./gradlew :desktopApp:packageDeb  ->  .../deb/hydria-operations_2.10.2-1_amd64.deb
```

Détails, prérequis par OS et versionnage : **`BUILD_INSTALLERS.md`**.
Le JRE est embarqué par jpackage — l'utilisateur final n'installe rien d'autre.
`packageVersion` (2.10.2) et `windows.upgradeUuid` sont figés pour la mise à jour MSI en place.
Signature (Authenticode Windows / clé `.deb`) : non configurée.

Les 6 écrans sont fonctionnellement complets (au niveau du périmètre de l'app terrain Android).

## Prochaines étapes

1. `.deb` : `./gradlew :desktopApp:packageDeb` sur une machine Linux ; tester l'install `.msi` sur
   un poste Windows vierge ; signature Authenticode / clé `.deb`.
2. `./gradlew :desktopApp:run` pour exercer réellement (login, sync, saisie, drain, carte).
