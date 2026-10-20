# Hydria Terrain — direction « Lisible au soleil »

Fichiers prêts à copier dans `app/src/main/`. Ils remplacent l'existant sans
changer les contrats API ni le fonctionnement hors connexion.

## À copier

| Fichier | Destination | Nature |
| --- | --- | --- |
| `res/values/colors.xml` | `res/values/colors.xml` | remplace — **mode clair** |
| `res/values-night/colors.xml` | `res/values-night/colors.xml` | nouveau — mode sombre |
| `res/values/bools.xml`, `res/values-night/bools.xml` | idem | nouveaux — barres système |
| `res/values/dimens.xml` | `res/values/dimens.xml` | nouveau — cibles, rayons, type |
| `res/values/themes.xml` | `res/values/themes.xml` | remplace — passe en DayNight |
| `res/font/archivo.xml`, `res/font/roboto_mono.xml` | `res/font/` | nouveaux — polices téléchargeables |
| `java/mg/hydria/app/HydriaVisuals.kt` | idem | remplace |
| `java/mg/hydria/app/HydriaWindow.kt` | idem | nouveau — téléphone / tablette |

## Trois branchements à faire côté code

1. **Mode clair/sombre auto** — dans la classe `Application` (ou en tête de
   `MainActivity.onCreate`) :
   `AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM)`.

2. **Résolution des couleurs** — `HydriaColors` n'est plus un jeu de constantes ;
   appeler `HydriaColors.bind(this)` et `HydriaType.bind(this)` au début de
   `onCreate()` de chaque Activity, avant la première vue. Les appels existants
   (`HydriaColors.text`, `HydriaColors.cyan`…) continuent de compiler.
   Supprimer les `window.statusBarColor = …` en dur : le thème s'en charge.

3. **Renommage d'enum** — `BadgeTone` devient `Tone` (mêmes valeurs).
   Un simple remplacement global suffit. `HydriaUi.badge()` disparaît au profit
   de `HydriaUi.chip()` / `HydriaUi.syncChip()` / `HydriaUi.taskRow()`.

## Ce que les nouvelles fabriques remplacent

- `CompletionRingView` → `HydriaUi.progressBar()` + grand chiffre monospace.
- les cartes d'indicateur assemblées à la main dans `renderTerrainTodo()` →
  `HydriaUi.taskRow(count, title, subtitle, tone, onClick)`.
- la barre de sync pleine largeur (`syncStatus`) → `HydriaUi.syncChip()` dans
  l'en-tête, qui ouvre `showSyncCenter()`.
- les boutons de mode `À FAIRE / PAR OUVRAGE / AUTOUR` → `HydriaUi.chip()`.
- `MiniBarsView` reste utilisable, mais n'est plus nécessaire : les six lignes
  de tâche portent déjà le chiffre.

`SparklineView` peut rester tel quel ; la maquette propose un histogramme à
6 barres (plus lisible au pouce), à faire dans un second temps.

## Comportement tablette (`HydriaWindow.kt`)

Trois classes de largeur de **fenêtre** (pas d'écran — le multi-fenêtre compte) :

| Largeur | Classe | Coquille |
| --- | --- | --- |
| `< 600dp` | `COMPACT` | un volet + onglets en bas — inchangé |
| `600–839dp` | `MEDIUM` | rail vertical 92dp + un volet, listes en 2 colonnes |
| `≥ 840dp` | `EXPANDED` | rail + volet liste + volet détail, sélection multiple |

Branchement dans `showApplication()` :

```kotlin
val width = HydriaWindow.of(this)
val rail = if (width.isTablet) HydriaWindow.navigationRail(this, tabs, currentScreen.name) else bottomTabs
detailPane = if (width.isTwoPane) FrameLayout(this) else null
setContentView(HydriaWindow.paneScaffold(this, width, rail, content, detailPane))
```

Les `render*()` ne changent pas : ils reçoivent le conteneur d'un volet au lieu
de `content`. Trois garde-fous à respecter :

- `HydriaWindow.supportsBatchSelection(width)` — la sélection multiple et la
  barre d'actions par lot n'existent qu'en `EXPANDED`. C'est un raccourci, jamais
  le seul chemin : tout reste faisable point par point sur téléphone.
- `HydriaWindow.showsDetailInline(width)` — en `EXPANDED`, `showInvoicesDialog()`
  et l'historique remplissent le volet de droite au lieu d'ouvrir un `AlertDialog`.
- `HydriaWindow.gridColumns(width)` — 1 / 2 / 3 colonnes. Les cibles tactiles ne
  grandissent pas : 64dp reste 64dp, c'est la densité d'information qui augmente.

Recalculer dans `onConfigurationChanged()` (rotation, mode fenêtré, pliables) —
et déclarer `android:configChanges` ou accepter la recréation d'Activity.
