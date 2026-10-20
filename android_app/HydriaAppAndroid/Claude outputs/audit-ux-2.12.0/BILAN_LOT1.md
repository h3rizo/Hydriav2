# Bilan du lot 1 — corrections de l'audit UX

**Date** : 20 octobre 2026 (sessions des 19 et 20 octobre).
**Réalisé par** des agents Sonnet. Chaque lot a suivi le même circuit : implémentation, revue indépendante du diff, puis correction si la revue relevait un problème bloquant ou important.
**Détail complet** dans [BILAN_LOT1_ANNEXE.md](BILAN_LOT1_ANNEXE.md) : chaque correction, ses fichiers, les 62 vérifications sur téléphone et les 36 remarques mineures des revues.

## 1. État

- **Build et tests** : un build final, lancé indépendamment des agents le 20/10 à 04:10, a réexécuté tous les tests. **567 tests, 0 échec** : shared Desktop 204, shared Android 176, app 187. Le module Desktop compile.
- **APK debug** : `app/build/outputs/apk/debug/app-debug.apk`, du 20/10 à 04:02. Il n'est ni distribué ni déployé.
- **Version** : toujours `2.12.0` (versionCode 57), car on ne la change pas sans ton accord. **Attention** : l'arborescence contenait déjà du travail 2.12.0 d'une autre session (fichiers modifiés le 19/10 au matin). L'APK l'inclut, et ce travail-là n'a pas été testé par ces sessions.
- **Sauvegardes avant modification** : `work/backup-1A/`, `backup-1A-suivi/`, `backup-1B/`, `backup-1C/`, `backup-1D/`, `backup-1E/`, avec un sous-dossier daté et les chemins relatifs d'origine. Pour annuler un lot, recopie ses fichiers dans l'ordre inverse : 1-E, puis 1-D, et ainsi de suite.
- **Aucun changement serveur**, aucun commit, aucun déploiement.

## 2. Ce qui a été corrigé

| Lot | Corrections | Après revue |
|---|---|---|
| **1-A** Ne plus perdre la saisie | COEUR-01 (la synchro n'efface plus un relevé en cours), COEUR-07 + TERRAIN-10 (Retour remonte d'un niveau, campagne mémorisée et restaurée), COEUR-08 (confirmation de déconnexion), COEUR-02 (remarque obligatoire contrôlée dans `shared` + « Corriger » pour les refus serveur), REP_PLAN-04 (formulaires protégés, erreurs sur le champ) | 1 problème corrigé : le marqueur « refusé » restait après une coupure réseau |
| **1-A suivi** | Confirmation « Abandonner la saisie ? » au Retour pendant un relevé ; volet de détail tablette remis à zéro quand la campagne se ferme | — |
| **1-B** Lisibilité | TERRAIN-14 (coins colorés supprimés), TERRAIN-05 (« 1282 » sur une ligne), REP_PLAN-11 (« 224 j · RETARD » au lieu de « -224 JOURS », calculé dans `shared`), REP_PLAN-14 (badge = réparations échues, « 99+ » entier), TRANSVERSE-03 (jetons de contraste du mode clair), TRANSVERSE-05 (zones tactiles de 48 dp), POINTAGE-06 (bouton désactivé lisible) | 4 problèmes corrigés : puces rognées dans la calculatrice, 10 textes encore en couleur d'accent |
| **1-C** Carte, calculatrice, volume | RECH_NAV-02 (HUD lisible dans les deux thèmes), RECH_NAV-01 (villages et grappes cliquables, nombre affiché sur les grappes), CALC_VOL-04 (« Tout effacer » garde les cahiers), CALC_VOL-06 (« 5000 + 7% » = 5 350), CALC_VOL-02 (un refus ne bloque plus la synchro du volumétrique) | 1 problème corrigé : la file n'attend plus le délai réseau élément par élément quand le réseau est coupé |
| **1-D** Dates | `HydriaUi.dateField` (sélecteur JJ/MM/AAAA, ISO en interne, fuseau Madagascar) dans les 5 formulaires (campagne, débit/compteur de tête, planning/réparation, encaissement, planning du Pointage) ; date **réelle** exigée dans `shared` (« 2026-02-30 » refusé) | — |
| **1-E** Finitions issues des revues | Date de campagne conservée après une synchro ; « Changer » demande aussi confirmation ; effacement de la calculatrice en une seule écriture (testé) ; « Corriger la date » rouvre l'encaissement avec la date et le journal choisis ; grappe touchée pendant une navigation ; « aujourd'hui » au fuseau Madagascar partout dans MainActivity ; bordure de champ à 3:1 en mode clair | — |

## 3. Plan de test sur le téléphone (version condensée)

Installe l'APK par-dessus la 2.12.0. Les données hors ligne sont conservées, car le certificat de debug est le même. Fais ces 16 contrôles en priorité. La liste complète des 62 vérifications est dans l'annexe.

