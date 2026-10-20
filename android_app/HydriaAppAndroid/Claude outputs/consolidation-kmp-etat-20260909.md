# Consolidation KMP — état au 9 sept. 2026 & plan des 4 chantiers restants

Suite de `hydria-native-analyse-migration-kmp.md` et `checklist-test-migration-kmp.md`.
App Android en `2.10.0` (code 40), module `:shared` (Android + JVM Desktop) qui build.
Toolchain JVM 17, Gradle 9.5, Kotlin 2.2.10, SQLDelight 2.2.1, Ktor 3.4.0.

**Build vérifié dans l'environnement** avec :
```
export JAVA_TOOL_OPTIONS="-Djdk.net.unixdomain.tmpdir=./work/no-unix-sockets"
./gradlew :shared:desktopTest :shared:testDebugUnitTest :app:testDebugUnitTest :app:assembleDebug
```
(le workaround `no-unix-sockets` contourne le blocage loopback de l'ancien environnement.)

---

## 0. Fait cette session

0. **Fin du chantier 2** (10 sept.) : les 5 derniers traitements inline des activités sortis dans
   `:shared` — `TerrainRules.perimeter`, `ReadingsRules.monthProgress`, `SearchRules.worksGroupKey`,
   `VolumeWorkflowGateway.reconciledEntries` (+ `isSyncConflict` déjà délégué). Voir §2 pour le
   détail et les tests. `:app:testDebugUnitTest` passe de 126 à 132.
1. **Nettoyage des 143 fichiers `.bak-*`** (5,8 Mo) dans tout l'arbre source (`app/`, `shared/`,
   racine). Archive de sécurité : `hydria-bak-archive-20260909.tar.gz` (jointe). Le build est
   inchangé (les `.bak` n'étaient jamais compilés) — vérifié.
3. **Squelette `:desktopApp`** (chantier 3, étapes 1 + 3) — voir plus bas §3.e.
2. **Extraction `VolumeActivity.state()` + `conflicted()`** → `shared` :
   - `shared/.../volume/VolumeWorkflowGateway.kt` : nouveaux `conflicted(row, pending)` et
     `statusLabel(row, actions, conflicted)`.
   - `app/.../volume/VolumeWorkflow.kt` : relais.
   - `app/.../volume/VolumeActivity.kt` : les deux fonctions deviennent des one-liners.
   - Tests : `LegacyVolumeWorkflow` gèle l'ancien code, `VolumeMigrationTest.
     conflictedAndStatusLabelAreIdenticalToLegacy()` compare ligne à ligne sur toutes les combos.
   - Durcissement mineur assumé : le nouveau `conflicted` fait `optJSONArray("factures")` (null → false)
     au lieu de `getJSONArray` inconditionnel ; identique sur le domaine réel (toute op volume a
     `factures`), juste plus défensif si une op malformée passait.

---

## 1. Validation terrain complète (hors ligne + après mise à jour)

**Ne peut se faire que sur un vrai appareil, par une personne.** Rien à coder ; ce qui suit est le
protocole à exécuter avant de retirer quoi que ce soit (chantier 4).

### 1.a Parcours par domaine, réseau coupé puis rétabli
Reprendre `checklist-test-migration-kmp.md` intégralement. Le point le plus important : la section
« Synchro générale (SyncDispatch) » — couper le réseau, faire **une action dans chaque domaine**
(réparation, planning, relevé, terrain, marquage GPS/repère navigation, volume), rétablir → la file
se vide sans « type inconnu » ni erreur.

### 1.b Scénario « après mise à jour » (spécifique — pas dans la checklist)
La bascule SQLDelight lit les anciennes tables `TerrainDatabase` **une fois** au premier lancement de
la version migrée, puis pose un drapeau `useNew*`. À tester avec un appareil qui a des **données
réelles de la version précédente** (2.7.x) :

1. Installer 2.7.0, se connecter, synchroniser, **saisir des choses sans les synchroniser** :
   un relevé, une photo de point, un marquage GPS, une opération volume (encaissement local).
2. Couper le réseau. Installer 2.10.0 **par-dessus** (pas de désinstallation — mise à jour APK).
3. Ouvrir l'app **hors ligne**. Vérifier :
   - la file d'attente affiche exactement les mêmes opérations en attente (compteurs du Centre de
     synchronisation identiques) ;
   - le snapshot terrain / le périmètre s'affiche (pas d'écran « synchronisez ») ;
   - l'état des cartes sociales, des index déjà saisis, de la calculatrice (mémoire), du cache
     recherche est préservé ;
   - aucune opération n'est dupliquée ni perdue.
4. Rétablir le réseau, synchroniser → tout part, la file se vide, pas de conflit 409 « fantôme ».
5. Cas limite : forcer un échec de migration (ex. base corrompue) et vérifier que l'app **retombe sur
   `TerrainDatabase`** (`useNew* = false`) sans planter — c'est le rôle du `runCatching` global dans
   `OfflineStore` (`migrateSyncQueueIfNeeded`, `migrateSnapshotIfNeeded`, etc.).

### 1.c Journal de bord
Pour chaque anomalie : action exacte + attendu/observé + en ligne/hors ligne. Ça pointe directement
le `*Rules` / `*Gateway` concerné.

---

## 2. Extraction des derniers traitements des activités

L'extraction est ~95 % faite : toutes les règles métier sont dans `shared/rules/*`,
`shared/*/…Gateway.kt`, `shared/*/…Rules.kt`. Les Activities ne gardent que la construction de vues
(Views programmatiques) et le spécifique Android (photo, GPS, MapLibre, impression) — **ça doit
rester dans `app/`** selon le plan.

**FAIT (10 sept. 2026).** Les 5 derniers traitements inline sont sortis dans le même style
(règle pure dans `shared`, relais dans `app`, `Legacy*` + test de caractérisation) :

| Fichier `app/` | Fonction | Cible `shared` | État |
|---|---|---|---|
| `MainActivity.kt` (~804) | `terrainForPerimetre(terrain)` — filtre les ouvrages `responsable_direct` + swap des `stats` | `shared/rules/terrain/TerrainRules.kt` : `perimeter(terrain, etendu)` | ✅ one-liner |
| `MainActivity.kt` (renderCampaignSetup) | `monthProgress(ouvrage)` — `Pair<done,total>` sur les points d'un ouvrage | `shared/rules/readings/ReadingsRules.kt` : `monthProgress(ouvrage, pending, year, month)` | ✅ one-liner |
| `MainActivity.kt` (~3653) | `isSyncConflict(item)` | `shared/sync` : `QueueOverviewGateway.isConflict()` | ✅ déjà délégué (rien à faire) |
| `search/SearchActivity.kt` (renderGroupedWorks) | clé de regroupement région/district/commune | `shared/rules/search/SearchRules.kt` : `worksGroupKey(row)` + `GROUP_KEY_SEPARATOR` | ✅ |
| `volume/VolumeActivity.kt` (~221) | `entries()` — fusion des lignes DiameX avec l'état `pointee` de la file | `shared/volume/VolumeWorkflowGateway.kt` : `reconciledEntries(diamex, pending, invoices)` | ✅ one-liner |

Tests ajoutés : `TerrainSearchCompatibilityTest` (`perimeter` + `worksGroupKey`),
`VolumeMigrationTest.reconciledEntriesFlagPointedLinesIdenticallyToLegacy()` (comparé à
`LegacyVolumeWorkflow`), `ReadingsCampaignProgressTest` (nouveau, 3 cas `monthProgress`).
Régression : `:shared:desktopTest` 149, `:shared:testDebugUnitTest` 146, `:app:testDebugUnitTest`
132 — 0 échec ; `:app:assembleDebug` + `:desktopApp:createDistributable` OK.

`MainActivity` reste volumineux (~4000 lignes) : c'est **normal**, c'est la couche UI Android ;
le but n'était pas de la vider mais d'en sortir le métier — **c'est fait à 100 %**.

---

## 3. Interface + installateurs Windows/Linux (stockage local)

**Pas commencé.** `settings.gradle.kts` ne contient que `:app` et `:shared`.

### 3.a Décisions à prendre avant de coder
- **Framework UI Desktop** : Compose Multiplatform (JetBrains) — seul choix cohérent avec `:shared`
  en Kotlin. Ajoute `org.jetbrains.compose` + `compose.desktop.currentOs`.
- **Périmètre v1 Desktop** : commencer par **Calculatrice + Recherche** (zéro dépendance
  GPS/caméra/MapLibre — cf. `hydria-native-analyse-migration-kmp.md` §5 Phase 4). Puis Relevés,
  Réparations, Planning. Navigation en dernier (MapLibre n'a pas d'équivalent Desktop mûr → écran
  dégradé : saisie manuelle de coordonnées / liste, pas de carte).
- **Format installateur** : `jpackage` via le plugin Compose (`nativeDistributions`) →
  `msi` (+ `exe`) pour Windows, `deb` + `AppImage` pour Linux. JRE **embarqué** (jpackage le fait) —
  l'utilisateur n'installe rien d'autre.
- **Stockage local Desktop** : SQLDelight `sqlite-driver` (déjà en `desktopMain`). Fichier DB dans
  le dossier utilisateur : `%APPDATA%/Hydria` (Windows) / `~/.local/share/hydria` (Linux) via
  `AppDirs` ou un `expect/actual` maison. `multiplatform-settings` ou un fichier JSON pour les
  préférences (équivalent `SharedPreferences`).

### 3.b Squelette à créer
```
settings.gradle.kts                 → include(":desktopApp")
build.gradle.kts (racine)           → + plugin org.jetbrains.compose apply false
desktopApp/build.gradle.kts         → plugins compose + application ;
                                       dependsOn(:shared) ; nativeDistributions { targetFormats(Msi, Deb, AppImage) }
desktopApp/src/jvmMain/kotlin/mg/hydria/desktop/
    Main.kt                         → application { Window { HydriaDesktopApp() } }
    HydriaDesktopApp.kt             → NavigationRail 5 écrans (calqué HydriaWindow.navigationRail)
    di/DesktopGraph.kt              → instancie HydriaHttpClient (CIO), driver SQLDelight (JdbcSqliteDriver),
                                       OfflineStore-équivalent Desktop
    storage/DesktopPaths.kt         → dossier DB/prefs par OS
    screens/CalculatorScreen.kt     → réutilise shared/calculator/*
    screens/SearchScreen.kt         → réutilise shared/search/* + shared/network/*
```

### 3.c Points de friction connus
- `OfflineStore` (app) est Android (`SharedPreferences`, `Context`). Le Desktop a besoin de son
  propre point d'entrée persistance qui appelle les mêmes `*Gateway` de `shared`. Les `*Gateway`
  de `shared/androidMain/database/` (`HydriaSnapshotGateway`, etc.) sont **Android-only** —
  il faut leurs équivalents `desktopMain` sur le driver JDBC, OU remonter ces gateways en
  `jvmCommonMain` avec le driver injecté (préférable).
- `HydriaSharedDatabaseHolder` est en `androidMain` uniquement → créer `desktopMain` avec
  `JdbcSqliteDriver(url)` + `HydriaSharedDatabase.Schema.create(driver)`.
- Réseau : `HydriaEngine.desktop.kt` (CIO) existe déjà. RAS.
- Auth : `HydriaAuthGateway` en `jvmCommonMain` → OK pour Desktop.

### 3.d Ordre
1. Squelette + `:desktopApp` qui lance une fenêtre vide qui compile. — ✅ **fait (§3.e)**
2. `DesktopPaths` + driver SQLDelight Desktop + `HydriaSharedDatabaseHolder` desktop. — `DesktopPaths` ✅, driver ❌
3. Écran Calculatrice (aucun réseau, aucune DB → valide la chaîne `shared`→Compose). — ✅ **fait**
4. Écran Recherche (réseau + cache DB → valide toute la pile).
5. `nativeDistributions` → produire un `.msi` et un `.deb`/`.AppImage`, tester l'install sur poste vierge.
   — config posée ✅, `createDistributable` (image + JRE) ✅, `.msi`/`.deb` non produits/testés.
6. Étendre écran par écran (Relevés → Réparations → Planning → Navigation dégradée).

### 3.e Fait le 2026-09-09 (squelette)
- `settings.gradle.kts` : `include(":desktopApp")`. Root `build.gradle.kts` : plugins
  `org.jetbrains.kotlin.jvm` 2.2.10, `org.jetbrains.kotlin.plugin.compose` 2.2.10,
  `org.jetbrains.compose` 1.9.0 (tous `apply false`). Compose MP 1.9.0 ✔ compatible Kotlin 2.2.10.
- `desktopApp/build.gradle.kts` : `kotlin("jvm")` + `org.jetbrains.compose` + `plugin.compose` ;
  `implementation(project(":shared"))` (le variant `desktop` de `:shared` résout tout seul, pas
  besoin de disambiguïsation) ; `compose.desktop { application { nativeDistributions {
  targetFormats(Msi, Exe, Deb) ; packageName="HydriaOperations" ; packageVersion="2.10.0" ;
  windows.upgradeUuid figé ; linux.packageName="hydria-operations" } } }`.
- `desktopApp/src/main/kotlin/mg/hydria/desktop/` :
  `Main.kt` (Window 1180×780), `HydriaDesktopApp.kt` (`NavigationRail` 5 modules + `ComingSoon`),
  `DesktopAppModel.kt` (enum `DesktopScreen`, état `screen`), `storage/DesktopPaths.kt`
  (%APPDATA%\Hydria\Operations / ~/.local/share/hydria-operations, `hydria.db` + `preferences.json`
  — **rien n'y écrit encore**), `screens/CalculatorScreen.kt` (liste éditable câblée sur
  `CalculatorEngine.recalculate`, mapping FR des `ExpressionError` local au module).
- `desktopApp/README.md`.
- Vérifié : `:desktopApp:compileKotlin` ✅ ; `:desktopApp:createDistributable` ✅ →
  `desktopApp/build/compose/binaries/main/app/HydriaOperations/` (167 Mo, JRE jlink embarqué,
  WiX téléchargé auto pour un futur `packageMsi`) ; `:shared:desktopTest` + `:app:assembleDebug`
  toujours verts (aucune régression). **Fenêtre non lancée** (pas de GUI dans l'environnement) —
  faire `./gradlew :desktopApp:run` pour voir.
### 3.f Fait le 2026-09-09 (base locale SQLDelight côté Desktop)

Les 6 façades DB ont été **remontées de `shared/androidMain` → `shared/jvmCommonMain`** (partagées
Android + Desktop) : `HydriaSyncQueueGateway`, `HydriaSnapshotGateway`, `HydriaSearchCacheGateway`,
`HydriaCalculatorGateway`, `HydriaVolumeCacheGateway`, `HydriaGeoGateway`. Elles ne connaissent plus
le driver (retiré `import android.content.Context` + `fun init(context)`).

- `HydriaSharedDatabaseHolder` (maintenant `jvmCommonMain`) : `init(driver: SqlDriver)` +
  `isInitialized` + `resetForTests()`.
- **Android** : nouveau `shared/androidMain/.../HydriaAndroidDatabase.kt` — `init(context)` =
  `AndroidSqliteDriver(Schema, context, "hydria_shared.db")` (fichier et driver **identiques** à
  avant). `OfflineStore.kt` : les 6 `HydriaXGateway.init(appContext)` → `HydriaAndroidDatabase.init(appContext)`.
  **Aucun changement de comportement runtime Android** — mêmes requêtes, même base, filet
  `runCatching`/`useNew*` intact.
- **Desktop** : nouveau `shared/desktopMain/.../HydriaDesktopDatabase.kt` — `init(file)` =
  `JdbcSqliteDriver("jdbc:sqlite:$path", schema = HydriaSharedDatabase.Schema)` (création/migration
  du schéma automatique via `PRAGMA user_version`). Appelé dans `desktopApp/Main.kt` sur
  `DesktopPaths.databaseFile` (`<dataDir>/hydria.db`).
- **Tests** : `shared/build.gradle.kts` : ajout du source set `desktopTest` (`dependsOn(commonTest)`).
  Nouveau `shared/src/desktopTest/.../DatabaseGatewayDesktopTest.kt` — 3 tests (cache recherche
  round-trip, file de synchro enqueue/list/markFailed/remove, snapshot au-delà de la limite de
  chunk 256 Ko) sur un fichier SQLite temporaire via `HydriaDesktopDatabase`. **Premier test
  unitaire de ces façades** (sur Android : seulement instrumenté).
- Vérifié : `:shared:desktopTest` (3/3), `:app:testDebugUnitTest` (126/126, **aucune régression**),
  `:app:assembleDebug`, `:desktopApp:compileKotlin` ✅.

### 3.g Fait le 2026-09-09 (écran Recherche Desktop + login minimal)

- `desktopApp/build.gradle.kts` : + `implementation("org.json:json:20240303")` (les façades `:shared`
  renvoient du `org.json.JSONObject`, invisible en transitif ; pas d'Android SDK sur Desktop).
- **Session** : `storage/DesktopPrefs.kt` (fichier JSON `<dataDir>/preferences.json`, best-effort),
  `auth/DesktopSession.kt` — `login()`/`logout()` via `HydriaAuthGateway.loginBlocking` (déjà la
  source de vérité du login), jeton + `employe_nom` + `user` persistés. Pas de gate de login global :
  seul l'écran Recherche l'exige, la Calculatrice reste hors-ligne.
- **Recherche** : `screens/SearchController.kt` reproduit `SearchActivity.load()/consume()` —
  réseau (`HydriaOperationsGateway.search/works/people`, Ktor CIO) → cache
  (`HydriaSearchCacheGateway.save/payload`) → repli hors-ligne
  (`SearchRules.offlineWorksResults` sur `HydriaSnapshotGateway.snapshot().terrain.ouvrages`).
  `screens/SearchScreen.kt` : formulaire de login si non authentifié, sinon segments
  Tout/Ouvrages/Personnes + champ + liste de cartes (titre/sous-titre/type + badge « Copie hors
  ligne »). `DesktopScreen.RECHERCHE.ready = true`, câblé dans `HydriaDesktopApp`.
- Vérifié : `:desktopApp:compileKotlin` ✅. (`:shared` et `:app` non touchés ce tour.)
  Écran non exercé (pas de GUI / pas de creds ici) — `./gradlew :desktopApp:run` pour tester la
  connexion réelle contre `www.hydria.mg`.

### 3.h Fait le 2026-09-10 (écran Relevés Desktop — slice verticale offline)

- `auth/LoginForm.kt` extrait de `SearchScreen` (partagé Recherche + Relevés).
- `screens/ReadingsController.kt` — slice verticale complète :
  1. **Périmètre** : `HydriaOperationsGateway.prepareTour(token, null)` → `HydriaSnapshotGateway.saveSnapshot(body)`.
  2. **Saisie** : ouvrage (`snapshot.ouvrages[]`) + date + point (`points_eau[]` filtrés `a_relever`) ;
     index / volume non facturé / remarque ; calculs `ReadingValidation` + `ReadingsRules`
     (consommation, volume facturé) ; validation `ReadingValidation.validate`.
  3. **File hors-ligne** : `HydriaSyncQueueGateway.enqueue(uuid, "reading", payload)` — payload
     identique à `MainActivity` (`point_eau_id`, `date_releve`, `nouvel_index`,
     `volume_non_facture`, `remarque`, `local_uuid`).
  4. **Drain** : pour chaque ligne `reading` en file → `HydriaOperationsGateway.saveReading(token, payload)`
     → `remove` si OK, `markFailed` sinon.
- `screens/ReadingsScreen.kt` — 2 volets (liste des points | formulaire de saisie), boutons
  « Synchroniser le périmètre » / « Synchroniser la file » + compteur en file.
- **Volontairement hors périmètre skeleton** : cartes sociales, enrichissement GPS, mode correction,
  toggle « déjà relevé ce mois ».
- `DesktopScreen.RELEVES.ready = true`. Vérifié : `:desktopApp:compileKotlin` +
  `:desktopApp:createDistributable` + régression `:shared:desktopTest` / `:app:testDebugUnitTest` /
  `:app:assembleDebug` ✅.

### 3.i Fait le 2026-09-10 (écran Réparations Desktop)

- `data/SnapshotSync.kt` extrait : `prepareTour` → `HydriaSnapshotGateway.saveSnapshot`, source unique
  du périmètre pour Relevés + Réparations (+ Planning à venir). `ReadingsController.syncPerimeter`
  refactoré pour l'utiliser.
- `screens/RepairsController.kt` — liste depuis `snapshot.reparations[]` (tableau plat), groupée/triée
  par ouvrage et criticité via `RepairOverviewGateway.prepare/visible` (:shared) ; libellés via
  `RepairRules` (activité, priorité, retard en jours) ; filtres « terminées » / « hors périmètre ».
  Action « Marquer terminée » → `HydriaSyncQueueGateway.enqueue(uuid, "finish_repair", {planning_id})`
  (même type que `RepairsSync` Android) ; drain → `HydriaOperationsGateway.finishRepair(token, planningId)`
  → `remove`/`markFailed` ; `RepairRules.pendingCompletionIds` masque les réparations déjà en file.
- `screens/RepairsScreen.kt` — liste groupée (en-tête ouvrage + cartes), colonne « retard en jours »,
  boutons de synchro + compteur en file.
- Hors périmètre skeleton : création / modification de réparation.
- `DesktopScreen.REPARATIONS.ready = true`. Vérifié : `:desktopApp:compileKotlin` +
  `:desktopApp:createDistributable` + `:shared:desktopTest` ✅.

### 3.j Fait le 2026-09-10 (écran Planning Desktop — lecture seule)

- `screens/PlanningController.kt` — agenda depuis `snapshot.plannings[]`, groupé/trié/sélectionné
  par `PlanningRules.agenda` (:shared, `PlanningAgenda.prepare` — même moteur que l'app Android :
  regroupement par date, date active = sélection valide sinon la plus proche d'aujourd'hui).
  Libellés via `PlanningRules` (jour de semaine, date complète, `dayIndicatorText` FÉRIÉ · WEEK-END),
  couleur de carte via `PlanningRules.activityKind` (VALIDATED / REPAIR / REST / OTHER).
- `screens/PlanningScreen.kt` — bande de jours horizontale (`LazyRow`, cellule = abrév + n° + puce si
  activités, sélection surlignée) + en-tête du jour + `LazyColumn` de cartes d'activité
  (fiche de poste, contexte, équipe, compteurs avances/déplacements/livraisons/paiements, statut).
- **Lecture seule** : création / modification de planning hors périmètre skeleton (pas de file).
- `HydriaDesktopApp` : les 5 écrans câblés, `when` exhaustif, `ComingSoon` + champ `DesktopScreen.ready`
  supprimés.
- Vérifié : `:desktopApp:createDistributable` + régression (`:shared:desktopTest`,
  `:app:testDebugUnitTest`, `:app:assembleDebug`) ✅.

### 3.l Fait le 2026-09-10 (écran Navigation dégradé Desktop)

- `screens/NavigationController.kt` — **sans carte ni GPS** (MapLibre pas d'équivalent Desktop mûr).
  - Téléchargement du périmètre : `NavigationDownload.run` (pagination, curseur dans `DesktopPrefs`)
    + `HydriaOperationsGateway.navigationEntities` → import dans SQLDelight par le **même chemin que
    l'app Android** : `GeoPageImportGateway.importPage` → `GeoImportGateway.entity/placement` →
    `HydriaGeoGateway.upsertServerEntity / upsertPlacementCandidate / upsertServerLandmarkType`,
    dans `HydriaGeoGateway.runImportTransaction`.
  - Liste : `HydriaGeoGateway.allEntities`, filtre catégorie (Village / Point d'eau / Équipement /
    Repère) + recherche nom/code/type. Si on saisit une position (lat/lon), distance + cap calculés
    par `GeoMath` et tri par distance.
  - Bouton « Réinitialiser le curseur » (repart du début à la prochaine synchro).
- **Hors périmètre** : marquage GPS, création de repères (exigent GPS + caméra).
- `DesktopScreen.NAVIGATION` ajouté (6ᵉ onglet). Vérifié : `:desktopApp:compileKotlin` +
  `:desktopApp:createDistributable` + régression (`:shared:desktopTest`, `:app:testDebugUnitTest`,
  `:app:assembleDebug`) ✅.

**Le module `:desktopApp` couvre maintenant les 6 écrans** (Calculatrice, Recherche+login, Relevés,
Réparations, Planning, Navigation dégradée).

### 3.k Fait le 2026-09-10 (installateurs Windows)

- Icônes : `desktopApp/icons/hydria.{ico,png}` générées depuis `branding/hydria-vase-master.png`
  (Pillow — `.ico` multi-tailles 16→256 Windows, `.png` 256 Linux). Câblées dans
  `desktopApp/build.gradle.kts` (`windows.iconFile` / `linux.iconFile`) + `shortcut`/`dirChooser`
  Windows, `shortcut`/`menuGroup` Linux.
- `./gradlew :desktopApp:packageDistributionForCurrentOS` (Windows) → **OK** :
  - `desktopApp/build/compose/binaries/main/msi/HydriaOperations-2.10.0.msi` (113 Mo)
  - `desktopApp/build/compose/binaries/main/exe/HydriaOperations-2.10.0.exe` (113 Mo)
  - WiX 3.11 auto-téléchargé, JRE embarqué.
  - MSI vérifié (COM `WindowsInstaller`) : `ProductVersion = 2.10.0`,
    `UpgradeCode = {5C7B1E42-...}` (= `upgradeUuid` → mises à jour en place OK), `Manufacturer = Hydria`.
- **`.deb` non produit** ici (pas de machine Linux — jpackage ne fait pas de cross-build). Config
  prête (`linux { ... }` + `icons/hydria.png`). Procédure : `desktopApp/BUILD_INSTALLERS.md`.
- **Non fait** : installer/lancer réellement le `.msi` (destructif, élévation) ; signature.

### 3.m Fait le 2026-09-10 (Relevés Desktop — cartes sociales)

- `ReadingsController` : `isKiosque` (type du point contient « KIOSQUE »), `availableSocialCards`
  (depuis `point.cartes_sociales[]` du snapshot, hors cartes déjà ajoutées), `socialCards`
  (`List<SelectedSocialCard>` : id / numéro / bénéficiaire / bidons 0-30), `addSocialCard` /
  `removeSocialCard` / `setSocialBidons`. `socialVolume` = Σ `ReadingsRules.socialCardVolume(bidons)`
  (bidon 20 L = 0,02 m³). `billedVolume` et `validationError` intègrent maintenant `socialVolume`.
  `save()` : `SocialCardGateway.prepare` (validation, avec messages `SocialCardError`) →
  `SocialCardGateway.payload` → `cartes_sociales` (chaîne JSON) dans le payload si non vide —
  **identique à `MainActivity`**.
- `ReadingsScreen.EntryForm` : section « Cartes sociales (bidons 20 L) » visible pour les kiosques —
  liste des cartes ajoutées (champ bidons + retirer) + menu « Ajouter une carte » ; le calcul
  affiché montre `conso − cartes = facture`. Formulaire rendu scrollable.
- Toujours hors périmètre Desktop : enrichissement GPS (pas de GPS sur poste de travail), mode
  correction d'un relevé déjà en file.
- Vérifié : `:desktopApp:createDistributable` + `:shared:desktopTest` ✅.

### 3.n Fait le 2026-09-10 (Relevés Desktop — mode correction)

- `ReadingsController` : `pendingByPoint` (`Map<point_eau_id, PendingReading>` — les relevés `reading`
  déjà en file pour `campaignDate`, calculé depuis `HydriaSyncQueueGateway.pending()`), `correcting`,
  `hasPendingReading(point)`. `selectPoint` : si le point a un relevé en file → **pré-remplit** index /
  volume non facturé / remarque / cartes sociales (parsées depuis `payload.cartes_sociales`, enrichies
  du numéro/bénéficiaire via `point.cartes_sociales[]`). `save()` en mode correction :
  `HydriaSyncQueueGateway.remove(ancien uuid)` puis `enqueue` du nouveau — **identique à `MainActivity`**.
- `ReadingsScreen` : chip « a corriger » sur les points concernés, note d'avertissement + bouton
  « Corriger le releve » dans le formulaire.
- Vérifié : `:desktopApp:createDistributable` + `:shared:desktopTest` ✅.

### 3.o Fait le 2026-09-10 (Réparations Desktop — création / édition)

- `RepairsController` : listes de saisie depuis `snapshot.references.{employes, ouvrages, repair_fiches,
  statuts, priorites}` (mêmes clefs que `MainActivity.showPlanningEditor`). État de formulaire
  (`fEmployee`/`fWork`/`fActivity`/`fDate`/`fStatus`/`fPriority`/`fRemark`, `editorOpen`, `editingId`).
  `openEditor(repair?)` pré-remplit (nouveau ou édition depuis `repair.employe_id`/`ouvrage_id`/
  `fiche_poste_id`/`statut_code`/`priorite_code`/`date_prevue`/`remarque`/`id`).
  `saveRepairForm()` : `RepairFormRules.validate(RepairDraft(...))` (:shared, mêmes règles
  qu'Android — employé/activité/ouvrage requis, date `AAAA-MM-JJ`) → `result.fields` → file
  `save_repair`. `drainQueue` traite maintenant **`finish_repair` ET `save_repair`**
  (`HydriaOperationsGateway.saveRepair` pour le second).
- `RepairsScreen` : bouton « Nouvelle reparation », « Modifier » sur chaque carte,
  `RepairEditorDialog` (`AlertDialog` M3 : 5 listes déroulantes `RefField` + date + remarque).
- Vérifié : `:desktopApp:createDistributable` + `:shared:desktopTest` ✅.

### 3.p Fait le 2026-09-10 (Planning Desktop — création / édition)

- `screens/RefDropdown.kt` extrait (liste déroulante `{id, label|nom}` + helper `refLabel`), partagé
  Réparations + Planning (le `RefField` local des Réparations supprimé).
- `PlanningController` : listes `snapshot.references.{employes, ouvrages, planning_fiches, statuts}`,
  état de formulaire (`fEmployee`/`fWork`/`fActivity`/`fDate`/`fStatus`/`fRemark`), `openEditor(planning?)`
  (pré-remplit depuis `planning.employe_id`/`ouvrage_id`/`fiche_poste_id`/`statut_code`/`date`/`remarque`/`id`
  ; nouvelle activité → date du jour sélectionné), `savePlanningForm()` :
  `PlanningFormRules.validate(PlanningDraft(...))` (:shared — employé/activité requis, ouvrage
  facultatif, date `AAAA-MM-JJ`) → file `save_planning`. Nouveau `drainQueue` →
  `HydriaOperationsGateway.savePlanning`. `pendingSaveCount`.
- `PlanningScreen` : boutons « Nouveau planning » / « Synchroniser la file » (visibles même sans
  aucun planning en cache), « Modifier » par carte d'agenda, `PlanningEditorDialog` (`AlertDialog` M3).
- Vérifié : `:desktopApp:createDistributable` + régression (`:shared:desktopTest`,
  `:app:testDebugUnitTest`, `:app:assembleDebug`) ✅.

**Les 6 écrans Desktop sont fonctionnellement complets** (au niveau du périmètre de l'app terrain
Android — hors GPS/carte/caméra qui n'existent pas sur poste de travail).

### 3.q Fait le 2026-09-10 (correctif JRE embarqué — « Failed to launch JVM »)

Le premier `.msi` (108 Mo) **plantait au lancement** :
`NoClassDefFoundError: java/sql/DriverManager` → `Failed to launch JVM`. Cause : `jlink`/`jdeps`
ne détecte pas les usages par réflexion, donc le runtime embarqué n'avait que 7 modules
(`java.base java.datatransfer java.xml java.prefs java.desktop java.logging jdk.crypto.ec`) —
il manquait `java.sql` (requis par `sqlite-jdbc` via `JdbcSqliteDriver`, appelé dans `Main.main()`
avant même la fenêtre).

Correctif : `includeAllModules = true` dans `desktopApp/build.gradle.kts` → `nativeDistributions`.
Installateur `.msi`/`.exe` : **108 → 134 Mo**. Vérifié : l'image relancée passe l'init base
(`%APPDATA%\Hydria\Operations\hydria.db` créé, schéma SQLDelight OK) et ouvre la fenêtre Compose ;
seuls des avertissements SLF4J bénins sur stderr. Doc : `desktopApp/BUILD_INSTALLERS.md`.

### 3.r Fait le 2026-09-10 (Recherche Desktop → parité Android)

L'écran Recherche Desktop était volontairement allégé (juste Tout / Ouvrages / Personnes, sans
filtres). Remis à parité avec `SearchActivity` — **UI Compose uniquement, 0 changement `:shared`**
(les signatures y étaient déjà : `search(token,q,types,page)`, `people(...,type,status,...)`,
`works(...,region,district,commune,employee)`, `workFilters(token)`) :

- **Onglet « Tout »** : `FlowRow` de 14 `FilterChip` (mêmes `ALL_TYPES` que l'app Android,
  ordre inclus, défaut = tout sauf `planning`) + boutons « Tout » / « Rien ». `selectedTypes`
  transmis à `search()`.
- **Onglet « Personnes »** : `RefDropdown` type (`PEOPLE_TYPES`) + statut (actif / inactif / tous,
  défaut `actif`).
- **Onglet « Ouvrages »** : `RefDropdown` région / district / commune / employé responsable,
  alimentés par `loadWorkFilters()` (`workFilters(token)` → cache SQLDelight `work_filters`,
  repli hors-ligne) + bouton « Réinitialiser ».
- `cacheKey()` aligné sur `SearchActivity` (inclut types triés + tous les filtres).

Régression : `:app:testDebugUnitTest` 132, `:shared:desktopTest` 149 — 0 échec ; `.msi`/`.exe`
reconstruits (134 Mo) ; image relancée OK (fenêtre ouverte, pas de crash au chargement Recherche).

### Reste à faire côté Desktop
1. **`.deb`** : `./gradlew :desktopApp:packageDeb` sur un poste / runner Linux (Debian/Ubuntu,
   `dpkg fakeroot binutils` **+ Android SDK** — `:shared` a une cible `androidTarget()` qui exige
   le SDK à la configuration). Voir `desktopApp/BUILD_INSTALLERS.md`.
2. **Tester l'install** `.msi` (134 Mo) sur un poste Windows vierge (raccourci, menu Démarrer,
   upgrade en place). Le bug « Failed to launch JVM » est corrigé (§3.q) — l'app démarre.
3. **Signature** Authenticode (`.msi` + `.exe`) / clé `.deb` — avec la signature de prod Android (§4.a).
4. **Exercer l'app** : `./gradlew :desktopApp:run` (login réel, sync périmètre, saisie, drain,
   téléchargement carte) — pas faisable dans l'environnement Claude (pas de GUI / d'identifiants).

**Les 6 écrans Desktop sont tous portés.** Le module `:desktopApp` est un client natif partiel
autonome (Compose, offline-first, JRE embarqué), aligné sur le périmètre de l'app terrain Android.

---

## 4. Signature de production + nettoyage des anciens replis

### 4.a Signature release — **bloqué sur toi** (keystore)
`app/build.gradle.kts` : `release { isMinifyEnabled = false }`, **aucun `signingConfig`**. La
distribution actuelle est l'**APK debug** (certif de dev, MAJ sans désinstallation — cf.
`DEPLOY_2.8.0.md`). Pour passer en release signé :
1. Tu génères une keystore (`keytool -genkeypair -v -keystore hydria-release.jks -alias hydria
   -keyalg RSA -keysize 2048 -validity 10000`) et tu **gardes** mot de passe + fichier (ne jamais
   commiter). Une fois perdue, plus aucune MAJ possible pour les appareils installés.
2. `keystore.properties` (git-ignoré) + `signingConfigs { create("release") { … } }` dans
   `app/build.gradle.kts`, `buildTypes.release.signingConfig = signingConfigs.getByName("release")`.
3. **Attention continuité** : les appareils ont aujourd'hui l'APK signé debug. Passer à une signature
   release = **signature différente** = Android refuse la MAJ (« package conflicte avec un existant »),
   il faut **désinstaller/réinstaller** partout. Soit tu assumes ce one-shot, soit tu restes en debug.
   → décision produit, à trancher avant.
4. Idem pour un futur `:desktopApp` : signature Authenticode (Windows) / clé pour `.deb`. Séparé.

### 4.b Nettoyage des replis — **bloqué sur le chantier 1** (validation terrain)

Ne rien retirer avant que 1.a + 1.b soient **verts sur un vrai appareil** pour le domaine concerné.
Les replis sont le filet de sécurité hors-ligne / post-MAJ. Ordre par domaine, une fois validé :

**Repli réseau (Ktor → `HydriaApi`)** — par domaine `X` ∈ {terrain, plannings, repairs, readings,
interventions, volume, navigation, search, calculator} :
1. `SessionNetworkRoute` de `X` : le figer à « toujours Ktor » (supprimer la branche `legacy`).
2. Dans `HydriaNetwork.kt` : supprimer les `{ HydriaApi.xxx(...) }` des méthodes de `X`.
3. Supprimer `OfflineStore.useNewXNetwork` + `OfflineStore.xNetwork` + les usages
   (`MainActivity`, `SearchActivity`, `NavigationTerrainActivity`, `VolumeActivity`… qui lisent
   `useNew*Network` pour un libellé de debug).
Quand **tous** les domaines sont faits :
4. Supprimer `app/network/SessionNetworkRoute.kt`, `HydriaApi.kt`.
5. `HydriaNetwork.kt` : soit le supprimer et faire pointer les appelants directement sur
   `HydriaOperationsGateway` (via un mince adaptateur `HydriaApi.Result`→`shared`), soit le garder
   comme cette façade mince. `HydriaApi.Result` étant le type de retour partout, garder un
   `data class` équivalent dans `app/` ou basculer sur `HydriaOperationsGateway.Result`.
6. `HydriaApi.login` : vérifier que `HydriaAuthGateway` le couvre déjà (login Android repointé sur
   `/mobile/api/login/`) avant suppression.

**Repli base locale (`TerrainDatabase` → SQLDelight)** — par bascule `useNew*` ∈ {SyncQueue,
SearchCache, Snapshot, Calculator, VolumeCache, Geo} :
1. Confirmer sur appareil (scénario 1.b) que la migration one-shot passe sur données réelles 2.7.x.
2. Dans `OfflineStore.kt` : supprimer chaque `else database.xxx()` (≈ lignes 326-548) et le
   `if (useNewX)`.
3. Supprimer les `migrateXIfNeeded()` (garder éventuellement 1-2 versions le temps que le parc soit
   à jour — les appareils qui sautent une version ont besoin de la migration).
4. Quand toutes les bascules sont retirées : supprimer `TerrainDatabase.kt` (908 lignes) et le champ
   `database` d'`OfflineStore`.

**Ordre recommandé** : calculator (le plus simple, pilote) → search → volume → readings → repairs →
plannings → interventions → terrain → navigation (le plus gros). Base locale en parallèle, même ordre
de domaine.

### 4.c Divers nettoyage
- `app/HydriaNetwork.kt.bak-*` et co : **fait** (chantier 0).
- `app/src/main/java/mg/hydria/app/HydriaNetwork.kt.bak-20260907d` : supprimé.
- Logs de build à la racine (`build_*.txt`, `gradle_build*.log`, `work_planning_threads.txt`,
  `build-volume.log`) : ~1 Mo de scratch, à supprimer quand tu veux (pas touché — ce sont tes traces
  de session).
- APK à la racine (`Hydria-Terrain-2.x.x-*.apk`) : ce sont des livrables, **garder** ou déplacer dans
  `releases/`.

---

## Résumé « par où continuer »

1. **Toi** : trancher signature debug-vs-release (§4.a) ; fournir keystore si release.
2. **Toi / testeur terrain** : exécuter §1.a + §1.b sur un appareil avec données 2.7.x réelles.
3. **Moi, sans blocage** : §2 (extractions restantes) + §3.b→3.d (squelette `:desktopApp`,
   Calculatrice puis Recherche, premier `.msi`/`.deb`).
4. **Moi, après §1 vert** : §4.b domaine par domaine.
