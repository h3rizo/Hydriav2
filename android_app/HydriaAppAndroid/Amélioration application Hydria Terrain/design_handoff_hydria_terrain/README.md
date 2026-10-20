# Handoff : Hydria Terrain — refonte visuelle et comportement tablette

## Vue d'ensemble

Refonte du design de **Hydria Terrain** (Android natif, `mg.hydria.app`, v2.3.1), l'application
terrain reliée à `www.hydria.mg` : agents relevant des index de compteurs, complétant des fiches
de points d'eau et d'équipements, et suivant des interventions, souvent hors connexion, en plein
soleil, à une main et avec des gants.

Direction retenue : **« Lisible au soleil »** — même architecture d'information que l'existant,
hiérarchie et contraste refaits, cibles tactiles élargies, mode clair et sombre automatiques,
et un comportement tablette à deux ou trois volets.

Ce qui change :

1. **Typographie** — Roboto remplacé par **Archivo** (texte) + **Roboto Mono** (tous les chiffres).
2. **Couleurs** — plus aucune constante en dur : `values/` (clair) et `values-night/` (sombre)
   portent les mêmes noms de ressource. Contrastes recalculés ≥ 4,5:1.
3. **Hiérarchie** — le chiffre passe à gauche en gros monospace ; la criticité passe par un filet
   de 3 dp en bord gauche de carte, jamais par le fond ; plus d'élévation ni d'ombre.
4. **Cibles** — 64 dp pour l'action principale, 68 dp pour une ligne de tâche, 34 dp minimum
   pour un filtre. Elles ne grandissent jamais avec l'écran.
5. **Synchronisation** — la barre orange pleine largeur devient une pastille permanente dans
   l'en-tête, qui ouvre un centre de synchronisation où les conflits remontent en premier.
6. **Tablette** — rail vertical de 92 dp, volets permanents, traitement par lot ; les boîtes de
   dialogue (filtres, factures, historique, fiche de résultat) disparaissent au profit de volets.

## À propos des fichiers de design

Les fichiers de ce bundle sont des **références de design réalisées en HTML** — des prototypes
qui montrent l'apparence et le comportement visés, **pas du code de production à copier**.

La cible est ici particulière : **le projet Android existe déjà**. Le travail n'est donc pas de
choisir un framework, mais de **retranscrire ces maquettes dans le code Kotlin/Views existant**
(`app/src/main/java/mg/hydria/app/`), qui construit ses écrans **programmatiquement** en
`LinearLayout` / `FrameLayout` — pas en XML de layout, sauf `activity_main.xml`.

Le dossier `implementation/` contient déjà la traduction Kotlin/XML de la spécification : ce sont
des fichiers **prêts à copier** dans `app/src/main/`. Voir `implementation/README.md`.

## Fidélité

**Haute fidélité (hifi).** Couleurs, tailles de police, graisses, rayons, hauteurs de cible et
espacements sont définitifs et listés ci-dessous en valeurs exactes. L'UI doit être reproduite
fidèlement, avec les composants Android natifs déjà en place — pas de nouvelle bibliothèque, pas
de Compose (le projet est en Views).

