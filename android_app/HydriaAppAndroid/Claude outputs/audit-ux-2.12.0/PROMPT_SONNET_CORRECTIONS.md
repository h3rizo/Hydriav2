# Consignes pour les corrections de l'audit UX (sessions Sonnet)

Ce fichier est destiné à une session Claude Code configurée sur **Sonnet**. On lui donne en une ligne le lot à traiter (voir « Comment lancer » en fin de fichier). Elle lit alors ce fichier en entier, applique les règles communes, puis réalise **uniquement** le lot demandé.

---

## 1. Règles communes (à appliquer pour tous les lots)

### Contexte
- App Android **Hydria Terrain** 2.12.0, package `mg.hydria.app`. Racine : `C:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\android_app\HydriaAppAndroid`.
- Interface en **Vues Android construites en Kotlin programmatique** : ni layouts XML, ni Compose. Le système de design est dans `app/src/main/java/mg/hydria/app/HydriaVisuals.kt` (`HydriaColors`, `HydriaType`, `HydriaUi`, `Tone`) et `HydriaWindow.kt`.
- Le métier est partagé avec l'app Desktop dans le module KMP `shared/` (`commonMain`, `jvmCommonMain`, tests dans `commonTest` et `desktopTest`). Une règle métier va dans `shared`, avec son test, et l'app Android ne fait que l'appeler.
- L'audit de référence se trouve dans `Claude outputs/audit-ux-2.12.0/` :
  - `AUDIT_UX_HYDRIA_TERRAIN_2.12.0.md` : la synthèse ;
  - `ANNEXE_CONSTATS.md` : le détail de chaque constat, avec preuve, impact et recommandation. **Avant de traiter un identifiant, lis son entrée dans l'annexe.**

### Avant chaque correction
1. **Revérifie que le défaut existe toujours.** L'app évolue vite et les numéros de ligne de l'annexe ont bougé : relocalise le code avec Grep. Si le défaut est déjà corrigé, note-le « déjà corrigé » et passe au suivant.
2. **Vérifie qu'aucune autre session ne travaille sur le fichier.** Si un fichier que tu dois modifier a été changé dans les 30 dernières minutes et que ce n'est pas toi, arrête-toi et demande avant de continuer.
3. **Fais une sauvegarde.** Il n'y a pas de git dans ce dossier. Avant la première modification d'un fichier, copie-le dans `work/backup-<lot>/<AAAAMMJJ-HHMM>/<chemin relatif>`. Pas de `.bak` dans `src/`.

### Style et périmètre
- **Changements minimaux**, dans le style du code voisin : mêmes helpers (`dp()`, `text()`, `HydriaUi.*`), même densité de commentaires. Pas de refactoring hors du périmètre du constat.
- **Nouveaux textes d'interface** : en français, codés en dur comme le code voisin. La traduction en malgache fait l'objet d'un lot à part, ne la commence pas ici. Exception : si le fichier utilise déjà `R.string`, ajoute la chaîne dans `values/strings.xml` **et** `values-mg/strings.xml`.
- **Nouveau composant réutilisable** : dans `HydriaVisuals.kt` (`HydriaUi`), pas en copie locale.
- **« Aujourd'hui »** se calcule toujours avec `ZoneId.of("Indian/Antananarivo")`.
- **Ne touche pas à** :
  - le backend Django : si une correction exige un changement serveur, décris-le dans le compte rendu sans le faire ;
  - `versionCode` / `versionName` ;
  - le déploiement et les APK ;
  - le dossier du design handoff ;
  - l'interface Compose de `desktopApp/`, que tu dois seulement garder compilable.
- **Décisions produit : ne pas trancher seul.** Demande avant POINTAGE-02, REP_PLAN-02 (côté serveur), TERRAIN-08, CALC_VOL-08 et CALC_VOL-09.

### Build et tests (obligatoires en fin de lot)
Lance-les depuis l'outil **PowerShell**. Bash échoue sur ce PC avec l'erreur « Unable to establish loopback connection ». Si le bac à sable bloque, utilise `dangerouslyDisableSandbox`. PowerShell 5.1 ne connaît pas `&&` : enchaîne avec `;`.

```powershell
$env:JAVA_TOOL_OPTIONS = "-Djdk.net.unixdomain.tmpdir=C:\tmp"; .\gradlew.bat :shared:desktopTest :shared:testDebugUnitTest :app:testDebugUnitTest :app:assembleDebug
```

