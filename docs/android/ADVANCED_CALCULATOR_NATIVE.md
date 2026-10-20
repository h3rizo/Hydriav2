# Calculatrice avancée native Android Hydria

## Inventaire de l'existant

### Web et backend

- Le modal Web est défini dans `backend/templates/base.html`.
- Ses brouillons historiques utilisent `hydria.calculator.memory.v1` et `hydria.calculator.cashbooks.v1` dans le stockage du navigateur.
- Le simulateur Web appelle `/config/tranches-irsa/api/simuler-salaire/`.
- La source métier est `GrilleSalaire.calculer_tous_les_champs()` avec `ConfigSalaire` et `ConfigTrancheIRSA`.
- Les règles constatées sont : CNaPS salarié à 1 % plafonnée à huit fois le salaire minimum, mutuelle identique à la CNaPS, base imposable arrondie vers le bas à 100 Ar, IRSA par tranches puis déduction et minimum, net arrondi `HALF_UP` à 100 Ar.
- Les gardiens utilisent un diviseur horaire de 240. Les taux de nuit, dimanche, férié, décret, premier mai et remplacement proviennent désormais du contrat synchronisé.

### Android

- Application : `android_app/HydriaAppAndroid`, package `mg.hydria.app`.
- Interface native AppCompat construite avec les composants `HydriaUi` et les couleurs `HydriaColors`.
- Client réseau unique : `HydriaApi`.
- Session unique : `OfflineStore` et jeton mobile existant.
- Base locale unique : `TerrainDatabase`, basée sur `SQLiteOpenHelper`.
- Synchronisation globale : `MainActivity.synchronize()`, déclenchée au démarrage, manuellement et au retour du réseau.
- Cartographie existante : MapLibre dans `NavigationTerrainActivity`, avec style en ligne OpenFreeMap et style neutre embarqué de secours.
- Aucun ViewModel, Room, WorkManager, thème clair ou gestionnaire de lots de tuiles hors ligne n'existait dans l'application auditée.

## Intégration retenue

La calculatrice est un écran AppCompat natif accessible depuis le menu Outils. Elle réutilise la session, la base SQLite, la synchronisation et MapLibre. Aucun WebView, moteur JavaScript, `eval`, second client HTTP ou second stockage n'a été ajouté.

| Web | Android natif |
|---|---|
| Calculs mémorisés | Parseur Kotlin décimal strict, lignes L1…L1000 et pavé natif |
| Simulateur de salaire | `SalaryEngine`, configuration locale signée par checksum |
| Mode devis | `QuoteCalculator`, 500 lignes maximum |
| Mode total | `TotalCalculator`, 500 lignes et 100 critères |
| Cahier de caisse | `CashCalculator`, 1 000 lignes, 100 critères et 200 instantanés nommés |
| Coordonnées GPS | `GpsConverter`, presse-papiers, URI cartographique et MapLibre |

Toutes les saisies sont enregistrées dans `calculator_state`, avec une clé de compte normalisée. Les résultats calculés ne sont pas des données de référence : ils sont recalculés au chargement.

## Synchronisation salariale

L'endpoint authentifié en lecture seule est :

```text
GET /mobile/api/salary-calculation-config/
```

Il expose des montants sous forme de chaînes décimales, les tranches IRSA, les taux et diviseurs effectivement lus par le moteur Django, la version, la date d'effet, la version de formule et un SHA-256 du JSON canonique.

Android transmet le checksum actif. Si la configuration est inchangée, le serveur ne renvoie pas le corps complet. Une nouvelle configuration est contrôlée avant écriture : checksum, version de formule, champs obligatoires, valeurs positives, ordre et bornes des tranches. L'activation est transactionnelle. Un rejet conserve la dernière version valide.

La version de formule prise en charge est `1`. Une version inconnue n'est jamais activée et l'interface affiche qu'une mise à jour de l'application est nécessaire. Les changements de taux, plafonds et tranches ne demandent pas de nouvelle version Android.

Le modèle Django actuel est un singleton global et ne porte pas de configurations futures. Le contrat indique donc honnêtement `organisation: global`, `status: active` et une liste future vide. La table Android est tout de même indexée par compte, organisation et version afin de ne pas bloquer une future évolution du backend.

## GPS et fonctionnement hors ligne

La conversion DMS/décimale, la validation, les copies et la restauration du brouillon ne dépendent pas du réseau. MapLibre tente le style en ligne existant et bascule vers `navigation_neutral_style.json` en mode hors ligne ou en cas d'échec. Le marqueur et le choix d'un point restent utilisables sur ce fond neutre.

L'application auditée ne contient pas de gestionnaire de lots de tuiles versionnés. Aucun second gestionnaire concurrent n'a été créé dans la calculatrice. La fourniture et la mise à jour de lots cartographiques détaillés restent donc une limite d'infrastructure distincte ; les données métier et la Navigation Terrain existantes ne sont pas modifiées.

## Validation

Commandes utilisées :

```powershell
$env:DEBUG='True'
..\.venv\Scripts\python.exe manage.py check
..\.venv\Scripts\python.exe manage.py test apps.core.tests_mobile_salary --keepdb --noinput

$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
$env:ANDROID_HOME='C:\Users\Dir Soakoja\AppData\Local\Android\Sdk'
.\gradlew.bat testDebugUnitTest assembleDebug lintDebug --no-daemon --console=plain
```

Les tests Kotlin couvrent le parseur, la cascade des références, les limites, la persistance, Devis, Total, Caisse, le moteur salarial et la conversion GPS. Les tests Django couvrent l'authentification, le contrat décimal et la réponse différentielle par checksum.

## Fichiers principaux

### Android créés

- `calculator/AdvancedCalculatorActivity.kt`
- `calculator/CalculatorModels.kt`
- `calculator/CalculatorRepository.kt`
- `calculator/DecimalExpressionParser.kt`
- `calculator/BusinessModels.kt`
- `calculator/SalaryConfigRepository.kt`
- `calculator/SalaryEngine.kt`
- `calculator/GpsConverter.kt`
- tests Kotlin correspondants dans `app/src/test/java/mg/hydria/app/calculator/`
- traductions malgaches dans `res/values-mg/strings.xml`

### Android modifiés

- `MainActivity.kt`
- `HydriaApi.kt`
- `OfflineStore.kt`
- `TerrainDatabase.kt`
- `AndroidManifest.xml`
- `res/values/strings.xml`
- `app/build.gradle.kts`

### Backend

- `apps/core/views_mobile_salary.py`
- `apps/core/tests_mobile_salary.py`
- `apps/core/urls.py`

## Limites de validation visuelle

La compilation, les tests et le lint sont automatisés sur ce poste. Les captures finales téléphone/tablette et les gestes MapLibre nécessitent un émulateur démarré ou un appareil Android connecté. Elles ne doivent pas être présentées comme validées tant que ce support n'est pas disponible.
