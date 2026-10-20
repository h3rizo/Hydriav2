# Audit UX — Hydria Terrain 2.12.0

**Date** : 19 octobre 2026
**Périmètre** : application Android `mg.hydria.app`, version 2.12.0 (versionCode 57), tous les écrans.
**Dimensions auditées** : esthétique, ergonomie, cohérence du workflow, rendu des données.
**Détail des 93 constats** : [ANNEXE_CONSTATS.md](ANNEXE_CONSTATS.md). Chaque constat y figure avec preuve dans le code, impact, recommandation et statut de vérification.

---

## 1. En une page

**Verdict.** Le socle est bon, et la refonte « Lisible au soleil » a tenu ses promesses là où elle a été appliquée :
- grands chiffres en police mono ;
- filet de criticité à gauche des cartes ;
- boutons principaux de 52 à 64 dp ;
- mode sombre très contrasté (texte 16 à 18:1) ;
- file hors ligne rassurante ;
- règles métier partagées et testées.

Les problèmes qui restent sont rarement esthétiques. Ce sont surtout des problèmes de **confiance**. L'agent peut perdre ce qu'il vient de saisir, ne pas voir qu'une saisie a été refusée, ou lire une donnée de travers. Trois facteurs aggravent ces défauts : le terrain (réseau lent, soleil, une main), un téléphone d'entrée de gamme (police système à 0,85) et un périmètre réel bien plus gros que celui des maquettes (3 601 tâches et 401 ouvrages, contre 47 tâches).

