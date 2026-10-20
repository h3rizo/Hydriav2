# Hydria Terrain → Hydria Opérations Native (KMP) — Analyse & plan de migration

*Analyse du projet Android existant à `HydriaAppAndroid`, en vue d'une migration progressive vers Kotlin Multiplatform + Compose Multiplatform (Android + Linux + Windows), sans réécriture complète.*

---

## 1. Cartographie de l'architecture actuelle

Projet **mono-module** (`:app`, namespace `mg.hydria.app`), AGP 9.3.2 / Kotlin 2.2.10 / JVM 17, `minSdk 26` / `compileSdk`-`targetSdk 34`. Version courante en dev : `2.9.1` (code 39) ; les `.apk` livrés vont de 2.1.4 à 2.7.0 — app mature, en production, avec beaucoup d'itérations réelles sur le terrain.

**Aucun pattern MVVM/MVI** : pas de `ViewModel`, pas de coroutine, pas de DI (ni Hilt ni Koin). Tout est synchrone via `Executors.newSingleThreadExecutor()`. L'UI est **100 % construite en code impératif** (Activities + Views programmatiques), un seul layout XML existe (`activity_main.xml`). Pas de Compose.

**Point le plus problématique : `MainActivity.kt` fait 4388 lignes.** C'est une god-class qui gère à elle seule 3 écrans (Terrain/Relevés, Réparations, Plannings) via un `enum Screen`, mélangeant logique métier (parsing, filtres, formats) et construction de vues.

Packages existants :
- `mg.hydria.app` (racine) : `MainActivity`, `HydriaApp`, `HydriaApi` (réseau), `OfflineStore` (persistance), `TerrainDatabase` (SQLite brut), `TerrainMeasurementEngine`, `HydriaVisuals`/`HydriaWindow`.
- `calculator/` : `AdvancedCalculatorActivity`, `CalculatorRepository`, `CalculatorModels`, `BusinessModels`, `SalaryEngine`, `SalaryConfigRepository`, `DecimalExpressionParser`, `GpsConverter`.
- `navigation/` : le module le **plus abouti architecturalement** — déjà séparé en `data/`, `geo/`, `location/`, `map/`, `model/`, `sync/`, `ui/`.
- `search/` : `SearchActivity`, `SearchDetailActivity`, `RecentInterventionsActivity`.
- `volume/` : `VolumeActivity`, `VolumeRepository`, `VolumeWorkflow`, `VolumePrinter`/`VolumeRecapPrinter`, `VolumeQr`.

Le README confirme le modèle produit : app native pour les écrans terrain à forte fréquence d'usage (Relevés, Réparations, Plannings, Navigation), avec un bouton **WEB** qui renvoie vers `www.hydria.mg` pour tout le reste. Ce n'est pas un shell WebView — c'est un client natif partiel assumé, exactement l'esprit que tu veux garder.

### État des 9 modules fonctionnels visés

| Module | État | Emplacement |
|---|---|---|
| Recherche | ✅ Existe | `search/` |
| Calculatrice avancée | ✅ Existe | `calculator/` |
| Navigation terrain | ✅ Existe (le plus propre) | `navigation/` |
| Marquage / GPS | ✅ Existe (intégré à navigation) | `navigation/location/`, backend `navigation_terrain` |
| Relevé volumétrique | ✅ Existe | `volume/` |
| Facturation | 🟡 Partiel — l'app envoie le relevé, la facturation est calculée côté serveur | `HydriaApi.kt` (`saveReading`) |
| Réparations | 🟡 Existe mais **noyé dans `MainActivity`** | `MainActivity.kt` (Screen.REPAIRS) |
| Planning | 🟡 Existe mais **noyé dans `MainActivity`** | `MainActivity.kt` (Screen.PLANNINGS) |
| Encaissement | ❌ N'existe pas en natif | — (bon candidat pour naître directement en `commonMain`) |

---

## 2. Stack technique — ce qui bloque et ce qui aide

**Bonne nouvelle :** AGP/Kotlin sont récents, aucune contrainte de version n'empêche d'adopter KMP dès maintenant.

**Mauvaise nouvelle :** aucune des fondations habituelles n'est en place — tout devra être introduit *avant* d'extraire la logique métier, sinon tu migreras deux fois :

| Aujourd'hui (Android-only) | Cible KMP | Effort |
|---|---|---|
| `HttpURLConnection` manuel (`HydriaApi.kt`) | **Ktor Client** | Réécriture de la couche réseau, mais logique d'appel inchangée |
| `org.json.JSONObject/JSONArray` | **kotlinx.serialization** | Mécanique, dataclasses à typer proprement |
| `SQLiteOpenHelper` + SQL brut (`TerrainDatabase`, chunking manuel anti-CursorWindow) | **SQLDelight** | Le plus gros chantier de données — mais l'astuce du chunking est une contrainte Android pure qui disparaît sur Desktop |
| `SharedPreferences` | **multiplatform-settings** (Russhwolf) ou DataStore KMP | Simple |
| `Executors` synchrone, zéro coroutine | **coroutines + Ktor suspend** | Réécriture de la couche async — pas un simple déplacement de fichier |
| Callbacks Activity | ViewModel + StateFlow partagés | Nécessaire pour partager la logique de présentation |