Si `shared/` a changé, ajoute `:desktopApp:compileKotlin`. Le premier build à froid prend 5 à 7 minutes. Corrige les échecs, et rapporte la sortie réelle sans l'enjoliver.

### Compte rendu de fin de lot
- Un tableau `Id | Statut (corrigé / déjà corrigé / reporté + raison) | Fichiers modifiés | Test ajouté`.
- Le résultat réel du build et des tests.
- La liste des vérifications à faire **à la main sur le téléphone**. Ne prétends jamais avoir testé sur appareil.
- Les changements serveur nécessaires, le cas échéant.
- Pas de commit ni de déploiement.

---

## 2. Lot 1-A — Ne plus perdre la saisie

Fichier principal : `MainActivity.kt`, plus `shared/.../readings/ReadingValidation.kt`.

1. **COEUR-01 — La fin de synchro efface le relevé en cours.**
   - **À faire** : dans le `runOnUiThread` de fin de `synchronize()`, ne pas appeler `renderCurrentScreen()` ni `showApplication(false)` si `currentScreen == READINGS` et `campaignOuvrageId != null`. Ne faire alors que `updateStatus()`. Le snapshot reste mis à jour dans le store, et l'écran sera reconstruit à la prochaine navigation.
   - **Critère d'acceptation** : un index tapé pendant un envoi n'est ni effacé ni déplacé vers un autre point.
2. **COEUR-07 (+ volet Retour de TERRAIN-10) — Retour quitte l'application.**
   - **À faire** : ajouter un `onBackPressedDispatcher.addCallback`. Il ferme d'abord la campagne active (même effet que « Changer »), puis l'élément ou la catégorie Terrain ouverte, puis ramène vers l'onglet Terrain depuis un autre onglet. À la racine : « Appuyez encore pour quitter », avec double appui sous 2 s.
   - Mémoriser `campaignOuvrageId`, `campaignOuvrageNom` et `campaignDate` dans les préférences déjà utilisées par l'app. Les restaurer au démarrage si l'ouvrage existe toujours dans le snapshot.
3. **COEUR-08 — Déconnexion sans confirmation.**
   - **À faire** : avant « Se déconnecter », afficher la confirmation « Se déconnecter ? Vous aurez besoin d'internet pour vous reconnecter et recharger votre tournée. », avec « Annuler » par défaut.
