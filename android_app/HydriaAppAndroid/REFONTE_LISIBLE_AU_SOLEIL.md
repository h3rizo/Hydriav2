# Hydria Terrain — refonte « Lisible au soleil »

Récapitulatif de la refonte visuelle et du comportement tablette de l'application
Android `mg.hydria.app`, d'après `Amélioration application Hydria Terrain/design_handoff_hydria_terrain/`.

Les 6 étapes du handoff sont implémentées. Chaque lot a été compilé avec succès
dans Android Studio avant de passer au suivant.

---

## Message de commit suggéré

```
Refonte Hydria Terrain « Lisible au soleil » (handoff, 6 étapes)

SOCLE
- Palette en ressources : values/ (clair) + values-night/ (sombre), mêmes noms,
  contrastes >= 4,5:1 ; thème Theme.HydriaApp en DayNight ; barres système
  suivant le mode (bools.xml)
- Typographie : Archivo (texte) + Roboto Mono (chiffres) via Google Fonts
  (res/font/, res/values/font_certs.xml)
- dimens.xml : cibles (64/68/56/48 dp), rayons, espacements, échelle typo
- HydriaVisuals.kt : couleurs lues dans les ressources (HydriaColors.bind),
  HydriaType (bind), enum Tone (ex-BadgeTone), fabriques taskRow / syncChip /
  chip / progressBar / accentedCard / styleNumeralInput / overline
- HydriaWindow.kt : WindowWidth (COMPACT/MEDIUM/EXPANDED), navigationRail,
  paneScaffold, gridColumns, supportsBatchSelection
- HydriaApp : Application, MODE_NIGHT_FOLLOW_SYSTEM
- bind() couleurs + polices en tête de chaque Activity ; retrait des
  window.statusBarColor en dur

TERRAIN
- En-tête : titre « Terrain » ; barre de sync pleine largeur -> pastille dans
  l'en-tête, restylée par updateStatus()
- Barre d'onglets 74 dp avec libellés (NavItem) + badge Réparations
- Carte de complétude : gros chiffre Roboto Mono + progressBar + 3 compteurs
- 2 boutons 64 dp (Carte cyan / Commencer ma tournée vase) ; filtres en chips
- 6 lignes de tâche via HydriaUi.taskRow (filet de criticité, chiffre à gauche)

RELEVÉ DE CAMPAGNE
- Champ d'index remonté en tête (indexCard), styleNumeralInput, unité m³
- Consommation calculée recalculée à chaque frappe
- Bouton « Enregistrer · point suivant » (suffixe atténué en Spannable), 64 dp

CENTRE DE SYNCHRONISATION
- Feuille modale BottomSheetDialog (poignée, coins hauts r26)
- 3 compteurs (relevés / photos / conflits), conflits en tête avec « Corriger »
  qui rouvre la saisie du point concerné ; bouton Journal ; ligne d'état

RÉPARATIONS / PLANNING / DÉPART DE CAMPAGNE / RECHERCHE / CALCULATRICE
- Réparations : retard en jours comme chiffre principal (colonne 46 dp),
  accentedCard, « ✓ Marquer terminée » pleine largeur 52 dp, terminée non
  synchronisée en opacity 0.75
- Planning : bande de jours en cases 52x64 (numéro monospace + puce de charge),
  agenda en accentedCard à filet coloré par type d'activité
- Départ de campagne : résumé du mois en tête (progressBar verte), une carte
  accentedCard + un bouton par ouvrage (Reprendre / Démarrer / Corriger)
- Recherche : champ 56 dp avec croix d'effacement (plus de bouton « Chercher »),
  onglets et filtres actifs en chips retirables, jeton de type 38 dp par
  résultat (PE/V/EQ/IN), filet rouge si intervention en retard, « N RÉSULTATS »
- Calculatrice : onglets en chips, références L1/L2 en jetons 34 dp, ligne
  active encadrée 2 dp cyan + résultat 26 sp, pavé 4 colonnes 56 dp

TABLETTE (largeur de fenêtre >= 600 dp)
- Rail de navigation vertical (navigationRail) + paneScaffold ; relayout dans
  onConfigurationChanged(), badge du rail rafraîchi après synchro
- Terrain : 2 volets (synthèse à gauche | liste de la catégorie à droite)
- Relevé : 2 volets (liste des points à gauche | formulaire à droite) +
  pavé numérique 3x4 intégré (numericKeypad), clavier système désactivé
- Colonnes MEDIUM (2) pour les lignes de tâche, les cartes d'ouvrage et les
  groupes de réparations (paneColumns / addInColumns)
- Navigation : HUD refait (cercle de cap 62 dp filet vase, distance en
  Roboto Mono 22 sp) ; légende -> filtres de couches actionnables 32 dp ;
  tablette = colonne fixe 392 dp à droite (HUD + « Autour de moi » 500 m)
- Recherche : 3 colonnes (facettes permanentes 300 dp | résultats 400 dp |
  fiche du résultat inline) ; les 2 AlertDialog de showFilters() disparaissent
  sur tablette ; SearchDetailActivity n'est plus poussée
- Calculatrice : menu d'onglets vertical 132 dp, pavé fixe 392 dp à droite,
  lignes en vrai tableau (L · libellé · expression · résultat · supprimer)
- Traitement par lot : barre de sélection multiple (compteur, Tout/Aucun) +
  cases teintées + bouton « Traiter la sélection » / « Tout traiter en série »
  (raccourci disponible aussi sur téléphone)
- Terrain EXPANDED : les items d'une catégorie deviennent un tableau
  (☐ · point · ouvrage · état · action) au lieu de cartes

NETTOYAGE
- Suppression de CompletionRingView, MiniBarsView, MiniBarEntry (remplacés par
  progressBar + taskRow) et des imports devenus inutiles
- Suppression de planningDateChipLabel et insertReference (code mort)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

---

## Fichiers touchés

### Nouveaux
- `app/src/main/java/mg/hydria/app/HydriaWindow.kt`
- `app/src/main/java/mg/hydria/app/HydriaApp.kt`
- `app/src/main/res/values-night/colors.xml`, `values-night/bools.xml`
- `app/src/main/res/values/dimens.xml`, `values/bools.xml`, `values/font_certs.xml`
- `app/src/main/res/font/archivo.xml`, `font/roboto_mono.xml`
- `REFONTE_LISIBLE_AU_SOLEIL.md` (ce fichier)

### Remplacés
- `app/src/main/java/mg/hydria/app/HydriaVisuals.kt`
- `app/src/main/res/values/colors.xml`, `values/themes.xml`
- `app/src/main/AndroidManifest.xml` (android:name=".HydriaApp")

### Modifiés
- `app/src/main/java/mg/hydria/app/MainActivity.kt` — Terrain, Relevé, Réparations,
  Planning, Départ de campagne, centre de sync, scaffold + rail tablette,
  Terrain/Relevé 2 volets, pavé numérique, colonnes MEDIUM, traitement par lot,
  tableau des points EXPANDED
- `app/src/main/java/mg/hydria/app/search/SearchActivity.kt` — champ 56 dp,
  chips, jetons de type, 3 volets tablette (facettes permanentes + fiche inline)
- `app/src/main/java/mg/hydria/app/search/SearchDetailActivity.kt` — rename Tone
- `app/src/main/java/mg/hydria/app/search/RecentInterventionsActivity.kt` — rename Tone
- `app/src/main/java/mg/hydria/app/calculator/AdvancedCalculatorActivity.kt` —
  onglets/pavé/lignes, menu vertical + pavé fixe + lignes en tableau (tablette)
- `app/src/main/java/mg/hydria/app/navigation/NavigationTerrainActivity.kt` —
  HUD refait, filtres de couches actionnables, colonne latérale tablette

## Reste à faire (non maquetté ou hors périmètre)

- Recherche : compteur par catégorie dans les facettes (pas de donnée côté API) ;
  la fiche inline se base sur le JSON du résultat, pas sur HydriaApi.searchDetail
  (donc pas de stats/histogramme)
- États vides, classe MEDIUM détaillée, tablette portrait, écran de connexion
- Remplacer les HydriaUi.badge() restants (~25 sites) par des chips au fil des
  reprises d'écran, puis retirer badge()/stylePrimary/styleSecondary/styleSpinner