Point d'attention réseau : l'API Django consomme du **`x-www-form-urlencoded`**, pas du JSON REST classique (`HydriaApi.saveReading` construit un `Map<String,String>`). Ktor devra utiliser le plugin form-submission plutôt que de poser un `Content-Type: application/json` par défaut — sinon ça casse le backend sans toucher à Django.

Bon signal côté backend : le module `navigation_terrain` utilise déjà un pattern **`local_uuid` unique** pour l'idempotence offline (sur `Repere`, `ReperePhoto`) qui correspond au `sync_queue.local_uuid` côté client SQLite. **Ce pattern d'UUID + version optimiste est exactement ce qu'il faut généraliser** dans le Sync Engine partagé — ne pas en inventer un autre.

Encapsulation `expect/actual` nécessaire pour : GPS/localisation, caméra (photos réparations), MapLibre (SDK Android — pas d'équivalent KMP mûr aujourd'hui, prévoir deux implémentations UI derrière une interface commune), ZXing (QR/impression), impression Android.

---

## 3. Ce qui peut rester tel quel (aucune modification immédiate)

- Tout ce qui est déjà bien isolé et fonctionne : `navigation/geo/{GeoMath, EdgeIndicatorEngine}`, `navigation/model/GeoModels` — ce sont déjà quasiment des candidats `commonMain` sans changement de logique, seulement un changement d'emplacement.
- `calculator/{CalculatorModels, BusinessModels, SalaryEngine, DecimalExpressionParser, GpsConverter}` — calcul pur, aucune dépendance Android visible.
- Les écrans Android eux-mêmes (Activities/Views) : rien à toucher tant que la couche métier n'a pas de nouvelle home.
- Le backend Django et son schéma `navigation_terrain` (`TypeRepere`, `Repere`, `ReperePhoto`, `GeoPositionAudit`) : à conserver comme référence de contrat API, pas à modifier dans un premier temps.

## 4. Classement par cible (commonMain / androidMain / desktopMain / à garder dans l'app Android pour l'instant)

**→ `commonMain` (candidats directs, portage à faible risque) :**
`GeoMath`, `EdgeIndicatorEngine`, `GeoModels`, `CalculatorModels`, `BusinessModels`, `SalaryEngine`, `DecimalExpressionParser`, `GpsConverter`, la logique de règles métier de Réparations/Planning une fois extraite de `MainActivity`.

**→ `commonMain` (candidats après réécriture de fondation) :**
`HydriaApi` → clients Ktor par domaine (auth, plannings, facturation, recherche, navigation_terrain), les DTOs JSON, `TerrainDatabase`/`OfflineStore` → schéma SQLDelight + repositories, `NavigationSyncManager` → Sync Engine générique basé sur `local_uuid`/version.

**→ `androidMain` (spécifique, à encapsuler derrière une interface commune) :**
`TerrainLocationController`, `HeadingController` (GPS/boussole Android), caméra/permissions, intégration MapLibre Android, `VolumePrinter`/`VolumeRecapPrinter` (impression Android), ZXing.

**→ `desktopApp` (à créer) :**
équivalents Desktop des interfaces ci-dessus (fichier/impression système, pas de GPS réel — champ de saisie manuelle des coordonnées ou import), rendu carte Desktop (MapLibre Java/Qt ou une lib KMP quand mature).