**Relevés (le plus important)**
- [ ] En ligne, enregistrer un relevé puis taper **aussitôt** l'index du point suivant. Une fois la synchro finie, l'index tapé et le point choisi ne doivent pas avoir changé.
- [ ] Index égal au précédent : le champ affiche « Remarque (obligatoire) », et « Enregistrer » sans remarque est refusé, avec l'erreur sur le champ.
- [ ] Taper un index puis appuyer sur Retour, puis sur « Changer » : la boîte « Abandonner la saisie ? » apparaît. Sans rien taper : la campagne se ferme directement.
- [ ] Démarrer une campagne, tuer l'app depuis les applications récentes, la rouvrir : on retrouve la même campagne.
- [ ] Départ de campagne : choisir une autre date, attendre une synchro. La date choisie est conservée.

**Navigation dans l'app**
- [ ] Retour depuis une liste Terrain, depuis Réparations ou depuis Planning : on remonte d'un niveau. À la racine, « Appuyez encore pour quitter ».
- [ ] Menu ⋮ puis « Se déconnecter » : une confirmation s'affiche, et « Annuler » ne déconnecte pas.

**Synchronisation**
- [ ] Un relevé refusé par le serveur affiche « Corriger » dans le centre de synchro, et ce bouton rouvre le bon point en mode correction.

**Lisibilité (à faire en mode clair ET en mode sombre, au soleil si possible)**
- [ ] Terrain : « 1282 » et « 1627 » sur une seule ligne, sans coins colorés à droite des cartes.
- [ ] Réparations : « 224 j » avec la mention « RETARD » ; le badge de l'onglet ne compte que les réparations en retard.
- [ ] Les puces de filtre et le menu ⋮ se touchent facilement ; le bouton « Pointage possible à 15h » est lisible.
- [ ] Carte : le HUD est lisible en mode clair, un village se touche, une grappe zoome et affiche un nombre.

**Calculatrice et volumétrique**
- [ ] « 5000 + 7% » = 5 350 ; « 200 × 15% » = 30 (inchangé).
- [ ] « Tout effacer » garde les cahiers de caisse nommés.
- [ ] Encaissement : sélecteur de date ; « Corriger la date » garde le journal ; un encaissement refusé ne bloque pas les suivants et le récapitulatif s'affiche.

**Dates**
- [ ] Les 5 formulaires ouvrent un calendrier. Une date future est impossible pour une campagne, une mesure ou un encaissement, mais possible pour un planning.

## 4. Ce qui reste (hors lot 1)

- **Remarques mineures des revues** : 36, listées dans l'annexe. Les plus notables :
  - la réduction automatique de taille des chiffres est en place, mais n'agit pas : c'est le passage en largeur libre qui règle le « 128 / 2 » ;
  - toucher une grappe pendant une navigation fait passer en exploration : le bouton ◎ ramène au suivi GPS, pas au guidage ;
  - le bouton « Tout effacer » de la calculatrice est étroit pour sa traduction malgache.
- **Écart avec le Desktop.** L'écran Relevés du Desktop n'applique pas encore la règle de remarque obligatoire, et l'écran Réparations du Desktop affiche toujours le retard brut. Les règles sont pourtant dans `shared`. Le Desktop était hors du périmètre des consignes.
- **Côté serveur (signalé, non fait).** Une intervention dont la date est passée est renvoyée « En cours » par le serveur (`views_preparation_tournee.py`, vers la ligne 329). L'app pourrait afficher « En retard » à la place.

## 5. Pour lancer le lot 2 : tes réponses nécessaires

Les 9 chantiers du lot 2 sont décrits dans [PROMPT_SONNET_CORRECTIONS.md](PROMPT_SONNET_CORRECTIONS.md), section 6. Avant de démarrer, j'ai besoin de ta décision sur ces points :

1. **Version et diffusion du lot 1.** Faut-il passer en 2.12.1 et distribuer l'APK au parc, après tes tests sur téléphone, ou attendre le lot 2 ?
2. **POINTAGE-02, créneaux « prévus ».** Doivent-ils être prévus par défaut selon l'activité du planning (par exemple matin et après-midi pour une activité de terrain), ou déclarés à l'avance par l'agent ? Les rappels et le décompte des pointages manqués en dépendent.
3. **L2-3, idempotence des créations hors ligne.** Ce chantier demande un petit changement serveur : accepter une clé générée sur le téléphone et ignorer un doublon. Est-ce que je peux le préparer, avec déploiement sur le VPS selon ta procédure ?
4. **REP_PLAN-02, statut « planifie ».** Faut-il l'ajouter aux statuts du serveur, ou migrer les plannings importés vers un statut existant ?
5. **L2-6, seuil de précision GPS.** Quel seuil exiger pour enregistrer les coordonnées d'un point : 15 m, 25 m, autre ? Faut-il le même seuil pour le pointage, aujourd'hui à 100 m ?
6. **Desktop.** Faut-il aligner l'app Desktop au fil des chantiers (remarque obligatoire, libellé du retard, sélecteur de date), ou la laisser pour plus tard ?
7. **Ordre des chantiers.** L'ordre proposé est L2-1 relevé réordonné, L2-2 garde-fous, L2-3 file visible, L2-4 centre de synchro, L2-5 mes pointages, L2-6 GPS, L2-7 série Terrain, L2-8 formateur, L2-9 cascade. Veux-tu en avancer un ?