**Les 5 constats critiques** (tous confirmés sur le code 2.12.0, aucune tentative de réfutation n'a abouti) :

| # | Constat | Pourquoi c'est grave |
|---|---|---|
| COEUR-01 | La fin de chaque synchronisation reconstruit l'écran Relevés et efface la saisie en cours. Le point sélectionné revient au premier de la liste. | À chaque relevé en ligne, l'index tapé pendant l'envoi peut disparaître, ou être enregistré sur le mauvais point. |
| REP_PLAN-03 | Plannings et réparations saisis hors ligne : invisibles avant la synchro, réédités sur des valeurs périmées, créations sans clé d'idempotence. | Doublons et corrections annulées sans bruit : l'inverse de ce que promet l'offline-first. |
| POINTAGE-02 | Un créneau n'est « prévu » que si on le déclare pendant le créneau. Les rappels ne partent presque jamais et un pointage manqué n'est jamais compté. | Données de présence fausses, alors qu'elles servent aux indemnités. |
| POINTAGE-03 | Un pointage hors ligne refusé plus tard disparaît sans explication, et aucun reçu n'est conservé. | L'agent le découvre à la fiche d'indemnité du mois, sans preuve. |
| RECH_NAV-02 | En thème clair, le HUD de navigation affiche un texte sombre sur un fond sombre codé en dur. | Distance et cible invisibles de jour, c'est-à-dire précisément dans la condition visée. |

**Les 10 chantiers à plus fort rendement** (détail au §4) :

1. **Garde de rendu pendant la saisie** (COEUR-01). Moins d'une demi-journée.
2. **Retour Android qui remonte d'un niveau** au lieu de quitter l'app, avec mémorisation de la campagne en cours (COEUR-07, TERRAIN-10). Moins d'une demi-journée.
3. **Un sélecteur de date unique** à la place des cinq champs « AAAA-MM-JJ » (campagne, débit, planning, réparation, encaissement).
4. **Un formateur de données unique** `HydriaFormat` pour les montants, volumes, dates, pluriels et valeurs vides (TRANSVERSE-02, -07, -09, CALC_VOL-07).
5. **Formulaire de relevé réordonné** : index en haut et barre « Enregistrer · point suivant » fixe en bas, pour passer de 5 à 9 gestes par relevé à 2 ou 3 (COEUR-03), avec des garde-fous de plausibilité (COEUR-04).
6. **Superposition de la file hors ligne** sur toutes les listes : la saisie apparaît tout de suite avec la mention « en attente d'envoi » (REP_PLAN-03, POINTAGE-04, COEUR-05).
7. **Centre de synchronisation lisible** : noms au lieu d'identifiants, panne réseau distinguée d'un refus, « Corriger » pour tout refus (COEUR-06, COEUR-02).
8. **Une feuille de capture GPS partagée**, avec précision affichée et seuil, pour le point d'eau, la position marquée sur la carte et le pointage (TERRAIN-01, RECH_NAV-03, POINTAGE-13).
9. **Lisibilité au soleil, deuxième passe** : jetons de contraste du mode clair, cibles de 48 dp, échelle typographique à 6 rôles (TRANSVERSE-03, -04, -05, RECH_NAV-02, POINTAGE-06).
10. **Écran d'accueil « Aujourd'hui »** au lieu de la complétude du périmètre, avec le Pointage intégré à la navigation (COEUR-10, POINTAGE-05, POINTAGE-09).

---

## 2. Ce qu'il faut préserver

Ces choix sont bons et doivent servir de référence aux écrans ajoutés depuis la refonte.

- **La carte NOUVEL INDEX** : cadre cyan de 2 dp, gros chiffres mono, rappel « min. 130,67 », consommation recalculée à la frappe, rouge immédiat si l'index est inférieur au précédent ([capture 09](captures/09_releve_saisie.png)).
- **La liste des points de relevé** : libellé « idxls — abonné · index précédent », tri numérique (2 avant 10), points déjà relevés masqués par défaut, recherche par nom ou idxls, mode « proches de moi ».
- **L'offline-first** : mise en file immédiate, phrase « Rien n'est perdu : tout est gardé sur le téléphone », conflits remontés en tête avec « Corriger » et « Comparer », double confirmation avant « Forcer » ou « Supprimer » ([capture 15](captures/15_sync_center.png)).
- **Le langage visuel tonal** : l'enum `Tone`, le filet de criticité à gauche (et non le fond qui change de couleur), le grand chiffre à gauche de chaque ligne de tâche.
- **Le mode sombre** : texte 16,7–18,2:1, secondaire 8,2–8,9:1, accents 7,5–9,9:1.
- **La sécurité de l'argent** : calculs en BigDecimal, serveur qui fait foi, factures encaissées non sélectionnables, version de devis vérifiée, file idempotente.
- **La calculatrice**, seule partie entièrement traduite en malgache, et son onglet GPS : meilleure position sur 30 s, objectif de 20 m. C'est ce modèle qu'il faut généraliser (§3.1).
- **Le pointage côté contrôle** : position simulée détectée, précision maximale de 100 m, bouton dans une barre fixe qui explique pourquoi on ne peut pas pointer.

---

## 3. Les thèmes de fond

Les 93 constats se regroupent en 8 thèmes. Pour chacun : le diagnostic, puis le principe de correction. Une correction d'architecture règle en général plusieurs constats d'un coup.

### 3.1 Ne jamais perdre ni fausser le travail de l'agent

C'est le thème le plus important : il contient les 5 critiques et une quinzaine de majeurs.

**Diagnostic**
- **Saisie effacée** :
  - par la synchronisation, en plein relevé (COEUR-01) ;
  - par un dialogue de 10 à 11 champs qui se ferme d'un toucher à côté (REP_PLAN-04) ;
  - par le bouton Retour, qui quitte l'app (COEUR-07) ;
  - par « Se déconnecter », qui efface toute la tournée hors ligne sans confirmation (COEUR-08) ;
  - par la rotation de l'écran ou le retour de l'appareil photo sur la carte (RECH_NAV-04).
- **Saisie invisible ou dédoublée** :
  - les plannings et réparations en file n'apparaissent nulle part (REP_PLAN-03) ;
  - le planning ajouté hors ligne n'apparaît pas au Pointage (POINTAGE-04) ;
  - la progression de campagne est fausse en ligne et la ressaisie crée un doublon (COEUR-05).
- **Saisie acceptée puis refusée en silence** :
  - remarque obligatoire (consommation nulle ou volume non facturé) non contrôlée dans l'app : le serveur refuse en 400, le relevé reste en erreur dans la file et compte comme « fait » dans la campagne. Le centre de synchro ne propose que « Supprimer » ; le seul chemin de correction passe par « Voir mes saisies » dans l'écran Relevés (COEUR-02) ;
  - pointage refusé qui disparaît (POINTAGE-03) ;
  - nom d'abonné que le serveur juge encore manquant (TERRAIN-09).
- **Saisie fausse sans alerte** :
  - GPS d'un point enregistré au premier signal, même s'il ne vient que du réseau mobile (TERRAIN-01). Le serveur refuse désormais au-delà de 2 km, ce qui borne le risque sans régler la précision ;
  - même problème pour « Marquer une position » sur la carte (RECH_NAV-03) ;
  - employé et activité présélectionnés d'office dans l'éditeur de planning (REP_PLAN-01, partiellement corrigé : l'employé connecté est désormais proposé) ;
  - statut « planifie » réécrit en « En cours » à chaque modification (REP_PLAN-02) ;
  - « % » qui divise par 100, donc « 5000 + 7% » donne 5 000,07 (CALC_VOL-06) ;
  - suppression d'une ligne de calcul qui décale toutes les références Ln (CALC_VOL-05) ;
  - « Confirmer l'impression réalisée » verrouille des factures jamais imprimées (CALC_VOL-09).

**Principe de correction : quatre mécanismes communs plutôt que 20 rustines**

1. **Garde de rendu.** Aucune reconstruction d'écran pendant qu'un formulaire est en cours de saisie. La fin de synchro ne met alors à jour que la pastille. Un brouillon (`readingDraft`) est réappliqué si l'écran doit quand même être reconstruit.
2. **Superposition de la file** (`PendingOverlay.apply(items, store.pending())` dans `shared`). Elle fusionne les opérations en attente dans toutes les listes (relevés, plannings, réparations, pointage), avec la mention « En attente d'envoi » et une clé d'idempotence générée sur le téléphone.
3. **Refus serveur réparable.** Tout refus 400 ou 422 devient « Refusé : <motif> » avec « Corriger », comme les 409 aujourd'hui. Les règles serveur déjà connues sont portées dans `shared`, pour attraper l'erreur dès la saisie : remarque obligatoire, nom d'abonné, date réelle.
4. **Feuille de capture GPS unique.** Elle reprend le modèle de l'onglet GPS de la calculatrice :
   - écoute de 30 à 60 s ;
   - précision affichée en gros (« ± 23 m » en vert, orange ou rouge) ;
   - « Enregistrer » actif seulement sous un seuil partagé ;
   - boutons « Réessayer », « Passer » et « Arrêter ».

   Elle sert au Terrain, à la carte et au Pointage.

### 3.2 La tâche répétitive d'abord : le relevé

**Diagnostic**
- Le champ de l'index arrive sous 7 blocs et « Enregistrer » est à environ deux écrans plus bas. Cela fait 5 à 6 gestes par relevé, et 8 à 9 si le point suivant n'est pas en tête de liste : plus de 300 gestes de navigation pour un ouvrage de 53 points (COEUR-03, [captures 09 et 10](captures/09_releve_saisie.png)).
- Un champ affiche seulement « 0 », sans libellé (le volume non facturé). Il y a aussi deux notions de GPS concurrentes : « Capturer ma position » pour l'agent et « Ajouter le GPS » pour le point ([capture 10](captures/10_releve_saisie_scroll.png)).
- Aucun garde-fou contre la faute de frappe, au-delà de « index inférieur au précédent » (COEUR-04).
- Le départ de campagne aligne 52 cartes avec chacune un gros bouton, et la date se tape au format ISO ([capture 02](captures/02_releves.png)).

**Principe de correction : réordonner `renderCampaignReading`**
1. Bandeau compact du point : abonné, type, « dernier 130,67 · min. ».
2. Carte NOUVEL INDEX avec le focus et le pavé numérique à l'ouverture ; consommation et volume facturé juste dessous.
3. Barre fixe en bas, hors du défilement : « Enregistrer · point suivant », avec « Facture 80 mm » en action secondaire.
4. Tout le reste en dessous, replié : enrichissement GPS/photo/téléphone, remarque, anciennes factures.

À l'enregistrement, un contrôle de plausibilité ouvre une confirmation nommée : « Leonce : index 1 300, soit +1 170 m³ (moyenne 12 m³). Corriger / Confirmer ». Il se déclenche si la consommation dépasse 5 fois la moyenne, si elle est nulle alors que la moyenne est positive, ou si l'index a gagné des chiffres. La fonction `ReadingPrintRules.deviation` existe déjà dans `shared`. Après chaque relevé, un bandeau « Relevé enregistré · Annuler » reste visible 4 s.

Le même principe s'applique aux autres séries :
- la série Terrain devient une barre persistante « 12 / 48 · PE-042 » avec « Passer », au lieu d'un dialogue à chaque élément (TERRAIN-04) ;
- toucher une carte de la liste ouvre l'élément au lieu de cocher la case (TERRAIN-10) ;
- « Marquer terminée » devient un bouton tonal avec une confirmation nommée et « Annuler » (REP_PLAN-05).

### 3.3 Dire clairement ce qui se passe

**Diagnostic**
- **Centre de synchronisation** : il affiche des UUID et des erreurs réseau brutes, et traite une panne passagère comme une « Erreur », avec « Supprimer » pour seule action (COEUR-06).
- **Pastilles** :
  - la pastille « … » n'a pas de sens clair ;
  - celle du Pointage dit « à jour » alors que des opérations attendent, et ne se touche pas (POINTAGE-08) ;
  - hors ligne, « à jour » s'affiche en rouge (TRANSVERSE-08).
- **Synchronisation de l'écran volumétrique** : le premier refus bloque toute la file et masque le récapitulatif de l'encaissement en cours (CALC_VOL-02).
- **Confirmations** :
  - sur la carte, elles disparaissent en une seconde ;
  - l'arrivée à destination ne propose aucune suite (RECH_NAV-10).
- **Complétude Terrain** :
  - le pourcentage ne bouge pas hors ligne, alors que « tâches restantes » baisse (TERRAIN-06) ;
  - les compteurs sont des totaux qui se lisent comme des restes.

**Principe de correction**
- **Une seule implémentation de pastille** (`HydriaUi.syncChip`) pour tous les écrans. Elle a quatre états en mots : « À jour », « 3 en attente », « Hors ligne · 3 gardés », « 1 refusé ». Elle est toujours cliquable et ouvre le centre.
- **Dans le centre**, chaque ligne affiche « Relevé · 10 — Leonce · Ambanja ». Les erreurs sont classées en trois groupes : *en attente de réseau* (ton neutre, nouvel essai automatique), *refusé* (« Corriger ») et *conflit* (« Comparer »). « Supprimer » passe dans « Plus d'options ».
- **Les confirmations** passent par un bandeau Snackbar de 4 s, avec annonce TalkBack, au lieu d'un toast.

### 3.4 Architecture d'information et navigation

**Diagnostic**
- **Accueil** : l'app s'ouvre sur la complétude du périmètre (27 %, 3 601 tâches) plutôt que sur le travail du jour (COEUR-10, [capture 01](captures/01_accueil.png)). « Tournée » y a trois sens différents.
- **Onglet Pointage** : il ouvre une Activity séparée, sans barre de navigation ([capture 05](captures/05_pointage.png)). Depuis la notification, Retour quitte l'app (POINTAGE-05). Trois points d'entrée tiennent trois discours différents sur le pointage (POINTAGE-09).
- **Planning** : la carte « Aucun planning aujourd'hui » s'affiche à côté de « 8 RDV » le même jour, parce qu'elle parle de l'agent alors que l'agenda montre l'équipe (REP_PLAN-09, [capture 04](captures/04_planning.png)).
- **Menu ⋮** : c'est une liste de texte qui cache la calculatrice, le volumétrique et la carte (COEUR-11).
- **Activities** : chacune a son propre en-tête et sa propre façon de revenir en arrière (COEUR-11).
- **Fiches** : on ne peut ni appeler, ni « Y aller », ni « Voir sur la carte », ni copier du texte (RECH_NAV-07). Chaque fiche est un vidage de tous les champs du modèle, un champ par carte (RECH_NAV-08).
- **En-têtes envahissants** : Planning et Réparations occupent la moitié de l'écran avant le premier élément (REP_PLAN-06, REP_PLAN-08, [capture 07](captures/07_reparations.png)).

**Architecture cible.** Quatre onglets plus le Pointage intégré :

1. **Aujourd'hui** :
   - créneau de pointage (« À pointer maintenant · jusqu'à 18h ») ;
   - relevés à faire (« Ambanja 0/53 · Reprendre ») ;
   - RDV du jour ;
   - réparations en retard ;
   - état de la synchro.
2. **Relevés.**
3. **Terrain** : complétude, carte, « Compléter les fiches » à la place de « tournée ».
4. **Réparations / Planning.**

Le Pointage devient un écran de `MainActivity` via une classe `PointageScreen`, sans Activity séparée. Un composant `HydriaUi.screenHeader(titre, sous-titre, onBack, trailing)` commun à toutes les Activities remplace les en-têtes ad hoc. Le menu ⋮ devient une feuille « Outils » avec pictogrammes. Les fiches gagnent une barre d'actions épinglée (Appeler · Y aller · Carte · Réparations) et une mise en page déclarative par type.

**Court terme**, sans tout refondre : ouvrir sur le dernier onglet utilisé, ou sur Relevés pendant une campagne, et ajouter en tête du Terrain une carte « Reprendre ma campagne ».

### 3.5 Lisible au soleil, pour de vrai

**Diagnostic**
- **Mode clair** : textes de ton, puces et bordures loin de l'objectif de 7:1 (TRANSVERSE-03). Le HUD de navigation y est même illisible (RECH_NAV-02, critique).
- **Échelle typographique** : environ 28 tailles différentes et 63 % des textes à 13 sp ou moins, soit environ 11 sp avec l'échelle 0,85 de l'appareil (TRANSVERSE-04).
- **Cibles tactiles** : 30 à 40 dp sur des actions quotidiennes (puces de filtre, pastille, menu ⋮) (TRANSVERSE-05, TERRAIN-15).
- **Transparence** : états désactivés et textes atténués à 1,9–3,7:1 (TRANSVERSE-06). Le bouton « Pointage possible à 15h » est à environ 3:1 (POINTAGE-06).
- **Défauts visibles sur le téléphone réel** :
  - **compteurs à 4 chiffres coupés** : « 1282 » s'affiche « 128 / 2 », « 1627 » s'affiche « 162 / 7 » (TERRAIN-05, [capture 13](captures/13_terrain_scroll.png)). La colonne fait 44 dp, alors que 4 chiffres en Roboto Mono 24 sp en demandent environ 56. Même défaut pour le retard des réparations au-delà de 99 jours (REP_PLAN-11) ;
  - **coins colorés parasites** à droite de toutes les cartes accentuées. La barre de couleur n'arrondit que ses coins gauches et dépasse derrière les coins arrondis de la carte (TERRAIN-14, REP_PLAN-15, POINTAGE-15). Le correctif tient en une ligne dans `HydriaVisuals.accentedCard` : `cornerRadius = radius` sur la barre ;
  - **badge « 99 »** sur l'onglet Réparations : il est rogné (« 99+ ») et compte toutes les réparations à faire, alors que son libellé TalkBack dit « en retard » (REP_PLAN-14) ;
  - **carte MapLibre claire** dans une app sombre (POINTAGE-12) ; en ligne, la palette de la carte n'est pas adaptée au fond clair (RECH_NAV-09).
- **Polices** : Archivo et Roboto Mono sont téléchargées au premier lancement. Sans réseau ce jour-là, l'app reste définitivement sur les polices de repli (TRANSVERSE-12).

**Principe de correction**
1. Ajouter des jetons de texte dédiés au mode clair (`hydria_cyan_text #0A5F6E`, `hydria_warning_text #7A4A00`, etc.) et un contour de champ à 3:1.
2. Créer `HydriaType.style(role)` avec 6 rôles et un plancher : méta 12 sp, corps 14, titre de ligne 15, titre de carte 17, chiffre 24, hero 44. Aucun texte sous 11 sp.
3. Garder les puces à 34–40 dp de hauteur visuelle, mais avec une zone tactile de 48 dp (InsetDrawable ou TouchDelegate).
4. Créer `HydriaUi.disabledButton` : texte opaque et fond atténué, sans transparence.
5. Colonnes de chiffres en `wrap_content` + `minWidth` + `maxLines = 1`, avec réduction automatique de la taille.
6. Embarquer les polices dans `res/font` (environ 400 Ko).
7. Rendre les fonds de carte et du HUD dépendants du thème.

### 3.6 Rendu des données : un formateur unique

**Diagnostic**
- **Nombres et montants** rendus de six façons :
  - « 125000.00 Ar » à l'écran et sur la facture A4 imprimée ;
  - « null Ar » pour un relevé en erreur ;
  - « 130,67 » en virgule mais « 1.0E7 » possible (TRANSVERSE-02, CALC_VOL-07).
- **Dates** : cinq formats coexistent. On voit « 2026-10-12 » au départ de campagne, « 12/10/2026 » dans la saisie et « 12 octobre 2026 » au planning. La date du jour ignore le fuseau Madagascar (TRANSVERSE-07).
- **Valeurs brutes d'API** : « planifie » s'affiche en orange sous un badge « À réaliser » (REP_PLAN-02).
- **Pluriels** : environ 68 libellés en « (s) », comme « 1 détail(s) » ou « 0 terminé(s) », lus tels quels par TalkBack (TRANSVERSE-09).
- **Retard** : « -224 JOURS » est ambigu, sans libellé, et son signe est l'inverse de la convention habituelle « J-5 » (REP_PLAN-11, TRANSVERSE-08).
- **Facture A4 mobile** : très en retrait du gabarit web. Pas d'en-tête d'organisation, pas de responsable, pas de consignes de paiement, et « N° Sans numéro » (CALC_VOL-08).
- **Saisie des dates** au format AAAA-MM-JJ dans cinq formulaires différents (campagne, débit, planning, réparation, encaissement), avec contrôle syntaxique seulement : « 2026-02-30 » passe (REP_PLAN-10, CALC_VOL-01, TERRAIN-07).

**Principe de correction**
- Créer `shared/commonMain/.../format/HydriaFormat.kt` en partant de `ReadingTicketFormat`, déjà testé. Comme il est partagé, le Desktop en profite aussi. Il expose :
  - `ariary()` : « 12 500 Ar », avec espace fine insécable ;
  - `m3()` : « 130,67 m³ » ;
  - `count()` : nombre groupé ;
  - `plural(n, un, autres)` ;
  - `dateCourte()` / `dateLongue()`, convertis vers Indian/Antananarivo ;
  - `retard(jours)` : « 224 j de retard » ou « dans 5 j » ;
  - `EMPTY = "—"` ;
  - `cleanJson()`, qui ramène « null », « N/A » et vide à null.
- Ajouter une table code → libellé (FR/MG) pour tous les statuts.
- Créer `HydriaUi.dateField()` (DatePickerDialog, affichage JJ/MM/AAAA, ISO en interne, date maximale = aujourd'hui) et l'utiliser dans les cinq formulaires.

### 3.7 Fluidité sur téléphone d'entrée de gamme

**Diagnostic.** Chaque changement d'onglet reconstruit tout l'onglet sur le fil principal. Réparations crée ses centaines de cartes d'un coup, d'où un voile plein écran avec un spinner figé sur le Blade 20 ([capture 03](captures/03_reparations.png), COEUR-09, REP_PLAN-07). Les listes du Terrain et les sauvegardes du snapshot, y compris la compression des photos, tournent aussi sur le fil principal (TERRAIN-11). La position de défilement est perdue après chaque action.

**Principe de correction**
1. Garder la vue de chaque onglet et ne la reconstruire que si la version du snapshot ou de la file a changé.
2. Mémoriser `scrollY` par écran.
3. Mettre à jour la carte touchée sur place après « Terminer ».
4. Afficher les listes longues par paquets (20 groupes puis « Afficher plus »), puis passer à un RecyclerView.
5. Déplacer `store.snapshot = …` et la compression des photos sur l'`executor`.

### 3.8 Le malgache

**Diagnostic.** `values-mg/strings.xml` ne couvre que la calculatrice, avec 160 chaînes bien traduites. Environ 75 % du texte visible est du français codé en dur dans le Kotlin, et `MainActivity` ne lit que 2 ressources de chaînes. En malgache, l'agent lit donc en français précisément les messages qui demandent le plus de clarté : remarque obligatoire, index refusé, conflit, motifs de refus de pointage (TRANSVERSE-01, COEUR-12, POINTAGE-11, REP_PLAN-12, CALC_VOL-12). Il n'existe aucun choix de langue dans l'app.

**Principe de correction**
1. Ajouter un mécanisme de langue : `locales_config.xml`, `AppCompatDelegate.setApplicationLocales` et une entrée « Langue / Fiteny » dans le menu.
2. Extraire les chaînes par ordre de visibilité : `HydriaVisuals`, onglets et menu, puis Relevés et centre de synchro, puis Pointage, puis le reste.
3. Faire renvoyer des clés (enums) par les règles partagées plutôt que du texte.
4. Faire relire par un agent malgachophone.

---

## 4. Feuille de route proposée

Les efforts sont des estimations pour un développeur qui connaît la base : S < 0,5 j, M = 0,5 à 2 j, L > 2 j.

### Lot 1 — « Filet de sécurité » : quick wins, environ 4 à 5 jours

Tous de niveau S. Chacun touche un ou deux fichiers.

| Ordre | Action | Constats |
|---|---|---|
| 1 | Garde de rendu en fin de synchro pendant une saisie de relevé | COEUR-01 |
| 2 | `onBackPressedDispatcher` qui remonte d'un niveau ; campagne mémorisée dans les préférences | COEUR-07, TERRAIN-10 |
| 3 | Confirmation avant « Se déconnecter » | COEUR-08 |
| 4 | Remarque obligatoire contrôlée dans `ReadingValidation` ; libellé « (obligatoire) » dynamique ; « Corriger » pour les refus 400 | COEUR-02 |
| 5 | Dialogues de formulaire non fermables par erreur + « Abandonner la saisie ? » | REP_PLAN-04 |
| 6 | Calculatrice : « AC » renommé « Tout effacer » sans toucher aux cahiers ; « 5000 + 7% » = 5 350 | CALC_VOL-04, CALC_VOL-06 |
| 7 | Volume : la synchro continue après un refus et le récapitulatif s'affiche quand même | CALC_VOL-02 |
| 8 | Colonnes de chiffres sans retour à la ligne (`taskRow`, retard des réparations) | TERRAIN-05, REP_PLAN-11 |
| 9 | Coins des cartes accentuées (1 ligne) | TERRAIN-14 |
| 10 | Couleurs du HUD et des panneaux de carte selon le thème | RECH_NAV-02 |
| 11 | Toucher un village ou une grappe sur la carte ; nombre affiché sur les grappes | RECH_NAV-01 |
| 12 | Jetons de contraste du mode clair ; zones tactiles de 48 dp ; bouton désactivé lisible | TRANSVERSE-03, -05, POINTAGE-06 |
| 13 | `HydriaUi.dateField()` dans les 5 formulaires de date | REP_PLAN-10, CALC_VOL-01, TERRAIN-07 |
| 14 | Badge Réparations : compte des échues seulement, « 99+ » entier | REP_PLAN-14 |

### Lot 2 — « Le travail du jour, fiable » : environ 2 à 3 semaines

| Action | Constats | Effort |
|---|---|---|
| Formulaire de relevé réordonné + barre fixe + brouillon | COEUR-03, COEUR-01 (suite) | M |
| Garde-fous de plausibilité + « Annuler » après enregistrement | COEUR-04 | M |
| `PendingOverlay` dans `shared` + clés d'idempotence | REP_PLAN-03, POINTAGE-04, COEUR-05 | M–L |
| Centre de synchronisation lisible + pastille unique | COEUR-06, POINTAGE-08, TRANSVERSE-08 | M |
| « Mes pointages aujourd'hui » avec reçu et motif de refus | POINTAGE-03, POINTAGE-01 | M |
| Feuille de capture GPS partagée | TERRAIN-01, RECH_NAV-03, POINTAGE-13 | M |
| Série Terrain en barre persistante, tournée par point puis par distance | TERRAIN-03, TERRAIN-04 | M |
| `HydriaFormat` + table des statuts + pluriels | TRANSVERSE-02, -07, -09, CALC_VOL-07, REP_PLAN-02 | M |
| Éditeur de planning : « — Choisir — » sur la cascade d'activité | REP_PLAN-01 | S–M |

### Lot 3 — « Structure » : plusieurs semaines, à planifier

| Action | Constats |
|---|---|
| Accueil « Aujourd'hui » + Pointage intégré à `MainActivity` | COEUR-10, POINTAGE-05, POINTAGE-09, REP_PLAN-09 |
| Rendu par onglet conservé, listes paginées puis RecyclerView | COEUR-09, REP_PLAN-07, TERRAIN-11 |
| Échelle typographique à 6 rôles, puis remplacement des ≈ 350 sites | TRANSVERSE-04, TRANSVERSE-10 |
| Malgache : mécanisme de langue puis extraction progressive | TRANSVERSE-01 et constats i18n |
| Fiches : barre d'actions + mise en page déclarative + diagramme lisible | RECH_NAV-07, RECH_NAV-08 |
| Carte hors ligne : retour du fond au retour du réseau, repères, zones téléchargeables | RECH_NAV-09 |
| Facture A4 mobile alignée sur le gabarit web | CALC_VOL-08 |
| En-tête commun `screenHeader` + feuille « Outils » | COEUR-11 |

### Décisions produit à prendre d'abord

Ces points ne relèvent pas que du code : ils demandent un arbitrage métier ou serveur.

1. **Pointage « prévu »** (POINTAGE-02, critique). Les créneaux d'un planning doivent-ils être prévus par défaut selon l'activité, ou déclarés à l'avance ? Tant que ce n'est pas tranché, les rappels et le décompte des pointages manqués resteront faux.
2. **Statut « planifie »** (REP_PLAN-02). Faut-il l'ajouter aux choix du serveur, ou migrer les plannings importés ?
3. **Compteur de tête remplacé ou remis à zéro** (TERRAIN-08). Il faut un indicateur dédié dans l'API `head_meter_reading`.
4. **Gabarit de facture A4 mobile** (CALC_VOL-08). Faut-il reprendre exactement le gabarit web, comme pour le Desktop ?
5. **Confirmation d'impression** (CALC_VOL-09). Faut-il la lier à la fin réelle de l'impression (`PrintJob`), et autoriser la réimpression à l'unité ?

---

## 5. Méthode et limites

**Sources**
- Code de la version 2.12.0 (MainActivity ≈ 5 600 lignes, autres Activities, module `shared`, backend Django pour les règles serveur).
- Spécification et maquettes du handoff « Lisible au soleil ».
- 14 captures prises sur le téléphone réel le 12 octobre : ZTE Blade 20, Android 15, ≈ 424 × 948 dp, police à 0,85, thème sombre, version 2.11.0, compte réel. Les principales sont dans [captures/](captures/).

**Déroulé**
1. Audit initial : 7 domaines audités par des agents spécialisés.
   - Terrain, Pointage, Réparations/Planning ont été audités le 12 octobre, sur la 2.11.0.
   - Les 4 autres le 19 octobre, sur la 2.12.0 : cœur relevés/synchro/parcours, transverse, recherche/carte, calculatrice/volume.
2. Vérification : les 45 constats établis sur la 2.11.0 ont tous été revérifiés sur la 2.12.0. Résultat : 0 infirmé, 5 partiellement corrigés, le reste confirmé.
3. Contre-épreuve : les 4 constats critiques récents ont subi une tentative de réfutation dans le code, qui a échoué pour les 4. Deux ont cependant été ramenés à « majeur », parce qu'un contournement existe déjà dans l'app. Pour COEUR-02, l'erreur s'affiche en rouge dans le centre, et la correction reste possible par « Voir mes saisies ». Pour RECH_NAV-01, un village reste atteignable par un indicateur de bord ou par le panneau « Autour de moi » sur tablette.

**Limites**
- **Audit statique, sans exécution.** Les temps (figeages, ANR) sont déduits du code, pas mesurés au profileur.
- **Captures prises en 2.11.0.** L'accueil a changé en 2.12.0 : les deux gros boutons « Carte » et « Commencer ma tournée » sont passés dans le menu « Outils ». La capture 01 n'est donc plus exacte sur ce point.
- **Mode clair et tablette non observés** sur un appareil. Les constats qui les concernent viennent du code et des calculs de contraste.
- **Pas de test avec des agents.** Les points d'ergonomie, en particulier le nombre de gestes et la compréhension des libellés, gagneraient à être confirmés par une observation de 2 ou 3 agents sur une vraie tournée, en malgache et en français.