**→ à garder tel quel dans l'app Android pour l'instant (ne pas toucher avant d'avoir une fondation commonMain stable) :**
Toutes les Activities/Views actuelles — elles continuent de tourner sur l'ancienne base tant que la logique qu'elles appellent n'a pas migré ; elles seront reconnectées au nouveau `commonMain` module par module, pas basculées d'un coup.

---

## 5. Ordre de migration proposé (révisé après lecture du code)

Ton ordre initial était bon ; je le resserre en tenant compte de ce qui bloque réellement.

**Phase 0 — Fondations (prérequis, sans toucher à l'UI ni au comportement visible)**
1. Créer le module `shared/` (structure KMP), targets `android` + `jvm` (Desktop) uniquement pour l'instant — pas besoin de viser iOS/autre.
2. Introduire kotlinx.serialization + définir les DTOs qui correspondent aux payloads Django déjà en usage (les regarder dans `HydriaApi.kt` et `django_backend_patch`).
3. Introduire Ktor Client dans `shared/network`, en respectant le form-encoding existant — remplacer `HydriaApi` progressivement, endpoint par endpoint, en gardant les deux implémentations en parallèle jusqu'à validation.
4. Introduire SQLDelight dans `shared/database`, avec un schéma qui reprend les tables actuelles de `TerrainDatabase` (sync_queue, snapshot, tables par domaine) — sans le hack de chunking CursorWindow qui n'a plus lieu d'être.

**Phase 1 — Premiers domaines métiers (risque faible, valeur immédiate)**
5. **Calculatrice avancée** → extraction vers `shared/calculator` (déjà quasi pure). Bon module pilote : petit, isolé, testable, permet de valider toute la chaîne shared→android avant de s'attaquer à plus gros.
6. **Recherche** → `shared/search`, modèles + logique de filtrage extraits, l'API `recherche/api/mobile/ouvrages/filtres/` migrée vers Ktor.
7. **Modèles + accès API génériques** (auth, config) → `shared/core`, `shared/auth`, `shared/network` consolidés.

**Phase 2 — Cœur data/offline**
8. **Base locale** → migration complète vers SQLDelight avec le schéma navigation_terrain (`local_uuid`, `version`, `archived_at`) comme référence de pattern, généralisé à tous les domaines.
9. **Relevés** (volume) → `shared/readings`, en s'appuyant sur la nouvelle base locale.
10. **Réparations** → extraction hors de `MainActivity` vers `shared/repairs` (le plus gros nettoyage de dette avant KMP à proprement parler).

**Phase 3 — Reste des modules**
11. **Planning** → extraction hors de `MainActivity` vers `shared/planning`.
12. **Facturation** → formalisation d'un vrai module `shared/billing` côté client (aujourd'hui minimal côté app).
13. **Encaissement** → à concevoir directement en `commonMain` dès le départ, avec repository/API/règles métier, puisqu'il n'existe pas encore côté Android (pas de dette à porter).
14. **Navigation terrain** → dernier par volume de code (973+ lignes + sous-packages), mais déjà bien structuré : portage plutôt mécanique une fois les fondations réseau/DB en place. Dépendance MapLibre à traiter séparément (encapsulation, pas de portage direct).

**Phase 4 — Desktop**
15. Créer `desktopApp/` (Compose Desktop) dès que 2-3 modules `shared` sont stables (viser après la Phase 1, sans attendre la fin de la Phase 3) — commencer par la Calculatrice et la Recherche côté Desktop, qui ne demandent aucune dépendance GPS/caméra.
16. Étendre progressivement Desktop aux modules Phase 2/3 au fur et à mesure de leur portage.

À chaque étape : Android doit rester fonctionnel et publiable (garder les deux implémentations en parallèle le temps de valider, puis supprimer l'ancienne).

---

## 6. Fichiers concrets à créer / déplacer / modifier pour démarrer (Phase 0 + module pilote Calculatrice)

**À créer :**
```
settings.gradle.kts          (modifier : ajouter include(":shared", ":desktopApp"))
shared/build.gradle.kts      (nouveau module KMP, targets android + jvm)
shared/src/commonMain/kotlin/mg/hydria/shared/calculator/
    CalculatorModels.kt      (déplacé depuis app/.../calculator/CalculatorModels.kt)
    BusinessModels.kt        (déplacé)
    SalaryEngine.kt          (déplacé)
    DecimalExpressionParser.kt (déplacé)
    GpsConverter.kt          (déplacé)
shared/src/commonMain/kotlin/mg/hydria/shared/network/
    HydriaHttpClient.kt      (nouveau, Ktor)
    dto/                     (nouveau, kotlinx.serialization)
```

**À modifier :**
```
app/build.gradle.kts         (ajouter implementation(project(":shared")))
app/.../calculator/AdvancedCalculatorActivity.kt   (appeler shared.calculator au lieu du code local)
app/.../calculator/CalculatorRepository.kt         (devient un wrapper fin vers shared, ou supprimé si redondant)
```

**À ne pas toucher dans cette phase :** `MainActivity.kt`, `TerrainDatabase.kt`, `OfflineStore.kt`, `navigation/`, `volume/` — tout le reste continue de fonctionner exactement comme avant.

---

## 7. Risques à surveiller

- **`MainActivity` (4388 lignes)** est le vrai goulot d'étranglement — Réparations et Planning ne pourront pas migrer proprement tant qu'ils n'en sont pas extraits en repositories/use-cases séparés. Prévoir ce nettoyage comme un chantier à part, avant la Phase 3, pas pendant.
- **Zéro test unitaire côté Kotlin** — chaque extraction vers `commonMain` se fait aujourd'hui sans filet ; vaut le coup d'ajouter des tests au moment de l'extraction (pas avant, pas de gros chantier de tests séparé).
- **MapLibre Android** n'a pas d'équivalent KMP mûr — c'est le module le plus susceptible de rester "deux implémentations UI parallèles derrière une interface" plutôt que vraiment partagé.
- **Double implémentation temporaire** (ancien `HydriaApi`/`TerrainDatabase` vs nouveau Ktor/SQLDelight) va cohabiter plusieurs semaines/mois — prévoir un flag ou un mécanisme de bascule propre par endpoint/domaine plutôt qu'un switch global.

---

## Prochaine étape possible

Si tu veux, je peux te préparer le contenu concret de la Phase 0 (structure `shared/build.gradle.kts`, `settings.gradle.kts` modifié, squelette Ktor respectant le form-encoding actuel) — dis-moi si tu veux que je commence par ça, ou si tu préfères d'abord qu'on regarde ensemble le détail de `MainActivity.kt` pour planifier son démantèlement avant tout le reste.