4. **COEUR-02 — Remarque obligatoire non contrôlée.**
   - **Règle partagée** : dans `ReadingValidation`, une remarque devient obligatoire si la consommation est nulle **ou** si le volume non facturé est différent de 0. C'est la règle de `backend/apps/billing/views_releves.py`, vers les lignes 2982 et 2988 (à lire, pas à modifier). Ajoute les tests correspondants dans `ReadingValidationTest`.
   - **Côté app** : appliquer la règle dans `prepareReading`, avec `remark.error`. Le libellé devient « Remarque (obligatoire) » quand la règle s'applique, recalculé dans `refreshConsumption()`.
   - **Centre de synchro** : pour un relevé refusé par le serveur (erreur HTTP 400, qui n'est pas un conflit), proposer « Corriger », qui appelle `openReadingCorrection`, comme pour les conflits.
   - Vérifie que l'écran Relevés du Desktop, qui utilise `ReadingValidation`, compile toujours.
5. **REP_PLAN-04 — Formulaire perdu en touchant à côté.**
   - **À faire** : dans les éditeurs de planning et de réparation, appeler `setCanceledOnTouchOutside(false)`. Ajouter un indicateur « formulaire modifié » alimenté par des TextWatcher et les listeners de Spinner. « Annuler » ou Retour demandent alors « Abandonner la saisie ? ».
   - Afficher les erreurs sur le champ concerné quand c'est possible, et garder le toast seulement en dernier recours.

## 3. Lot 1-B — Lisibilité au soleil

Fichiers principaux : `HydriaVisuals.kt` et `res/values{,-night}/colors.xml`, puis les écrans concernés.

1. **TERRAIN-14 — Coins colorés parasites.**
   - **À faire** : dans `accentedCard`, donner `cornerRadius = radius` sur les 4 coins de la couche barre, à la place des `cornerRadii` actuels qui laissent les coins droits carrés.
2. **TERRAIN-05 + REP_PLAN-11 — Colonnes de chiffres.**
   - **À faire** : colonne du chiffre de `taskRow` et colonne de retard de la carte de réparation en `WRAP_CONTENT`, avec `minWidth` égal à la largeur actuelle et `maxLines = 1`. Ajouter l'autosize `TextViewCompat.setAutoSizeTextTypeUniformWithConfiguration` (14 à 24 sp).
   - **Critère d'acceptation** : « 1282 » tient sur une ligne.
   - **Retard** : le libellé est calculé dans `shared`, dans `RepairRules` ou équivalent, avec un test. Il affiche « 224 j » avec la mention « RETARD » en couleur d'erreur, « dans 5 j » pour une échéance future, et « AUJ. » pour le jour même. Plus de signe négatif.
3. **REP_PLAN-14 — Badge de l'onglet Réparations.**
   - **À faire** : ne compter que les réparations échues (`overdueDays > 0`). Le badge « 99+ » doit s'afficher en entier : `clipChildren = false` sur les conteneurs, ou une translation.
   - Le `contentDescription` doit correspondre à ce qui est compté.
4. **TRANSVERSE-03 — Contraste du mode clair.**
   - **À faire** : appliquer dans `values/colors.xml` (mode clair seulement) les jetons proposés par l'annexe :
     - `hydria_text_secondary #3A525C` ;
     - `hydria_text_muted #52707C` ;
     - nouveaux jetons de texte de ton : `hydria_cyan_text #0A5F6E`, `hydria_success_text #0F6B3F`, `hydria_warning_text #7A4A00`, `hydria_vase_text #8F4600`, `hydria_error_text #A32E22` ;
     - `hydria_field_outline #7F9AA4`.
   - En mode sombre, les jetons de texte prennent la même valeur que l'accent actuel, pour que le rendu sombre ne change pas.
   - Les lier dans `HydriaColors.bind`. Utiliser les jetons de texte pour tout **texte** coloré par un ton sur une surface : chips, badges, pastille de synchro, compteurs de `taskRow`. Ne pas les utiliser pour les fonds.
5. **TRANSVERSE-05 — Cibles tactiles.**
   - **À faire** : dans `HydriaUi.chip`, garder la hauteur visuelle mais donner une zone tactile de 48 dp (InsetDrawable vertical autour du fond arrondi, `minHeight` 48 dp). Pastille de synchro et bouton ⋮ également à 48 dp. Supprimer les `dp(30)` des puces de l'écran Terrain.
6. **POINTAGE-06 — Bouton de pointage désactivé illisible.**
   - **À faire** : créer `HydriaUi.disabledButton(button)`, qui garde un texte opaque (`textSecondary`) sur un fond `surfaceRaised` avec contour, **sans** `alpha`. L'utiliser pour le bouton de pointage désactivé dans `PointageActivity`.

## 4. Lot 1-C — Carte, calculatrice, volumétrique

1. **RECH_NAV-02 — HUD de navigation illisible en mode clair.**
   - **À faire** : dans `NavigationTerrainActivity` et `EdgeIndicatorsView`, remplacer les fonds codés en dur `Color.argb(..., 7, 21, 29)` par une couleur de surface du thème (`HydriaColors.surface` à alpha 238, ou un nouveau jeton `hydria_map_overlay` dans `values` et `values-night`).
   - **Critère d'acceptation** : textes lisibles dans les deux thèmes.
2. **RECH_NAV-01 — Villages et grappes de la carte non cliquables.**
   - **À faire** : dans `selectAt()`, interroger un rectangle de ±24 dp autour du doigt sur les couches entités, villages et grappes, et garder l'élément le plus proche du doigt. Toucher une grappe zoome de +2 sur son centre.
   - Ajouter dans `MarkerLayerManager` une SymbolLayer qui affiche `point_count_abbreviated` sur les grappes.
3. **CALC_VOL-04 — « AC » efface les cahiers de caisse.**
   - **À faire** : le bouton « AC » de l'en-tête devient « Tout effacer » et conserve les cahiers de caisse nommés. Sinon, la confirmation doit annoncer combien de cahiers seront supprimés. La touche « AC » du pavé devient « C ».
4. **CALC_VOL-06 — Le pourcentage divise par 100.**
   - **Règle partagée** : dans le parseur d'expressions de `shared`, `A + B%` = A × (1 + B/100) et `A − B%` = A × (1 − B/100). Ailleurs, le `%` garde son sens actuel : « 200 × 15% » et « 50% » seul ne changent pas.
   - Ajouter les tests (le module est partagé avec le Desktop).
5. **CALC_VOL-02 — Un refus bloque la synchro du volumétrique.**
   - **À faire** : dans `VolumeActivity.synchronize()`, traiter chaque élément dans son propre try/catch et continuer la file. Appeler toujours la suite (récapitulatif) à la fin. Préfixer le message d'erreur par l'ouvrage, le mois et le montant de l'opération concernée.

## 5. Lot 1-D — Dates

1. **Composant date.**
   - **À faire** : créer `HydriaUi.dateField(context, initialIso, maxToday = true, onChange)`. C'est un champ non saisissable au clavier, qui affiche JJ/MM/AAAA, ouvre un `DatePickerDialog` au toucher et garde l'ISO en interne. Si `maxToday` est vrai, la date maximale est aujourd'hui, au fuseau Madagascar.
2. **Remplacer les saisies de date au clavier** :
   - date de campagne dans le départ de campagne ;
   - formulaires Débit source et Compteur de tête (TERRAIN-07, partie date seulement) ;
   - éditeurs de planning et de réparation (REP_PLAN-10) ;
   - encaissement volumétrique (CALC_VOL-01, qui demande aussi de mémoriser et présélectionner le dernier journal) ;
   - formulaire de planning du Pointage, s'il comporte une date.
3. **Validation partagée.** Dans `shared`, `PlanningFormRules` et `RepairFormRules` doivent valider une date **réelle** : « 2026-02-30 » est refusé. Ajouter les tests.

---

## 5 bis. Décisions de l'utilisateur (20 octobre 2026) — prévalent sur les règles ci-dessus

1. **Version et diffusion** : ne pas changer la version et ne rien diffuser avant la fin du lot 2.
2. **POINTAGE-02, créneaux « prévus »** : ils sont **prévus par défaut selon l'activité du planning**. Par exemple, matinée et après-midi pour une activité de terrain. C'est un changement serveur (Django, `backend/apps/planning/`), désormais autorisé **en local seulement**.
3. **REP_PLAN-02, statut « planifie »** : **migrer les plannings importés vers un statut existant**, à savoir `en_cours`, seul statut ouvert parmi `en_cours`, `termine`, `annule` et `reporte`. On le fait par une migration de données Django, écrite et testée en local.
4. **Seuil de précision GPS (L2-6)** : **rester à 100 m**, et accepter au-delà après confirmation explicite, à cause de l'imprécision des GPS d'entrée de gamme. Le seuil est une constante unique dans `shared`.
5. **Desktop** : **aligner l'app Desktop au fil des chantiers**. Sont concernés la remarque obligatoire, le libellé du retard, le sélecteur de date, et les équivalents de chaque chantier du lot 2. La modification de l'interface Compose de `desktopApp/` est donc désormais **autorisée**, pour l'alignement seulement.
6. **Ordre des chantiers** : celui du tableau ci-dessous.
7. **Clé anti-doublon (L2-3)** : **oui**. Chaque création faite hors ligne (planning, réparation, et tout autre élément créé depuis le téléphone) porte une clé générée par le téléphone (UUID). Le serveur ignore une seconde création portant la même clé et renvoie l'élément déjà créé. C'est un changement serveur, autorisé **en local seulement**, avec les garde-fous ci-dessous ; s'il nécessite une migration, la signaler.

**Garde-fous serveur** :
- aucune modification sur le VPS, aucun `migrate` en production, aucun déploiement ;
- toute migration Django créée doit être signalée dans le compte rendu, l'utilisateur veut être prévenu avant de l'appliquer en production ;
- tests serveur avec `python manage.py test <module> --testrunner django.test.runner.DiscoverRunner`, depuis `backend/` ;
- ne pas lancer `migrate` sur la base de développement locale, qui a d'autres migrations en retard.

## 5 ter. Plans L2-1 et L2-2 validés (20 octobre 2026, 09:10)

L'utilisateur a validé les deux plans et toutes les recommandations (`PLANS_L2-1_L2-2.md`, questions 1 à 9). Les plans complets sont la référence de ces deux chantiers.

**L2-1**
1. Touche « ✓ » du clavier sur l'index : elle **ferme seulement le clavier**. Elle n'enregistre pas. Même chose pour la touche Entrée sur Desktop.
2. Barre du bas : **« Enregistrer · point suivant » en principal**, « Calculer et imprimer (80 mm) » en secondaire.
3. Choix du point : **bloc repliable simple** dans la page. Pas de feuille du bas.
4. Relevé quitté sans enregistrer : **le brouillon est gardé sans question**, avec un toast « Saisie gardée en brouillon ». À la réouverture du point, le bandeau « Brouillon repris » s'affiche. La boîte « Abandonner la saisie ? » du lot 1 disparaît pour Retour et « Changer ». Durée de vie d'un brouillon : jusqu'à la fermeture de la campagne, **3 jours au plus**.
5. Clavier ouvert sur l'écran de relevé en campagne : **masquer l'en-tête et la barre d'onglets**, seulement sur cet écran.

**L2-2**
6. Seuils, chacun dans une seule constante dans `shared` :
   - consommation **> 5 fois** la moyenne du point ;
   - au moins **3 relevés** à consommation positive ;
   - excédent **> 10 m³** ;
   - plafond **500 m³** sans historique fiable ;
   - distance au point : **250 m**.
7. Consommation nulle : **pas de boîte en plus**. La remarque obligatoire suffit.
8. Valeur extrême : **simple confirmation** pour tout le monde, sans blocage réservé au Directeur.
9. Fenêtre d'annulation : **8 secondes**.

## 6. Lot 2 — Chantiers de fond (un chantier par session)

Une session par chantier, dans cet ordre. Même méthode : lire les entrées de l'annexe, sauvegarder, appliquer les règles communes, build et tests, compte rendu. Pour chacun, **commence par proposer un plan court et attends mon accord avant de coder**, car ce sont des changements de structure.

| Chantier | Constats | Point d'attention |
|---|---|---|
| L2-1 Formulaire de relevé réordonné + barre « Enregistrer · point suivant » fixe + brouillon | COEUR-03, COEUR-01 (brouillon) | Ne pas casser le mode tablette 2 volets ni le pavé intégré |
| L2-2 Garde-fous de plausibilité + « Annuler » après enregistrement | COEUR-04 | Réutiliser `ReadingPrintRules.deviation` ; seuils dans `shared` avec tests |
| L2-3 `PendingOverlay` (saisies en file visibles partout) + clés d'idempotence | REP_PLAN-03, POINTAGE-04, COEUR-05 | La clé d'idempotence demande peut-être un changement serveur : le décrire |
| L2-4 Centre de synchronisation lisible + pastille unique | COEUR-06, POINTAGE-08, TRANSVERSE-08 | Classer réseau / refus / conflit ; « Supprimer » dans « Plus d'options » |
| L2-5 « Mes pointages aujourd'hui » (reçu, motif de refus) + case « prévu » clarifiée + créneaux prévus par défaut selon l'activité | POINTAGE-03, POINTAGE-01, POINTAGE-02 | POINTAGE-02 : décision du §5 bis (serveur, en local seulement) |
| L2-6 Feuille de capture GPS partagée (précision, seuil, délai max) | TERRAIN-01, RECH_NAV-03, POINTAGE-13 | Modèle : onglet GPS de la calculatrice ; seuil de **100 m** en constante dans `shared`, au-delà avec confirmation (§5 bis) |
| L2-7 Série Terrain en barre persistante + tournée par point puis par distance | TERRAIN-03, TERRAIN-04, TERRAIN-10 | `buildTourTasks` est dans `shared` |
| L2-8 `HydriaFormat` (Ariary, m³, dates, pluriels, vide) + table des statuts + migration « planifie » → `en_cours` | TRANSVERSE-02, -07, -09, CALC_VOL-07, REP_PLAN-02 | Partir de `ReadingTicketFormat` ; remplacer d'abord les écrans les plus vus ; REP_PLAN-02 : migration de données du §5 bis |
| L2-9 Cascade d'activité avec « — Choisir — » en création | REP_PLAN-01 | L'employé connecté est déjà présélectionné ; ne pas le casser |

---

## 7. Comment lancer

Ouvre une **nouvelle** session Claude Code dans le dossier `android_app/HydriaAppAndroid`, choisis le modèle **Sonnet**, puis colle la ligne du lot voulu.

**Fais les lots un par un, dans l'ordre**, jamais deux sessions en même temps : ils modifient les mêmes fichiers (`MainActivity.kt`, `HydriaVisuals.kt`).

```text
Lis entièrement « Claude outputs/audit-ux-2.12.0/PROMPT_SONNET_CORRECTIONS.md », applique ses règles communes et réalise uniquement le lot 1-A.
```

Pour les lots suivants, remplace `1-A` par `1-B`, `1-C`, `1-D`. Pour le lot 2, utilise le libellé du chantier, par exemple : « réalise uniquement le chantier L2-1 ».