**Ce qui reste indicatif** : les fonds de carte (simulés en CSS dans les maquettes — la vraie
carte est celle de `NavigationTerrainActivity` avec son style `navigation_neutral_style.json`),
et les données affichées (noms d'ouvrages, index, montants) qui sont des exemples plausibles.

## Structure du document de design

Le fichier `Hydria Terrain.dc.html` s'ouvre directement dans un navigateur. Il est organisé en
**tours**, du plus récent (en haut) au plus ancien :

| Tour | Contenu |
| --- | --- |
| **6** | Les 3 écrans « manquants » en **tablette** : `6a` Relevés·départ, `6b` Recherche, `6c` Calculatrice |
| **5** | Écrans manquants en **téléphone** : `5a` Relevés·départ, `5b` Recherche, `5c` Calculatrice |
| **4** | **Comportement tablette** : `4a` Terrain, `4b` Relevé, `4c` Navigation, `4d` seuils et règles |
| **3** | **Spécification** : `3a` paires de couleurs, `3b` typographie, `3c` cibles et composants |
| **2** | Direction déployée : `2a` écrans restants en sombre, `2b` mode clair |
| **1** | Les 3 directions explorées : **`1a` retenue**, `1b` et `1c` écartées |
| **0** | **Recréation de l'existant** (v2.3.1) pour comparaison |

> Les tours `1b` et `1c` sont des directions **écartées** — ne pas les implémenter. Elles sont
> conservées pour comprendre pourquoi `1a` a été choisie.

---

## Écrans

Tous les écrans téléphone sont maquettés en **340 × 716 px** (≈ 360 × 760 dp), les écrans tablette
en **1 160 × 740 px** (tablette 10" en paysage).

### 1. Terrain — accueil (`1a`, `2b` en clair, `4a` en tablette)

**But** : l'agent voit l'état de son périmètre et ce qu'il reste à faire, puis démarre sa tournée.

**Structure téléphone**, de haut en bas, gouttière latérale **18 dp** :

1. **En-tête** (padding `6/18/14/18`, hauteur libre) : logo `hydria_vase_foreground` 36 dp,
   titre « Terrain » (Archivo 700, 19sp, `letter-spacing: -0.02em`) + sous-titre
   « RAKOTO Jean · Analalava » (Archivo 400, 11,5sp, `text_secondary`), **pastille de sync**
   (38 dp, rayon 19 dp) et bouton `⋮` (38 dp).
2. **Carte de complétude** (rayon 16 dp, `surface` + filet 1 dp `outline`, padding 18/18/16) :
   surtitre « COMPLÉTUDE DU PÉRIMÈTRE » (Archivo 600, 11sp, `+0.09em`), valeur **68** en
   Roboto Mono 700 **44sp** `-0.03em` avec « % » en Archivo 600 20sp cyan, « 47 tâches restantes »
   aligné à droite, barre de progression 10 dp, puis trois compteurs `12 ouvrages / 148 points /
   63 équip.` (chiffres en Roboto Mono 600 13sp).
3. **Deux boutons** de 64 dp, gap 10 dp : « Carte » (`flex: 1`, fond cyan) et
   « Commencer ma tournée » (`flex: 1.35`, fond vase).
4. **Rangée de filtres** : « À compléter » (Archivo 600 15sp) + 3 chips de 30 dp
   (Tout / Par ouvrage / Autour).
5. **Lignes de tâche**, gap 8 dp — le composant central du design :

   ```
   ┌─┬──────┬──────────────────────────────────┬───┐
   │▌│   6  │ Mesures de débit en retard       │ › │   68 dp
   │▌│      │ Échéance dépassée · 3 captages   │   │
   └─┴──────┴──────────────────────────────────┴───┘
    ▲   ▲
    │   └─ colonne 44 dp, chiffre aligné à DROITE,
    │      Roboto Mono 700 24sp, -0.03em, couleur = ton
    └─ filet 3 dp, couleur = ton (rouge / orange / vert)
   ```

   Titre Archivo 600 14,5sp, sous-titre Archivo 400 11,5sp `text_secondary`, chevron
   `text_muted` 20sp. Padding horizontal 16 dp, gap 14 dp. Ligne terminée : `✓` vert en Archivo
   700 17sp à la place du chiffre, pas de chevron, `opacity 0.7`, pas de clic.
6. **Barre d'onglets** 74 dp, fond `background_deep`, filet haut 1 dp : 4 onglets **avec libellé**
   (10,5sp), icône 22 dp, l'onglet actif sur une pastille `surface_raised` rayon 14 dp. Badge de
   17 dp sur Réparations (Roboto Mono 700 10sp, fond `error`, texte `on_accent`).

**Variantes** :
- **`2a` premier écran** — onglet « Par ouvrage » : une carte par ouvrage avec pourcentage coloré
  (vert/orange/rouge selon le seuil), chips de manques, et un **histogramme de 6 barres** de débit
  source (la dernière barre en cyan plein, les précédentes à `rgba(cyan, .35)`).
- **`4a` tablette** — trois colonnes : rail 92 dp, colonne de synthèse 400 dp (complétude, bouton
  de tournée, liste des catégories dont l'active est encadrée cyan), et **volet de détail** avec
  un tableau des points (grille `34px 1.6fr 1fr 108px 92px 128px`), **barre de sélection multiple**
  et actions par lot.

### 2. Relevé de campagne (`1a`, `2b` en clair, `4b` en tablette)

**But** : saisir l'index d'un point d'eau, point après point.

**Téléphone** — l'index est l'objet principal de l'écran :

1. En-tête : retour 38 dp, « Ambodivona » (Archivo 700 17sp) + « Campagne du 03/09/2026 »,
   bouton « Changer » 36 dp.
2. Progression : « Progression » / « 18 / 26 » (Roboto Mono 600 13sp, vert), barre 8 dp.
3. Carte du point : surtitre « POINT D'EAU · 19 SUR 26 », nom en Archivo 700 18sp, chevron 36 dp.
4. Deux cartes 14 dp côte à côte : « Dernier index » (Roboto Mono 700 17sp cyan + date) et
   « GPS agent » (`± 6 m` vert + « 12 m du point »).
5. **Champ d'index** — rayon 18 dp, fond `surface_raised`, **filet 2 dp cyan** :
   surtitre « NOUVEL INDEX » cyan + « min. 1 284 » à droite, valeur **1 337** en
   Roboto Mono 700 **46sp** `-0.04em`, curseur = trait cyan de 2 × 40 dp, unité « m³ » Archivo 500
   15sp ; séparateur 1 dp ; « Consommation calculée » / **+ 53 m³** (Roboto Mono 700 15sp, vert),
   recalculée à chaque frappe.
6. Trois actions secondaires de 52 dp : Photo (icône vase) / Remarque / Factures.
7. Bandeau d'avertissement rayon 14 dp, fond `warning_wash`, filet `rgba(warning, .4)` :
   « Fiche à compléter : photo manquante. Elle partira avec le relevé. »
8. Pied d'écran : bouton d'annulation 64 dp + **« Enregistrer · point suivant »** 64 dp cyan
   (le « · point suivant » en 13sp `rgba(ink, .6)` — l'enchaînement est annoncé).

**`4b` tablette** — trois volets : campagne à gauche (340 dp, liste des 26 points avec ceux déjà
saisis en `opacity .55` et leur valeur), saisie au centre (392 dp, champ + **pavé numérique 3×4
intégré**, cases rayon 13 dp, chiffres Roboto Mono 600 24sp), historique à droite (histogramme
12 mois, GPS, fiche, 3 dernières factures). Les factures ne sont plus un `AlertDialog`.

### 3. Navigation terrain (`1a`, `2b` en clair, `4c` en tablette)

**But** : rejoindre un point sur le terrain, marquer une position.

**Téléphone** : la carte occupe tout l'écran. En haut, retour 44 dp + champ de recherche 44 dp
(fond `rgba(background, .9)`, `backdrop-filter: blur(8px)`), puis une rangée de **filtres de
couches** de 32 dp avec leur puce de couleur — ils remplacent la légende non actionnable de la
v2.3.1. À droite, colonne de 4 boutons ronds de 52 dp (recentrer / nord / + / −).

En bas, un **panneau de guidage** (rayon 20 dp, `rgba(background, .96)`) : flèche de cap dans un
cercle de 62 dp (fond `rgba(vase, .15)`, filet 2 dp vase, `transform: rotate(<cap>deg)`),
surtitre « EN ROUTE », nom du point, **380 m** en Roboto Mono 700 22sp + « · 5 min · cap 24° » ;
puis « Marquer ma position » 56 dp vase + deux boutons carrés 56 dp ; enfin une ligne d'état
`GPS ±6 m · fond local · 3 en attente` avec sa puce verte.

**`4c` tablette** : le panneau devient une **colonne fixe de 392 dp à droite** — HUD en haut, puis
liste « Autour de moi » (rayon 500 m) triée par distance, chaque ligne avec sa puce de catégorie
et sa distance en Roboto Mono 700 13sp. La carte garde toute sa surface. Les indicateurs de bord
(`EdgeIndicatorsView`) restent pertinents pour ce qui sort du cadre.

### 4. Réparations (`2a`)

Filtres Échues / Hors périmètre / Terminées, puis des sections surtitrées (« EN RETARD »,
« SYNCHRONISATION EN ATTENTE »). Chaque carte : **retard en jours** comme chiffre principal
(`-9`, Roboto Mono 700 22sp, colonne 46 dp, avec « JOURS » en 9,5sp dessous), titre, lieu et date
prévue, badge de priorité (24 dp), et **« ✓ Marquer terminée »** en cible pleine largeur de 52 dp
dans la carte. Une intervention terminée non synchronisée reste visible en `opacity .75` avec la
mention « part à la prochaine sync ».

### 5. Planning (`2a`)

Bandeau horizontal de jours (cases 52 × 64 dp : abrév. 10sp, numéro Roboto Mono 700 20sp, puce de
charge 5 dp ; jour actif en cyan plein, week-end désaturé), puis un agenda en **colonne d'heures**
(52 dp, Roboto Mono 700 14sp) + carte d'activité à filet coloré par type.

### 6. Centre de synchronisation (`2a`)

Feuille modale (rayon haut 26 dp, fond `#0B1F28`, poignée 42 × 5 dp) ouverte par la pastille
d'en-tête. Titre « Travail en attente » + « Rien n'est perdu : tout est gardé sur le téléphone. »
Trois compteurs (relevés / photos / conflits, Roboto Mono 700 26sp). Puis la file, **conflits en
premier** avec leur action « Corriger » directe. Bouton « Synchroniser » 60 dp + bouton de journal
60 dp. Ligne d'état en pied.

### 7. Relevés · départ de campagne (`5a`, `6a` en tablette)

**But** : choisir l'ouvrage sur lequel relever — remplace le formulaire liste + menu déroulant +
date de la v2.3.1.

Le **résumé du mois** passe en tête (112 / 148, barre verte, `7 terminés / 4 en cours /
1 non commencé`), la date de campagne devient une ligne de 52 dp modifiable, puis chaque ouvrage
est une carte à filet coloré portant **son propre bouton** : « Reprendre la campagne » (cyan),
« Démarrer la campagne » (secondaire) ou « Corriger une saisie » pour un ouvrage terminé.
Le chiffre principal est la fraction `18/26` en Roboto Mono 700 20sp.

**`6a` tablette** : volet gauche = tableau de bord du mois avec un **histogramme des 12 ouvrages**
(vert terminé / orange en cours / rouge non commencé) et un rappel des 3 relevés en attente ;
volet droit = grille **2 colonnes** de cartes d'ouvrage + une carte en pointillés
« 7 ouvrages terminés masqués ».

### 8. Recherche (`5b`, `6b` en tablette)

Champ de 56 dp **pleine largeur** avec filet cyan et croix d'effacement (plus de bouton
« Chercher » séparé : la recherche est déjà différée dans `SearchActivity`), onglets
Tout / Personnes / Ouvrages de 38 dp, filtres actifs en **jetons retirables**, et un compteur
« 14 RÉSULTATS ». Chaque résultat porte un **jeton de type de 38 dp** — `PE` cyan, `V` violet,
`EQ` vase, initiales pour une personne, `IN` rouge pour une intervention — ce qui manquait pour
lire une liste mixte d'un coup d'œil. Une intervention en retard prend le filet rouge.

**`6b` tablette** : trois volets. Facettes permanentes à gauche (300 dp) — cases à cocher de
catégorie **avec leur compteur**, sélecteurs de périmètre/district/commune de 48 dp, bouton de
réinitialisation : les deux `AlertDialog` de `showFilters()` disparaissent. Résultats au centre
(392 dp). **Fiche du résultat à droite** — en-tête avec jeton 56 dp et actions
« ◎ M'y rendre » / « Relever l'index », 4 cartes de stat, histogramme 12 mois, factures.
`SearchDetailActivity` n'est plus poussée sur tablette.

### 9. Calculatrice avancée (`5c`, `6c` en tablette)

**Téléphone** : onglets Calculs / Salaire / Devis / Total / Caisse (36 dp, défilement horizontal),
bouton `AC` dans l'en-tête. Les lignes précédentes restent visibles **en compact** au-dessus
(`opacity .65`, `L1` + libellé + expression + résultat), la ligne active est mise en avant
(rayon 16 dp, filet 2 dp cyan, résultat en Roboto Mono 700 26sp vert). Les **références L1/L2
deviennent des jetons de 34 dp à toucher** plutôt qu'un bouton « Réf. » par carte. Pavé
**4 colonnes**, cases de 56 dp, opérateurs sur fond `surface_raised` en cyan, `= Ligne suivante`
sur 2 colonnes.

**`6c` tablette** : les six onglets (dont **GPS**) passent en **menu vertical de 132 dp** — plus
de bande à faire défiler. Les lignes deviennent un vrai **tableau** (grille
`48px 1.1fr 1.5fr 168px 44px` : ligne / libellé / expression / résultat / supprimer), résultats
alignés à droite en monospace, ligne en erreur avec filet rouge et message
« Division par zéro » à la place du résultat. Pavé **fixe à droite** (392 dp) surmonté des jetons
de référence : on saisit sans que la liste bouge.

---

## Interactions et comportement

### Navigation

- **Téléphone** : 4 onglets en bas, navigation par empilement (comportement actuel inchangé).
- **Tablette** : rail vertical à gauche, mêmes onglets dans le même ordre, mêmes libellés.
  Le contenu s'ouvre **dans le volet de droite** au lieu d'être poussé sur la pile.
- La pastille de sync de l'en-tête (ou du bas du rail) ouvre le **centre de synchronisation**.

### Enchaînement de saisie

« Enregistrer · point suivant » enregistre **et** charge le point suivant de la campagne, sans
retour à la liste. Sur tablette, le volet de gauche met simplement à jour la ligne saisie
(passage en `opacity .55` avec sa valeur) et surligne la suivante.

Sur `1a`, toucher une ligne de tâche « Photos de points manquantes » **enchaîne les prises** :
appareil photo → point suivant, sans repasser par la liste.

### États

- **Hors ligne** — la pastille passe en `error` avec la mention « Hors ligne · reprise
  automatique ». Rien n'est bloquant : toute la saisie reste possible, elle est mise en file.
- **Conflit de synchronisation** — un relevé refusé par le serveur (index inférieur au dernier
  connu) remonte **en tête** du centre de sync, filet rouge, avec un bouton « Corriger » qui
  rouvre la saisie du point concerné.
- **Fiche incomplète** — bandeau `warning_wash` sur l'écran de relevé, et compteur « 1 manque »
  dans la carte de fiche sur tablette.
- **Tâche terminée** — `✓` vert, `opacity .7`, plus cliquable, pas de chevron.
- **Hors de portée** — sur le tableau tablette, un point à plus de ~1 km affiche « Trop loin »
  en `text_muted` au lieu du bouton d'action, et sa distance passe en `warning`.
- **Liste vide** — non maquetté ; à traiter (voir « Reste à faire »).

### Animations

Aucune animation nouvelle. Le ripple des composants Material est conservé
(`HydriaUi.ripple()`, `rgba(<accent>, .19)`). Pas de transition de volet sur tablette : le
contenu du volet est remplacé directement — plus rapide et plus lisible en plein soleil.

### Accessibilité

Chaque composant du fichier `HydriaVisuals.kt` fourni pose son `contentDescription` :
`taskRow` → « <titre>, <n> restant(s) » ou « <titre>, terminé » ; `syncChip` → « <n> action(s) à
synchroniser, toucher pour ouvrir le centre de synchronisation » / « Hors ligne, <n> action(s)
conservée(s) sur ce téléphone » / « Synchronisation à jour » ; `progressBar` → « <n> pour cent
complet » ; les chevrons décoratifs sont en `IMPORTANT_FOR_ACCESSIBILITY_NO`.

### Comportement responsive

Trois classes de largeur de **fenêtre** (pas d'écran — le multi-fenêtre et les pliables comptent) :

| Largeur utile | Classe | Comportement |
| --- | --- | --- |
| `< 600 dp` | `COMPACT` | un volet, onglets en bas, navigation par empilement |
| `600–839 dp` | `MEDIUM` | rail vertical 92 dp, un seul volet, listes en 2 colonnes, pas de tableau ni de sélection multiple |
| `≥ 840 dp` | `EXPANDED` | rail + 2 ou 3 volets, tableau, sélection multiple, dialogues remplacés par des volets |

**Trois règles à ne pas contourner** :

1. Les cibles tactiles **ne grandissent pas** avec l'écran : 64 dp reste 64 dp. C'est la quantité
   d'information visible qui augmente, pas la taille des boutons.
2. Aucun contenu ne s'étire au-delà de **720 dp** de large : les volets ont des largeurs fixes
   (300 / 340 / 392 / 400 dp) et c'est le volet de détail qui absorbe le reste.
3. Rien n'est **exclusif** à la tablette côté métier. Le traitement par lot est un raccourci,
   jamais le seul chemin : un agent sur téléphone doit pouvoir tout faire.

## Gestion d'état

Aucun nouveau modèle de données. Les états déjà présents dans `MainActivity` / `store.snapshot`
suffisent. S'ajoutent uniquement des états d'**interface** :

- `windowWidth: WindowWidth` — recalculé dans `onConfigurationChanged()`.
- `selectedCategory: String?` — quelle catégorie de tâche remplit le volet de détail (`EXPANDED`).
- `selectedIds: Set<String>` — sélection multiple du tableau ; toujours vide hors `EXPANDED`.
- `activeFacets` / `activeScope` — facettes de recherche, désormais persistantes à l'écran plutôt
  que dans un dialogue.
- `selectedResultId: String?` — quel résultat remplit la fiche de droite (`EXPANDED`).

Aucun nouvel appel réseau. Le calcul de consommation en direct (`nouvel index − dernier index`)
est purement local, comme la validation d'index minimum déjà en place.

## Design tokens

### Couleurs — mêmes noms, deux valeurs

| Ressource | Clair | Sombre |
| --- | --- | --- |
| `hydria_background_deep` | `#FFFFFF` | `#050F14` |
| `hydria_background` | `#F4F7F8` | `#08171F` |
| `hydria_surface` | `#FFFFFF` | `#0E2029` |
| `hydria_surface_raised` | `#F4F9FA` | `#14313C` |
| `hydria_outline` | `#D2E0E4` | `#22414D` |
| `hydria_outline_soft` | `#E2EBEE` | `#1B3843` |
| `hydria_text` | `#07151D` | `#FFFFFF` |
| `hydria_text_secondary` | `#4A6570` | `#9FBAC4` |
| `hydria_text_muted` | `#7A929B` | `#5D7C88` |
| `hydria_cyan` | `#0E7E90` | `#55D9E7` |
| `hydria_cyan_strong` | `#0A5F6E` | `#1AA9BE` |
| `hydria_cyan_wash` | `#E6F3F5` | `#14313C` |
| `hydria_vase` | `#C96F10` | `#F29A38` |
| `hydria_vase_wash` | `#FBEEDE` | `#2A1F12` |
| `hydria_success` | `#1E8A56` | `#58D594` |
| `hydria_success_wash` | `#F0F7F3` | `#11291F` |
| `hydria_warning` | `#A86A10` | `#F1B15B` |
| `hydria_warning_wash` | `#FDF3E3` | `#2D271E` |
| `hydria_error` | `#C0392B` | `#FF7777` |
| `hydria_error_wash` | `#FBEDED` | `#2C1A1A` |
| `hydria_on_accent` | `#FFFFFF` | `#07151D` |

**Couleurs cartographiques — ne basculent PAS** (un point d'eau garde son cyan dans les deux modes,
pour que la légende reste apprise) : `hydria_map_village #6C5BD4` (sombre `#9B8AFB`),
`hydria_map_point #0E7E90` / `#55D9E7`, `hydria_map_equipment #C96F10` / `#F29A38`,
`hydria_map_landmark #1E8A56` / `#58D594`.

### Typographie

**Règle unique : tout chiffre qu'on compare ou qu'on saisit est en Roboto Mono. Le reste est en
Archivo.** Les deux passent par le fournisseur de polices Google — rien à embarquer dans l'APK.

| Rôle | Police | Taille | Détail |
| --- | --- | --- | --- |
| Valeur héro | Roboto Mono 700 | 44sp | `letter-spacing -0.03em` |
| Valeur de saisie | Roboto Mono 700 | 46sp (34sp en champ) | `-0.04em` |
| Chiffre de ligne | Roboto Mono 700 | 24sp | `-0.03em`, colonne 44 dp alignée à droite |
| Titre d'écran | Archivo 700 | 19sp | `-0.02em` |
| Titre d'écran tablette | Archivo 700 | 24–26sp | `-0.02em` |
| Titre de carte | Archivo 600/700 | 16–18sp | |
| Titre de ligne | Archivo 600 | 14,5sp | |
| Corps | Archivo 400 | 13sp | |
| Métadonnée | Archivo 400 | 11,5–12sp | `text_secondary` |
| Surtitre de section | Archivo 600 | 10,5–11sp | `letter-spacing +0.09em`, majuscules |
| Libellé d'onglet | Archivo 500/600 | 10,5sp | |

### Cibles et rayons (`dimens.xml`)

| Token | Valeur |
| --- | --- |
| `hydria_target_min` | 48 dp |
| `hydria_target_row` | 68 dp |
| `hydria_target_form` | 56 dp |
| `hydria_target_primary` | 64 dp |
| `hydria_target_nav` | 74 dp |
| `hydria_radius_card` | 16 dp |
| `hydria_radius_row` / `_field` | 14 dp |
| `hydria_radius_button` | 16 dp |
| `hydria_radius_pill` | 19 dp |
| `hydria_radius_sheet` | 26 dp |
| `hydria_accent_bar` | 3 dp |
| `hydria_hairline` | 1 dp |
| `hydria_gutter` | 18 dp |
| `hydria_gap` | 8 dp |
| `hydria_gap_section` | 14 dp |
| `hydria_card_padding` | 16 dp |
| `hydria_numeral_column` | 44 dp |

Largeurs de volet tablette : rail **92 dp**, facettes **300 dp**, campagne **340 dp**,
saisie / panneau latéral **392 dp**, liste **400 dp**. Menu vertical de la calculatrice **132 dp**.

### Ombres et élévation

**Aucune.** Une carte = `hydria_surface` + filet 1 dp `hydria_outline`, `elevation = 0f`,
`stateListAnimator = null`. Seule exception, en mode **clair** uniquement : les panneaux posés
**sur la carte** prennent une ombre portée (`0 4px 20px rgba(7,21,29,.16)`) au lieu d'être
translucides — un panneau translucide est illisible sur un fond de carte chargé au soleil.

## Assets

| Asset | Provenance |
| --- | --- |
| `assets/hydria_vase.png` | `app/src/main/res/drawable-xxxhdpi/hydria_vase_foreground.png` — déjà dans le projet |
| Icônes d'onglet | `ic_terrain.xml`, `ic_readings.xml`, `ic_repairs.xml`, `ic_planning.xml` — déjà dans le projet, réutilisées telles quelles (les SVG des maquettes en sont la transcription) |
| Archivo, Roboto Mono | Fournisseur de polices Google (`com.google.android.gms.fonts`) — voir `implementation/res/font/` |

Aucun asset nouveau à produire. Les glyphes de la maquette (`◎ ◉ ✎ ⌕ ✛ ⤼ ⌫`) sont des
substituts typographiques : côté Android, utiliser des `VectorDrawable`, en reprenant le style
des icônes existantes (trait plein, 22–24 dp, `viewBox 24`).

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `Hydria Terrain.dc.html` | **Le document de design.** S'ouvre dans un navigateur ; tours 0 à 6 |
| `support.js` | Runtime du document de design — nécessaire pour l'ouvrir, sans intérêt pour l'implémentation |
| `assets/hydria_vase.png` | Logo utilisé dans les maquettes |
| `implementation/README.md` | **Instructions de copie et 3 branchements** à faire côté code |
| `implementation/res/values/colors.xml` | Palette mode clair — **remplace** l'existant |
| `implementation/res/values-night/colors.xml` | Palette mode sombre — nouveau |
| `implementation/res/values/dimens.xml` | Cibles, rayons, espacements, échelle typo — nouveau |
| `implementation/res/values/themes.xml` | Thème en DayNight — **remplace** l'existant |
| `implementation/res/values/bools.xml`, `values-night/bools.xml` | Barres système claires/sombres |
| `implementation/res/font/archivo.xml`, `roboto_mono.xml` | Polices téléchargeables |
| `implementation/java/mg/hydria/app/HydriaVisuals.kt` | **Remplace** l'existant : couleurs lues dans les ressources + fabriques de composants |
| `implementation/java/mg/hydria/app/HydriaWindow.kt` | Nouveau : classes de largeur, rail, `paneScaffold()` |

### Captures (`screenshots/`)

Rendus PNG à l'échelle 1× de chaque option du document, pour lire les maquettes sans ouvrir le
HTML. Le HTML reste la référence en cas de doute (les captures sont un rendu DOM, certains effets
CSS peuvent y être approximatifs).

| Fichier | Contenu |
| --- | --- |
| `0-existant-v2.3.1.png` | L'existant recréé — point de comparaison |
| `1a-telephone-terrain-releve-navigation.png` | **La direction retenue** : Terrain, Relevé, Navigation |
| `2a-telephone-ouvrages-reparations-planning-sync.png` | Par ouvrage, Réparations, Planning, centre de sync |
| `2b-telephone-mode-clair.png` | Les 3 mêmes écrans en mode clair |
| `3a-specification-tokens.png` | Paires de couleurs, échelle typo, cibles et composants |
| `4a-tablette-terrain-lot.png` | Tablette — Terrain + traitement par lot |
| `4b-tablette-releve-trois-volets.png` | Tablette — Relevé en trois volets |
| `4c-tablette-navigation.png` | Tablette — Navigation, panneau latéral |
| `4d-seuils-et-regles.png` | Seuils 600/840 dp et les 3 règles |
| `5a-telephone-releves-depart.png` | Départ de campagne |
| `5b-telephone-recherche.png` | Recherche |
| `5c-telephone-calculatrice.png` | Calculatrice avancée |
| `6a-tablette-releves-depart.png` | Départ de campagne en tablette |
| `6b-tablette-recherche.png` | Recherche en tablette |
| `6c-tablette-calculatrice.png` | Calculatrice en tablette |

### Fabriques de composants disponibles

`HydriaUi.taskRow(count, title, subtitle, tone, onClick)` · `syncChip(pending, online)` ·
`chip(label, active)` · `progressBar(percent, accent)` · `primaryButton()` · `secondaryButton()` ·
`card()` · `accentedCard(tone)` · `styleInput()` · `styleNumeralInput()` · `overline()`.

`HydriaWindow.of(activity)` · `navigationRail(tabs, selectedId, footer)` ·
`paneScaffold(activity, width, navigation, content, detail)` · `gridColumns(width)` ·
`supportsBatchSelection(width)` · `showsDetailInline(width)` · `paneHeader()`.

Ce qu'elles remplacent : `CompletionRingView` → `progressBar()` + grand chiffre ;
les cartes d'indicateur assemblées à la main dans `renderTerrainTodo()` → `taskRow()` ;
la barre de sync pleine largeur → `syncChip()` ; les boutons de mode → `chip()` ;
`BadgeTone` → `Tone` (remplacement global, mêmes valeurs) ; `HydriaUi.badge()` → supprimé.

## Ordre d'implémentation suggéré

1. **Socle** — copier `res/` et les deux fichiers Kotlin, appeler `HydriaColors.bind(this)` /
   `HydriaType.bind(this)` dans `onCreate()`, activer `MODE_NIGHT_FOLLOW_SYSTEM`, renommer
   `BadgeTone` → `Tone`, retirer les `window.statusBarColor` en dur. À ce stade tout compile et
   l'app change déjà de peau, sans refonte d'écran.
2. **Terrain** — réécrire `renderTerrain()` / `renderTerrainTodo()` avec `taskRow()` et
   `progressBar()`, remplacer la barre de sync par `syncChip()`, ajouter les libellés d'onglet.
3. **Relevé** — remonter le champ d'index en tête, `styleNumeralInput()`, consommation en direct,
   « Enregistrer · point suivant ».
4. **Centre de synchronisation** — nouvelle feuille, conflits en premier.
5. **Réparations, Planning, Départ de campagne, Recherche, Calculatrice** — même système.
6. **Tablette** — `paneScaffold()` + rail, puis les volets écran par écran, puis le traitement
   par lot en dernier (c'est un raccourci, pas un prérequis).

## Reste à faire (non maquetté)

- **États vides** et premier lancement (aucune campagne, aucun ouvrage, aucun résultat).
- **Classe `MEDIUM` (600–839 dp)** : décrite dans les règles, pas dessinée.
- **Tablette en portrait** : les maquettes tablette sont toutes en paysage.
- Onglets **Salaire / Devis / Total / Caisse / GPS** de la calculatrice : seul « Calculs » est
  maquetté, en téléphone et en tablette.
- Écran de **connexion** (`showLogin()`) : hors périmètre demandé.
- Remplacement des glyphes typographiques par de vrais `VectorDrawable`.
