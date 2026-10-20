# Annexe — détail des 93 constats de l'audit UX Hydria Terrain

Compagnon du rapport [AUDIT_UX_HYDRIA_TERRAIN_2.12.0.md](AUDIT_UX_HYDRIA_TERRAIN_2.12.0.md). Constats triés par domaine puis par sévérité.
Répartition : 5 critiques, 66 majeurs, 20 mineurs, 2 cosmétiques.

Les numéros de ligne des « preuves » renvoient à la version où le constat a été établi ; ceux de la ligne « Vérification sur 2.12.0 » renvoient au code actuel.

## Tableau récapitulatif

| Id | Sévérité | Effort | Constat | Statut |
|---|---|---|---|---|
| COEUR-01 | Critique | S · quick win | La fin de chaque synchronisation efface la saisie en cours : l'écran Relevés est entièrement reconstruit | Vérifié en 2.12.0 (contre-épreuve : réfutation échouée) |
| COEUR-02 | Majeur | S · quick win | Un relevé refusé par le serveur reste bloqué dans la file sans moyen de le corriger ; la règle « remarque obligatoire » n'est pas contrôlée dans l'appli | Vérifié en 2.12.0 (contre-épreuve : réfutation échouée) |
| COEUR-03 | Majeur | M | Enregistrer est à environ deux écrans du champ index : 5 à 6 gestes par relevé, 8 à 9 si le point suivant n'est pas le premier de la liste | Vérifié en 2.12.0 (relecture de l'auditeur) |
| COEUR-04 | Majeur | M | Aucun garde-fou contre la faute de frappe ou le mauvais point : à l'enregistrement, seul « index inférieur au précédent » est contrôlé | Vérifié en 2.12.0 (relecture de l'auditeur) |
| COEUR-05 | Majeur | M | Progression et fin de campagne fausses dès qu'on est en ligne ; « Corriger une saisie » mène à une impasse et re-saisir crée un doublon | Vérifié en 2.12.0 (relecture de l'auditeur) |
| COEUR-06 | Majeur | M | L'état de synchronisation est illisible pour un non-informaticien : UUID, erreurs réseau brutes, panne passagère présentée comme « Erreur » avec « Supprimer » | Vérifié en 2.12.0 (relecture de l'auditeur) |
| COEUR-07 | Majeur | S · quick win | Le bouton Retour quitte l'application depuis n'importe quel sous-écran, et le contexte de campagne n'est pas conservé | Vérifié en 2.12.0 (relecture de l'auditeur) |
| COEUR-08 | Majeur | S · quick win | « Se déconnecter » : un seul appui, sans confirmation, efface toute la tournée hors ligne et impose le réseau pour se reconnecter | Vérifié en 2.12.0 (relecture de l'auditeur) |
| COEUR-09 | Majeur | M | Changement d'onglet : voile plein écran et spinner figé, car l'onglet entier est reconstruit sur le fil principal (Réparations crée toutes ses cartes d'un coup) | Vérifié en 2.12.0 (relecture de l'auditeur) |
| COEUR-10 | Majeur | M | Début de journée : l'appli s'ouvre sur la complétude du périmètre (27 %, 3 601 tâches) plutôt que sur le travail du jour ; « tournée » a trois sens ; choix d'ouvrage non recherchable | Vérifié en 2.12.0 (relecture de l'auditeur) |
| COEUR-11 | Mineur | M | En-têtes et retours incohérents d'une Activity à l'autre ; le menu ⋮ est une liste texte qui cache calculatrice, volumétrique et carte | Vérifié en 2.12.0 (relecture de l'auditeur) |
| COEUR-12 | Mineur | L | Les parcours de relevé et de synchronisation n'existent qu'en français : le malgache ne couvre que la calculatrice | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-01 | Majeur | L | Le malgache n'existe que dans la calculatrice : ≈ 75 % du texte visible reste en français codé en dur | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-02 | Majeur | M | Aucun formateur commun : montants, volumes et nombres sont rendus de six façons, y compris sur la facture A4 imprimée au client | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-03 | Majeur | S · quick win | Mode clair : textes de ton, puces et bordures loin de l'objectif 7:1 « au soleil » | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-04 | Majeur | M | Échelle typographique inutilisée : ≈ 28 tailles, 63 % des textes ≤ 13 sp, soit ≈ 11 sp à l'échelle 0,85 de l'appareil | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-05 | Majeur | S · quick win | Cibles tactiles de 30–40 dp sur des actions quotidiennes, contraires aux 48 dp du système de design | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-06 | Mineur | S | Texte atténué et états désactivés par transparence : des informations utiles tombent à 1,9–3,7:1 | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-07 | Mineur | S | Cinq formats de date coexistent, dont des dates ISO brutes ; la date du jour ignore le fuseau Madagascar | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-08 | Mineur | S | États portés par la couleur ou le signe seul : pastille « à jour » rouge hors ligne, « -224 JOURS » sans libellé | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-09 | Mineur | M | Pluriels bricolés « (s) » sur ≈ 68 libellés, lus tels quels par TalkBack | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-10 | Mineur | M | Système de design contourné : jetons de dimension non utilisés, ≈ 830 dp() littéraux, couleurs de carte du mode sombre figées | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-11 | Mineur | M | Structure TalkBack absente : aucun titre déclaré, aucune région vivante, descriptions qui masquent le contenu | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TRANSVERSE-12 | Mineur | S | Polices Archivo et Roboto Mono téléchargées au premier lancement : repli définitif en sans-serif et mono large | Vérifié en 2.12.0 (relecture de l'auditeur) |
| TERRAIN-01 | Majeur | M | Le GPS d'un point est la première position reçue, sans seuil de précision, sans confirmation et sans délai maximal | Vérifié en 2.12.0 |
| TERRAIN-02 | Majeur | S · quick win | Deux actions sur le même point dans une série créent un « conflit » artificiel à la synchro | Partiellement corrigé en 2.12.0 |
| TERRAIN-03 | Majeur | M | « Commencer ma tournée » lance 3 434 tâches triées par catégorie puis par ordre alphabétique, sans aperçu | Vérifié en 2.12.0 |
| TERRAIN-04 | Majeur | M | Série : un dialogue « Continuer / Fermer » à chaque élément, pas de « Passer », et la série se fige | Vérifié en 2.12.0 |
| TERRAIN-05 | Majeur | S · quick win | Les compteurs à 4 chiffres passent à la ligne (« 128 / 2 », « 162 / 7 ») | Vérifié en 2.12.0 |
| TERRAIN-06 | Majeur | S · quick win | Carte de complétude : le % ne bouge pas hors ligne, et les compteurs (des totaux) se lisent comme des restes | Vérifié en 2.12.0 |
| TERRAIN-07 | Majeur | M | Formulaires Débit source et Compteur de tête : libellés qui disparaissent, date ISO à taper, erreurs génériques | Vérifié en 2.12.0 |
| TERRAIN-08 | Majeur | M | Compteur de tête : remplacement impossible et analyse trompeuse dans les cas limites | Vérifié en 2.12.0 |
| TERRAIN-09 | Majeur | S · quick win | Fiche abonné : le téléphone accepte un nom que le serveur considère encore comme manquant | Vérifié en 2.12.0 |
| TERRAIN-10 | Majeur | S · quick win | Liste d'une catégorie : toucher coche au lieu d'ouvrir, ouverture cachée en appui long, et Retour ferme l'app | Vérifié en 2.12.0 |
| TERRAIN-11 | Majeur | M | Listes et sauvegardes construites d'un bloc sur le fil principal | Vérifié en 2.12.0 |
| TERRAIN-12 | Mineur | M | « Par ouvrage » et « Autour » ne débouchent sur aucune action | Partiellement corrigé en 2.12.0 |
| TERRAIN-13 | Mineur | S | Premier écran : 3,5 tâches visibles, barre de mesures permanente en environ 10 sp, tâche terminée au milieu | Partiellement corrigé en 2.12.0 |
| TERRAIN-15 | Mineur | S | Puces de filtre : dernière lettre rognée, 30 dp de haut, mélange Archivo et Roboto | Vérifié en 2.12.0 |
| TERRAIN-14 | Cosmétique | S · quick win | accentedCard : coins colorés parasites en haut et en bas à droite | Vérifié en 2.12.0 |
| REP_PLAN-03 | Critique | M | Saisies hors ligne invisibles, réédition sur valeurs périmées et créations non idempotentes (doublons) | Vérifié en 2.12.0 |
| REP_PLAN-01 | Majeur | M | Éditeur : employé et activité présélectionnés d'office (1er dans l'ordre alphabétique) | Partiellement corrigé en 2.12.0 |
| REP_PLAN-02 | Majeur | M | Statut « planifie » affiché brut et réécrit en « En cours » à chaque modification | Vérifié en 2.12.0 |
| REP_PLAN-04 | Majeur | S · quick win | Formulaire de 10-11 champs dans un AlertDialog fermable sans confirmation ; erreurs en toast | Vérifié en 2.12.0 |
| REP_PLAN-05 | Majeur | S · quick win | « Marquer terminée » : bouton dominant, confirmation anonyme, aucune annulation, « Suite à donner » écrasée | Vérifié en 2.12.0 |
| REP_PLAN-06 | Majeur | M | Liste Réparations : en-tête envahissant, 3 boutons pleine largeur par carte, groupes entièrement dépliés, aucune recherche | Partiellement corrigé en 2.12.0 |
| REP_PLAN-07 | Majeur | M | Reconstruction complète et synchrone de la liste : voile au changement d'onglet, figeages, défilement perdu | Vérifié en 2.12.0 |
| REP_PLAN-08 | Majeur | S · quick win | Planning : en-tête fixe (titre, carte de pointage, bouton) qui occupe la moitié de l'écran | Vérifié en 2.12.0 |
| REP_PLAN-09 | Majeur | S · quick win | Pointage du jour : « Aucun planning aujourd'hui » affiché à côté de « 8 RDV » le même jour | Vérifié en 2.12.0 |
| REP_PLAN-10 | Majeur | S · quick win | Date saisie en texte libre AAAA-MM-JJ, contrôle syntaxique seulement | Vérifié en 2.12.0 |
| REP_PLAN-11 | Majeur | S · quick win | Chiffre de retard : signe ambigu, colonne qui déborde, libellés à contraste insuffisant, statut « En cours » trompeur | Vérifié en 2.12.0 |
| REP_PLAN-12 | Majeur | L | Textes en dur non traduits en malgache, pluriels « (s) », coquilles et doublons de noms | Vérifié en 2.12.0 |
| REP_PLAN-13 | Mineur | M | Bande de jours : jours vides absents, ni mois ni repère « aujourd'hui », puces de charge toutes orange, agenda tout empilé | Vérifié en 2.12.0 |
| REP_PLAN-14 | Mineur | S | Badge de l'onglet Réparations : « 99+ » rogné en « 99 », sens incohérent (« en retard » vs toutes à faire) | Vérifié en 2.12.0 |
| REP_PLAN-15 | Cosmétique | S | Finitions : coins parasites des cartes accentuées, listes sans flèche, champ Remarque non stylé, thème de dialogue ignoré | Vérifié en 2.12.0 |
| POINTAGE-02 | Critique | M | « Prévu » ne se déclare que pendant le créneau : rappels inertes et pointages manqués jamais comptés | Vérifié en 2.12.0 |
| POINTAGE-03 | Critique | M | Un pointage hors ligne refusé plus tard disparaît sans explication, et aucun reçu n'est conservé | Vérifié en 2.12.0 |
| POINTAGE-01 | Majeur | M | La case « prévu » ressemble à l'action de pointer | Vérifié en 2.12.0 |
| POINTAGE-04 | Majeur | M | Planning ajouté hors ligne : l'écran affiche toujours « Aucun planning », d'où des doublons | Vérifié en 2.12.0 |
| POINTAGE-05 | Majeur | M | L'onglet « Pointage » ouvre un écran hors de la navigation | Vérifié en 2.12.0 |
| POINTAGE-06 | Majeur | S · quick win | Bouton principal grisé : information clé à ~3:1 de contraste, et fausse promesse sans planning | Vérifié en 2.12.0 |
| POINTAGE-07 | Majeur | S · quick win | Autorisations GPS et notifications : demandes concurrentes, boucle possible, aucun recours | Vérifié en 2.12.0 |
| POINTAGE-08 | Majeur | S · quick win | Pastille « à jour » du pointage : périmètre trompeur et pastille non cliquable | Vérifié en 2.12.0 |
| POINTAGE-09 | Majeur | S · quick win | Trois points d'entrée, trois discours : l'accueil ne dit jamais « à pointer maintenant » | Vérifié en 2.12.0 |
| POINTAGE-10 | Majeur | S · quick win | « Mon équipe » : cartes « 0/0 » répétées, ratio sans libellé, symboles sans légende | Vérifié en 2.12.0 |
| POINTAGE-11 | Majeur | M | Pointage entièrement en français codé en dur, notification et motifs de refus compris | Vérifié en 2.12.0 |
| POINTAGE-12 | Mineur | S | Carte claire dans l'application sombre, vide hors ligne, et 240 dp même sans village géolocalisé | Vérifié en 2.12.0 |
| POINTAGE-13 | Mineur | S | Statut GPS : une position ancienne présentée comme actuelle, des messages hors sujet | Vérifié en 2.12.0 |
| POINTAGE-14 | Mineur | S | Rappels : un seul avis à l'ouverture du créneau, aucune relance, aucun réglage dans l'application | Vérifié en 2.12.0 |
| POINTAGE-15 | Mineur | S | Écarts au système de design : cibles de 40 dp, case native, dialogue non thématisé, coins colorés parasites | Vérifié en 2.12.0 |
| RECH_NAV-02 | Critique | S · quick win | HUD de navigation illisible en thème clair : texte sombre sur panneau sombre codé en dur | Vérifié en 2.12.0 (contre-épreuve : réfutation échouée) |
| RECH_NAV-01 | Majeur | S · quick win | Carte : les villages ne se touchent pas, les grappes sont muettes et inertes | Vérifié en 2.12.0 (contre-épreuve : réfutation échouée) |
| RECH_NAV-03 | Majeur | M | Marquer une position : pas de réticule et aucun garde-fou sur la qualité du fix | Vérifié en 2.12.0 (relecture de l'auditeur) |
| RECH_NAV-04 | Majeur | M | Rotation ou retour de l'appareil photo : la navigation active et la photo en cours sont perdues | Vérifié en 2.12.0 (relecture de l'auditeur) |
| RECH_NAV-05 | Majeur | M | HUD : l'itinéraire routier de la 2.11.0 est relégué en 12 sp et la flèche l'ignore | Vérifié en 2.12.0 (relecture de l'auditeur) |
| RECH_NAV-06 | Majeur | M | Recherche hors ligne limitée aux ouvrages mais présentée comme une copie complète | Vérifié en 2.12.0 (relecture de l'auditeur) |
| RECH_NAV-07 | Majeur | M | Fiches : ni appeler, ni « Y aller », ni « Voir sur la carte », ni texte copiable | Vérifié en 2.12.0 (relecture de l'auditeur) |
| RECH_NAV-08 | Majeur | M | Fiches : dump de tous les champs du modèle (un champ = une carte) et diagramme de flux aux étiquettes superposées | Vérifié en 2.12.0 (relecture de l'auditeur) |
| RECH_NAV-09 | Majeur | L | Carte hors ligne : fond uni jamais rétabli au retour du réseau, aucune zone téléchargeable, palette non adaptée au fond clair en ligne | Vérifié en 2.12.0 (relecture de l'auditeur) |
| RECH_NAV-10 | Majeur | M | Arrivée et enregistrements : aucune suite proposée et confirmations qui disparaissent en une seconde | Vérifié en 2.12.0 (relecture de l'auditeur) |
| RECH_NAV-11 | Majeur | S · quick win | Indicateurs hors écran masqués sous les panneaux (haut, bas et droite) | Vérifié en 2.12.0 (relecture de l'auditeur) |
| RECH_NAV-12 | Mineur | S | Résultats : jeton « OU » pour 8 types sur 14, 13 puces de filtre par défaut, pagination sans retour | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-01 | Majeur | S · quick win | Date d'encaissement en texte libre, sans garde-fou, et journal sans valeur par défaut | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-02 | Majeur | S · quick win | Synchronisation de l'écran : le premier refus bloque les suivants et supprime l'affichage du récapitulatif | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-03 | Majeur | M | Encaissement et Pointage : total, compteur et bouton de validation défilent avec la liste ; comparaison sur deux colonnes de 300 dp | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-04 | Majeur | S · quick win | « AC » de l'en-tête efface aussi les cahiers de caisse enregistrés et porte le même nom que « AC » du pavé | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-05 | Majeur | M | Supprimer une ligne de calcul décale tous les Ln du dessous sans réécrire les références, sans confirmation ni annulation | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-06 | Majeur | S · quick win | Le « % » divise par 100 : « 5000 + 7% » donne 5 000,07 sans aucun avertissement | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-07 | Majeur | S · quick win | Montants bruts « 125000.00 Ar » à l'écran et sur la facture, et « null Ar » pour les relevés en erreur | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-08 | Majeur | M | Facture A4 mobile très en retrait du gabarit web : pas d'en-tête organisation, ni responsable, ni consignes de paiement, « N° Sans numéro » et mention interne imprimée | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-09 | Majeur | M | « Confirmer l'impression réalisée » : bouton verrouillant, indépendant de l'impression réelle, et réimpression possible seulement par lot entier | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-10 | Majeur | M | Onglet Calculs sur téléphone : les lignes passées ne sont pas compactes, la liste n'a de place que pour moins d'une carte | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-11 | Majeur | M | Onglets Salaire, Devis, Total, Caisse : libellés qui disparaissent à la saisie, nouvelle ligne invisible après « Ajouter », typographie hors charte | Vérifié en 2.12.0 (relecture de l'auditeur) |
| CALC_VOL-12 | Mineur | L | Écran Volumétrique construit hors refonte : statuts en texte brut, chaînes en dur sans malgache, erreurs d'exception affichées | Vérifié en 2.12.0 (relecture de l'auditeur) |

## Cœur du travail : relevés, synchronisation, parcours

_Audit initial sur la version 2.12.0._

**Synthèse du domaine.** Le coeur du travail terrain repose sur de bonnes bases : file hors ligne, champ NOUVEL INDEX très lisible, enchaînement automatique vers le point suivant. Mais l'audit du code montre deux risques de perte ou de blocage de travail à traiter en priorité. (1) Chaque fin de synchronisation reconstruit l'écran Relevés et efface la saisie en cours, alors qu'après chaque relevé la tournée complète est re-téléchargée, ce qui allonge la fenêtre de perte. (2) Des relevés que le serveur refuse (remarque obligatoire si consommation nulle ou volume non facturé) sont acceptés par l'appli puis restent coincés dans la file, sans bouton « Corriger ». Viennent ensuite des frictions de fond. Enregistrer est à environ deux écrans du champ index (5 à 6 gestes par relevé, 8 à 9 si le point suivant n'est pas le premier de la liste). Aucun garde-fou de plausibilité ni annulation n'existe à l'enregistrement. Les compteurs de campagne et la fin de campagne sont faux dès qu'on est en ligne. Le centre de synchronisation affiche des UUID et des erreurs techniques. Retour système quitte l'application, et « Se déconnecter » efface tout le hors ligne en un seul appui. La cause du voile avec spinner figé est une reconstruction complète de l'onglet sur le fil principal, avec des centaines de cartes Réparations construites d'un coup. Enfin l'architecture d'information ne place pas le travail du jour à l'accueil, les en-têtes et retours diffèrent selon les Activities, et le malgache ne couvre que la calculatrice. Quatre correctifs sont des quick wins de moins d'une demi-journée : COEUR-01, COEUR-02, COEUR-07 et COEUR-08. Limites : audit statique du code et des captures, sans profilage ni exécution ; le comportement serveur a été lu dans backend/apps/billing/views_releves.py et backend/apps/planning/views_preparation_tournee.py.

**À préserver :**

- Le champ NOUVEL INDEX est très lisible en plein soleil : cadre cyan de 2 dp, chiffres monospace de grande taille, rappel « min. 130,67 » et consommation calculée en direct. L'index inférieur au précédent est signalé en rouge dès la frappe (MainActivity.kt:3257-3333, capture 09).
- Le libellé des points est précis et utile : « idxls — abonné · index précédent », tri numérique par idxls (2 avant 10), icône de type, filtre par parcelle seulement pour les longues listes, recherche par nom ou idxls et mode « proches de moi » (ReadingPointListRules).
- Les points déjà relevés ce mois sont masqués par défaut avec une bascule explicite, ce qui réduit la liste et le risque de doublon. Après Enregistrer, le point suivant est présélectionné et le bouton annonce « Enregistrer · point suivant ».
- L'offline-first est rassurant : mise en file immédiate, « Rien n'est perdu : tout est gardé sur le téléphone », compteurs relevés/photos/conflits, conflits remontés en tête avec « Corriger » et « Comparer », double confirmation avant Forcer ou Supprimer.
- Le mode correction fonctionne tant que le relevé est en file : champs préremplis, badge « Mode correction », bouton « Corriger le relevé ». La facture 80 mm se calcule hors ligne avec blocage d'écart à ±50 % et rappel des impayés séparé du total.
- Le système de design est cohérent : accentedCard et Tone, boutons principaux de 52 à 64 dp, retour sonore et haptique à l'enregistrement, pastille de synchro avec contentDescription détaillée, onglets avec stateDescription.
- Le client Ktor partagé a un repli sur l'ancien client réseau, et le snapshot décodé est gardé en mémoire (OfflineStore.kt:29-31) pour éviter les ANR au démarrage.

### COEUR-01 — La fin de chaque synchronisation efface la saisie en cours : l'écran Relevés est entièrement reconstruit

- **Sévérité** : Critique
- **Écran** : Relevés > saisie de campagne (renderCampaignReading)
- **Catégorie** : workflow · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (contre-épreuve : réfutation échouée)

**Constat.** Après un Enregistrer en ligne, commitReading lance synchronize() puis affiche aussitôt le point suivant. Pendant que l'agent tape l'index suivant, l'envoi puis le téléchargement complet de la tournée (le hash change après chaque relevé) se terminent et rappellent renderCurrentScreen(). Tous les champs sont recréés : l'index, la remarque, le non-facturé et les cartes sociales saisis sont perdus, et le point sélectionné (par le Spinner, la recherche ou « proches de moi ») revient au premier de la liste. Aucun brouillon n'est conservé. Il suffit d'une coupure réseau courte pour que onAvailable relance le même cycle.

**Impact pour l'agent.** Sur réseau rural lent, la fenêtre dure de quelques secondes à plusieurs dizaines de secondes, à chaque relevé. L'agent perd ce qu'il vient de taper et doit ressaisir. Il peut aussi ne pas remarquer que le point a changé et enregistrer l'index sur le mauvais point (erreur de données).

**Preuve (version 2.12.0).** MainActivity.kt:1083-1093 : à la fin de synchronize(), runOnUiThread appelle renderCurrentScreen() (ou showApplication(false) en tablette) sans aucune garde. MainActivity.kt:3570-3606 et 3618 : updateLastReading(0) vide l'index (l.3603), la remarque et le non-facturé, et le Spinner repart sur le 1er point restant. Déclencheurs de synchro : commitReading l.3747, NetworkCallback.onAvailable l.496-499, retours GPS/photo/téléphone. MainActivity.kt:1057-1063 : afterQueue re-télécharge la tournée entière. Côté serveur, views_preparation_tournee.py:1046 calcule snapshot_version sur tout le contenu, dont dernier_releve, donc il change après chaque relevé. OfflineStore.kt:29-31 parle de « plusieurs Mo » ; HydriaApi.kt:318 fixe un readTimeout de 120 s.

**Vérification sur 2.12.0.** app/src/main/java/mg/hydria/app/MainActivity.kt:1083-1091 : le runOnUiThread final de synchronize() fait `if (windowWidth.isTablet ...) showApplication(initial = false) else renderCurrentScreen()` sans aucune garde, même quand la tournée renvoie not_modified. MainActivity.kt:3603-3605 (updateLastReading) : `index.text.clear(); remark.text.clear(); nonFacture.setText("0")` ; l.3617-3618 `updateLastReading(0)` ; l.3053 `spinner(pointItems...)` recréé à chaque rendu, jamais repositionné (seul pointSpinner.setSelection : l.3876, clic sur la liste tablette). commitReading l.3742-3754 : enqueue, synchronize(), puis renderCurrentScreen(). — Réfutation tentée, échec. (1) Aucune garde : renderCurrentScreen() (l.1111-1124) fait content.removeAllViews() puis reconstruit tout ; le seul ordre « saisie en cours » n'existe nulle part. (2) Aucun brouillon : grep draft|brouillon sans résultat dans MainActivity ; les TextWatcher de l'index (l.3292-3296) ne font que recalculer l'affichage. (3) Le point sélectionné n'est pas mémorisé : retour à la position 0 de la liste filtrée (ou du plus proche en mode GPS). (4) Déclencheurs confirmés : commitReading l.3747, NetworkCallback.onAvailable l.496-499, plus ~15 autres appels à synchronize(). (5) afterQueue (l.1057-1063) re-télécharge la tournée ; le serveur (backend/apps/planning/views_preparation_tournee.py:426-484 et 1046-1050) inclut dernier_releve dans snapshot_version, donc le hash change après chaque relevé et le téléchargement est complet. Même sans changement, le rendu a lieu. Précision de sévérité : la perte n'est pas permanente (l'agent ressaisit) et sur réseau rapide la fenêtre est invisible ; sur réseau rural lent (envoi + tournée complète + config salaire, timeout 120 s) la fenêtre dure de quelques secondes à plusieurs dizaines et recoupe presque toujours la frappe suivante. Risque réel de relevé enregistré sur le mauvais point si l'agent avait choisi un point par le Spinner (retour au 1er) et ne remarque pas le changement ; seuls garde-fous : index >= dernier index et distance GPS > 250 m (si GPS capturé, facultatif). Je maintiens « critique » (flux central, systématique sur le réseau visé, risque d'erreur de donnée) en bas de l'échelle ; correctif S : ne pas rappeler renderCurrentScreen() depuis synchronize() sur READINGS + campagne active, ou brouillon + sélection par id.

**Recommandation.** 1) Garde immédiate (S) : dans le runOnUiThread de synchronize(), ne pas appeler renderCurrentScreen() ni showApplication() si currentScreen == READINGS && campaignOuvrageId != null (ou si un champ du formulaire n'est pas vide) ; se limiter à updateStatus(). 2) Brouillon (M) : garder dans l'Activity un readingDraft (pointId, index, remarque, nonFacturé, cartes) alimenté par les TextWatchers et réappliqué dans updateLastReading ; sélectionner le point par id et non par position 0. 3) Ne plus télécharger la tournée complète après un simple envoi de relevé : exécuter fetchTour à l'ouverture, en manuel ou au plus toutes les N minutes, et mettre à jour localement dernier_releve et releve_mois_courant du point à l'accusé de réception.

### COEUR-02 — Un relevé refusé par le serveur reste bloqué dans la file sans moyen de le corriger ; la règle « remarque obligatoire » n'est pas contrôlée dans l'appli

- **Sévérité** : Majeur (initialement Critique)
- **Écran** : Relevés > Enregistrer ; Centre de synchronisation
- **Catégorie** : workflow · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (contre-épreuve : réfutation échouée)

**Constat.** Un kiosque non utilisé (index identique, consommation nulle) est enregistré sans remarque : l'appli répond « Relevé enregistré ». À la synchro, le serveur refuse avec un 400, ce qui n'est pas un « conflit » pour l'appli. Le relevé reste en file marqué « Erreur » à chaque tentative, et la seule action offerte est « Supprimer de la file », avec un texte pour développeur (« fonctionnalité pas encore activée côté serveur »). Le mode correction existe pourtant (openReadingCorrection) mais n'est accessible que pour les 409. Entre-temps le relevé en file compte comme « fait » dans les compteurs.

**Impact pour l'agent.** Le refus est découvert plus tard, loin du point d'eau. Le seul recours visible est de supprimer le relevé puis de revenir sur place le refaire, ce qui représente du travail perdu et un point de campagne faussement terminé. Le cas consommation nulle est fréquent sur les kiosques peu utilisés.

**Preuve (version 2.12.0).** Serveur : backend/apps/billing/views_releves.py:2982 et :2988 renvoient HTTP 400 (« La remarque est obligatoire si la consommation est égale à 0 » ; « Le champ remarque est obligatoire si le volume non facturé est différent de 0 ») ; :2959 renvoie 400 « Index refuse » si un autre agent a saisi un index plus récent. Client : shared/.../readings/ReadingValidation.kt ne contient aucune règle sur la remarque ; MainActivity.kt:3345 intitule le champ « Remarque (optionnelle) » ; prepareReading l.3664-3730 ne la vérifie pas. MainActivity.kt:5302-5313 : « Corriger » n'est proposé que si isSyncConflict (409 ou erreur commençant par « Conflit », QueueOverviewGateway.kt) ; l.5282-5300 : toute autre erreur n'offre que « Supprimer de la file ».

**Vérification sur 2.12.0.** backend/apps/billing/views_releves.py:2979-2989 : HTTP 400 « La remarque est obligatoire si la consommation est égale à 0 » et « Le champ remarque est obligatoire si le volume non facturé est différent de 0 » (+ « Index refuse » 400 juste avant, ~l.2953-2962). Client : shared/src/commonMain/kotlin/mg/hydria/shared/readings/ReadingValidation.kt (enum ReadingError sans règle remarque) ; MainActivity.kt:3345 `field("Remarque (optionnelle)")`, prepareReading l.3664-3730 ne contrôle pas la remarque ; MainActivity.kt:5141-5142 isSyncConflict -> QueueOverviewGateway.isConflict = payload contient `_sync_conflict` (posé seulement sur 409 par QueueSyncEngine.kt) ou erreur commençant par « Conflit » (QueueOverview.kt:13-14) ; MainActivity.kt:5281-5300 : pour une erreur non-conflit seul « Supprimer de la file » (texte « fonctionnalité pas encore activée côté serveur ») ; « Corriger » uniquement dans `if (conflict)` (l.5302-5313). — Défaut confirmé, mais sévérité à réviser à « majeur ». Confirmé : aucune règle remarque dans shared/ ni dans l'app (grep remark/remarque/obligatoire) ; le serveur rejette en 400 (donc jamais 409, pas de _sync_conflict) ; la file garde l'élément en erreur à chaque synchro ; le relevé refusé reste dans campaignQueuedMap (MainActivity.kt:2892-2915) donc compté « fait » (completed/remaining). Aucun réglage serveur ne remplit la remarque avant le contrôle (la remarque `ticket_local`/repère est ajoutée après, l.3041-3047). Atténuations trouvées qui empêchent « critique » : (a) l'erreur serveur est affichée en rouge dans le centre de synchro avec un texte explicite, et en toast « Synchronisation reportée : … » à chaque fin de synchro (updateStatus l.5464) ; (b) la pastille d'en-tête reste en WARNING avec le compteur > 0 ; (c) un chemin de correction existe en réalité : écran Relevés > interrupteur « Voir mes saisies de cette campagne » (campaignShowDone) sélectionne le relevé en file en mode correction (updateLastReading l.3586-3595), commitReading supprime l'ancienne entrée (l.3738-3739) et ré-enfile, sans déplacement sur place ; mais rien n'y renvoie depuis l'erreur, et le libellé de « Supprimer » pousse à détruire le relevé. Le défaut reste réel (pas de validation côté client, « Corriger » réservé aux 409, texte développeur, relevé compté comme fait) et correctif S ; il génère du retard de facturation et du travail perdu, pas une perte irréversible.

**Recommandation.** 1) Ajouter dans shared ReadingValidation deux erreurs (REMARK_REQUIRED_ZERO_CONSUMPTION et REMARK_REQUIRED_NON_BILLABLE, avec leurs tests partagés) et les traiter dans prepareReading : remark.error = « Remarque obligatoire : consommation nulle ». Rendre le libellé du champ dynamique, « Remarque (obligatoire) » quand la consommation vaut 0 ou que le non-facturé est différent de 0, dans refreshConsumption(). 2) Dans syncCenterItemCard (l.5302), afficher « Corriger » pour tout relevé en erreur (type == "reading" && last_error non vide), pas seulement en conflit ; openReadingCorrection fonctionne puisque l'entrée reste en file. 3) Présenter l'erreur serveur comme une consigne (« Le bureau a refusé ce relevé : remarque obligatoire. Corrigez-le ») et masquer « Supprimer » derrière « Plus d'options ».

### COEUR-03 — Enregistrer est à environ deux écrans du champ index : 5 à 6 gestes par relevé, 8 à 9 si le point suivant n'est pas le premier de la liste

- **Sévérité** : Majeur
- **Écran** : Relevés > saisie de campagne
- **Catégorie** : ergonomie · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Décompte pour un relevé : toucher le champ (1), taper les chiffres, fermer le clavier ou défiler (1), balayer 1 à 2 fois (1-2), toucher Enregistrer (1), soit 5 à 6 gestes. La page est ensuite reconstruite en haut avec le 1er point présélectionné, ce qui est bien. Mais si l'agent suit l'ordre physique des abonnés, il faut en plus ouvrir le Spinner, défiler et choisir (2-3 gestes), ou taper une recherche : 8 à 9 gestes. Trois blocs d'exception (GPS, fiche à compléter, cartes sociales) se trouvent sur le chemin entre l'index et Enregistrer. L'en-tête, la pastille et la barre d'onglets restent affichés pendant la saisie.

**Impact pour l'agent.** Pour un ouvrage de 53 points, cela fait plus de 300 gestes de navigation, sur la tâche la plus répétitive de l'application. Cela entraîne fatigue, saisie à une main difficile et incitation à sauter les contrôles.

**Preuve (version 2.12.0).** MainActivity.kt:3622-3655 donne l'ordre des blocs : point d'eau, alerte BP, badge correction, dernier relevé, NOUVEL INDEX, info GPS + bouton, fiche à compléter (GPS/photo/téléphone), cartes sociales, non facturé, volume facturé, remarque, anciennes factures. saveButton n'arrive qu'à la ligne 3845, en fin de ScrollView. Au-dessus de l'index : 2 à 3 interrupteurs (l.2933, 3009, 3055), parcelle (l.3094) et recherche (l.3121). Capture 09 : l'index occupe y≈1190-1425 px, au bord bas de l'écran. Capture 10 : Enregistrer est à y≈1195-1303 px après un défilement d'environ 1 076 px. Aucun focus automatique sur l'index ni d'action clavier (IME_ACTION n'est utilisé que l.3100 pour la recherche).

**Recommandation.** Réordonner renderCampaignReading ainsi. (1) Bandeau point compact : nom de l'abonné, type, « dernier 130,67 · min. ». (2) Carte NOUVEL INDEX avec index.requestFocus() à l'ouverture et imeOptions = IME_ACTION_DONE qui lance prepareReading ; consommation et volume facturé juste dessous. (3) Barre d'action fixe en bas, hors du ScrollView (footer ajouté à content) : « Enregistrer · point suivant » en principal, « Calculer et imprimer » en secondaire, plus des boutons « point précédent / suivant ». (4) Remarque, non facturé, cartes sociales, GPS, fiche à compléter et anciennes factures dans une section « Plus de détails » repliée, qui s'ouvre d'elle-même quand une règle l'exige (remarque obligatoire, kiosque). (5) Parcelle, recherche, proches de moi et « voir mes saisies » regroupés dans un sélecteur « Choisir un point » en bottom sheet, avec l'index déjà saisi affiché par ligne.

### COEUR-04 — Aucun garde-fou contre la faute de frappe ou le mauvais point : à l'enregistrement, seul « index inférieur au précédent » est contrôlé

- **Sévérité** : Majeur
- **Écran** : Relevés > Enregistrer
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Un chiffre en trop (1 300 au lieu de 130), un zéro oublié ou une consommation nulle sur un point qui consomme d'habitude sont acceptés sans question et mis en file. L'écart n'est détecté qu'au moment d'imprimer (±50 %) ou plus tard par le directeur. La confirmation ne dit ni quel point ni quel index a été enregistré. Corriger une faute vue juste après n'est possible qu'en ouvrant « Voir mes saisies » puis en retrouvant le point.

**Impact pour l'agent.** Une facture aberrante part chez l'abonné ou chez le directeur. Une faute évidente à l'écran n'est pas rattrapable d'un geste. Sur 53 points sans contrôle de distance par défaut, le risque de relevé sur le mauvais point est réel.

**Preuve (version 2.12.0).** shared/.../readings/ReadingValidation.kt : 6 règles, aucune de plausibilité. MainActivity.kt:3664-3730 (prepareReading). Le GPS n'est jamais capturé automatiquement (commentaire l.3148-3150) ; la garde des 250 m (l.3757-3766) ne joue que si l'agent touche le bouton et si le point a des coordonnées (capture 01 : 128 points sans GPS). moyenne_consommation et nb_releves_precedents sont déjà préchargés (views_preparation_tournee.py:485-488) mais ne servent qu'au blocage d'impression (ReadingTicketGateway.kt:36-40). MainActivity.kt:3748-3751 : toast « Relevé enregistré · N point(s) restant(s) » sans le point ni l'index. Aucune annulation.

**Recommandation.** Dans prepareReading, réutiliser ReadingPrintRules.deviation (déjà dans shared) et ajouter des seuils : consommation supérieure à 5 fois la moyenne, consommation nulle alors que la moyenne est positive, ou index ayant plus de chiffres que l'ancien. Dans ces cas, ouvrir un AlertDialog : « Leonce : index 1 300, soit +1 170 m³ (moyenne 12 m³). Corriger / Confirmer ». Remplacer le toast post-enregistrement par une Snackbar « Leonce · 131,50 enregistré, ANNULER » (8 s) qui retire l'entrée (store.remove) et retarde synchronize() d'autant. Afficher le nom de l'abonné dans la carte NOUVEL INDEX. Option : capture GPS passive à l'ouverture du formulaire pour activer l'alerte de distance sans bloquer.

### COEUR-05 — Progression et fin de campagne fausses dès qu'on est en ligne ; « Corriger une saisie » mène à une impasse et re-saisir crée un doublon

- **Sévérité** : Majeur
- **Écran** : Relevés > choix d'ouvrage puis campagne
- **Catégorie** : rendu donnees · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** En ligne, chaque relevé est envoyé puis retiré de la file ; au rafraîchissement, le point devient « déjà relevé » et disparaît. La ligne « Relevés de la campagne : 0 / 52 » reste à 0 pendant que le dénominateur baisse, et le dernier point aboutit à « Points masqués » au lieu de « Campagne terminée ». Le choix d'ouvrage annonce « 53/53 » puis, via « Corriger une saisie », la campagne affiche « 0 / 53 » et « Aucun relevé saisi ». Un relevé déjà synchronisé n'est plus corrigeable dans l'appli (le mode correction ne lit que la file). Le re-saisir via « Afficher les points déjà relevés ce mois » crée un second relevé sans avertissement ; le serveur interdit aussi un index inférieur au précédent.

**Impact pour l'agent.** L'agent ne voit jamais sa progression avancer et n'a pas de clôture nette, d'où le doute sur le bon envoi. Une faute de frappe déjà envoyée ne peut pas être réparée ; la ressaisie produit un doublon et une consommation fausse.

**Preuve (version 2.12.0).** Écran de choix : MainActivity.kt:2697-2705 utilise ReadingsRules.monthProgress (relevé côté serveur OU en file). En campagne : l.2910-2915 et 2918-2923 comptent « completed » à partir de la seule file locale, et « total » exclut les points déjà relevés (l.2883-2885). L'écran « Campagne terminée » (l.2965-2995) exige donePoints non vide, donc seulement tant que des relevés sont encore en file ; sinon l.2947-2962 affiche « Points masqués… Activez le bouton ci-dessus ». « Corriger une saisie » (l.2784-2804) active campaignShowDone, puis l.3082-3089 affiche « Aucun relevé saisi pour cette campagne ». Serveur : views_preparation_tournee.py:476-480 (releve_mois_courant) ; views_releves.py:3050 fait un Releve.objects.create, et je n'ai trouvé de déduplication que par local_uuid.

**Recommandation.** 1) Calculer le numérateur avec la même règle que le choix d'ouvrage (monthProgress : releve_mois_courant OU en file) et ne pas retirer du dénominateur les points déjà relevés ; « terminée » = tous les points actifs relevés ou en file. 2) Alimenter « Voir mes saisies » avec dernier_releve (index, date du mois) en plus de la file, avec une pastille « envoyé / en attente ». 3) Avant d'enregistrer un point déjà relevé ce mois, demander « Ce point a déjà un relevé le 29/09 (130,67). Créer un 2e relevé ? ». 4) Pour corriger un relevé envoyé : endpoint serveur de correction, ou message clair « Demandez la correction au bureau » ; renommer le bouton « Revoir mes saisies ».

### COEUR-06 — L'état de synchronisation est illisible pour un non-informaticien : UUID, erreurs réseau brutes, panne passagère présentée comme « Erreur » avec « Supprimer »

- **Sévérité** : Majeur
- **Écran** : Pastille d'en-tête, Centre de synchronisation (showSyncCenter), toasts
- **Catégorie** : feedback etats · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Une carte du centre affiche « Point : 3f9c… » : impossible de savoir quel abonné est concerné. Un échec réseau (« Unable to resolve host… ») s'affiche en anglais dans un toast de 3,5 s qui s'empile avec les autres. Une simple coupure marque la saisie « Erreur » et propose de la supprimer, alors qu'elle repartira seule. La pastille « … » ne dit ni quoi ni combien de temps (jusqu'à 120 s), et un nombre nu n'a pas d'unité. Un relevé enregistré pendant une synchro attend le prochain déclencheur, donc le dernier relevé d'une série peut rester en file (pastille ambre « 1 »). Au retour des autres Activities (Navigation, Volume, Pointage), la pastille n'est pas rafraîchie.

**Impact pour l'agent.** L'agent ne peut ni identifier ce qui est bloqué ni savoir s'il doit attendre, relancer ou corriger. Il peut supprimer des relevés valides à cause d'une coupure passagère, et croire à tort que tout est parti, ou au contraire que rien n'est parti.

**Preuve (version 2.12.0).** QueueJournalGateway.kt (shared, sync) :12 et :32-33 construit « Point : <point_eau_id> » et « Ouvrage : <ouvrage_id> », affiché par MainActivity.kt:5281. QueueSyncEngine.kt : le catch renvoie exception.message (HydriaApi.request, l.305-355, n'a pas de catch). MainActivity.kt:1092 : toast « Synchronisation reportée : $it », y compris quand seul le re-téléchargement de la tournée a échoué (afterQueue l.1057-1081). MainActivity.kt:5282-5300 : toute erreur, même transitoire, donne le badge « Erreur » et « Supprimer de la file » (texte l.5290, avec « fonctionnalité pas encore activée côté serveur »). l.5218 : « Synchroniser » ferme la feuille. Pastille l.5477-5482 : « … », nombre nu, « hors ligne », « à jour ». MainActivity.kt:1017-1022 : la liste des opérations est figée au départ et rien ne relance la synchro à la fin du cycle (l.1083-1093). Aucun onResume (grep). Captures 03 (« … » seul) et 15.

**Recommandation.** 1) Dans syncCenterItemCard, résoudre point et ouvrage à partir de store.snapshot (map id vers « 10 — Leonce · Ambanja ») ; c'est un changement S. 2) Classer les erreurs : réseau, timeout ou 5xx deviennent « En attente de réseau, nouvel essai automatique » (ton neutre, sans bouton Supprimer) ; un refus serveur 400 devient « Refusé : <message> » avec « Corriger » ; « Supprimer » passe dans « Plus d'options » avec un texte compréhensible. 3) Mapper UnknownHost/SocketTimeout vers « Pas de réseau » dans le catch de QueueSyncEngine, et ne plus annoncer « reportée » quand seule la tournée a échoué. 4) Pastille : « envoi 2/5 », « 3 à envoyer » et un état « échec » rouge avec « ! » ; remplacer le toast par une Snackbar persistante avec l'action « Voir ». 5) Relancer synchronize() en fin de cycle si pendingCount() > 0 et qu'il y a eu des progrès ; ajouter onResume() { updateStatus(); synchronisation si en ligne et file non vide }.

### COEUR-07 — Le bouton Retour quitte l'application depuis n'importe quel sous-écran, et le contexte de campagne n'est pas conservé

- **Sévérité** : Majeur
- **Écran** : MainActivity (Relevés > campagne, Terrain > listes, onglets)
- **Catégorie** : ergonomie · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Retour système depuis la saisie d'un relevé, une liste de tâches Terrain ou un onglet autre que Terrain ferme l'application. Au relancement, l'animation d'intro rejoue, l'onglet est Terrain et l'ouvrage, la date et la parcelle de la campagne sont perdus. Le même effet suit une mise à mort du processus (téléphones d'entrée de gamme, retour de l'appareil photo).

**Impact pour l'agent.** Le réflexe Android de « remonter d'un cran » éjecte l'agent hors de l'appli en pleine campagne, et il doit refaire défiler les ouvrages pour retrouver le sien. La saisie non enregistrée est perdue.

**Preuve (version 2.12.0).** Aucune occurrence de onBackPressed, OnBackPressedCallback ni onBackInvokedDispatcher dans app/src/main/java (grep). AndroidManifest : MainActivity en singleTask, racine de la tâche (IntroActivity fait finish()). MainActivity.kt:103-180 : currentScreen (défaut TERRAIN), campaignOuvrageId, campaignDate, terrainCategory, etc. sont des champs de l'Activity. onSaveInstanceState (l.453-474) ne sauve que l'état de la photo. Seuls retours internes : « Changer » (l.2839-2855) et « ← Retour » de la liste de tâches Terrain (l.2110).

**Recommandation.** Dans onCreate, ajouter onBackPressedDispatcher.addCallback(this) qui remonte d'un niveau : campagne active vers le choix d'ouvrage (même code que « Changer »), terrainOpenWorkId/terrainCategory vers le niveau supérieur, onglet différent de Terrain vers Terrain, sinon double appui « Appuyez encore pour quitter ». Persister campaignOuvrageId, campaignDate et campaignParcelId dans les SharedPreferences, et les restaurer par « Reprendre la campagne Ambanja ? ». Option : passer l'intro si une session est active.

### COEUR-08 — « Se déconnecter » : un seul appui, sans confirmation, efface toute la tournée hors ligne et impose le réseau pour se reconnecter

- **Sévérité** : Majeur
- **Écran** : Menu ⋮ (showSessionMenu)
- **Catégorie** : ergonomie · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Une pression accidentelle sur la dernière ligne d'une liste de 7 à 8 entrées déconnecte l'agent, supprime les données préchargées (998 points, tarifs, tickets) et le renvoie sur un écran de connexion qui ne fonctionne qu'avec du réseau. Seule la file non vide protège.

**Impact pour l'agent.** En zone sans couverture, une erreur de tap rend l'application inutilisable jusqu'au retour du réseau, puis impose de retélécharger plusieurs Mo, sans possibilité d'annuler.

**Preuve (version 2.12.0).** MainActivity.kt:5116-5119 : si la file est vide, store.clearSession() puis showLogin(). OfflineStore.kt:581-588 : clearSession() retire le token ET appelle clearSnapshot(). MainActivity.kt:544-548 : le login exige une connexion (« Une connexion est nécessaire pour la première authentification »). MainActivity.kt:5105-5130 : liste texte sans pictogramme ni séparation, où l'entrée « Télécharger la mise à jour » (l.5121-5127) vient s'ajouter après « Se déconnecter » et déplace les positions.

**Recommandation.** Entourer l'action d'une confirmation : « Se déconnecter ? Vous aurez besoin d'internet pour vous reconnecter et recharger votre tournée. » (bouton « Annuler » par défaut). Placer l'entrée dans un groupe « Session » séparé, en rouge. À terme, ne vider le snapshot que si le compte change (garder les données hors ligne pour la reconnexion du même agent).

### COEUR-09 — Changement d'onglet : voile plein écran et spinner figé, car l'onglet entier est reconstruit sur le fil principal (Réparations crée toutes ses cartes d'un coup)

- **Sévérité** : Majeur
- **Écran** : Barre d'onglets, toutes les pages (surtout Réparations)
- **Catégorie** : performance percue · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Chaque changement d'onglet, même vers un écran léger, déclenche un voile gris cliquable avec un spinner qui ne tourne pas, puis la reconstruction complète. Par construction du code, l'onglet Réparations crée plusieurs centaines de vues imbriquées. La cause exacte du temps passé reste à confirmer par un profilage (Systrace ou Android Studio Profiler). Ces reconstructions se produisent aussi, sans voile, quand une synchro se termine : l'écran gèle sans prévenir.

**Impact pour l'agent.** L'agent voit un voile et un spinner immobile et l'écran ne répond plus au toucher : sur un téléphone d'entrée de gamme il croit à un plantage et retape ou relance l'appli.

**Preuve (version 2.12.0).** MainActivity.kt:678-688 : withScreenTransition affiche l'overlay puis exécute renderCurrentScreen() de façon synchrone dans un post ; appliqué aux onglets l.900-910 et au rail l.640-643. HydriaVisuals.kt:441-451 : overlay isClickable avec ProgressBar indéterminée, qui ne peut pas s'animer tant que le fil principal est occupé. MainActivity.kt:4041-4145 : renderRepairs construit toutes les cartes (repairActivityCard l.4147+) dans un ScrollView, sans pagination ni RecyclerView. MainActivity.kt:1090-1091 : la même reconstruction est lancée sans voile à chaque fin de synchro. MainActivity.kt:987-994 : repairsBadgeCount re-parse la liste à chaque updateNavigationState/updateStatus, avec store.pending() (SQLite) sur le fil UI. OfflineStore.kt:360-364 : le setter de snapshot garde snapshotLock pendant saveSnapshot, alors que le getter, appelé depuis l'UI, prend le même verrou. Capture 03 : le voile et le spinner recouvrent l'écran Relevés déjà dessiné.

**Recommandation.** 1) Garder la vue construite de chaque onglet (un conteneur par Screen) et ne la reconstruire que si la version du snapshot ou de la file a changé. 2) Réparations : n'afficher que les 10 premiers ouvrages puis « Afficher plus », ou passer à un RecyclerView. 3) Supprimer le voile pour les onglets légers ou le remplacer par un squelette non bloquant. 4) Mettre en cache repairsBadgeCount par version de snapshot. 5) Dans OfflineStore, n'écrire le snapshot en base qu'en dehors du verrou, et ne verrouiller que l'échange de la référence mémoire.

### COEUR-10 — Début de journée : l'appli s'ouvre sur la complétude du périmètre (27 %, 3 601 tâches) plutôt que sur le travail du jour ; « tournée » a trois sens ; choix d'ouvrage non recherchable

- **Sévérité** : Majeur
- **Écran** : Accueil (Terrain), Planning, Relevés (choix d'ouvrage)
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Le premier écran met en avant un score d'exhaustivité des fiches et un grand bouton « Commencer ma tournée », alors que les relevés dus (0/998), les réparations en retard (badge) et les rendez-vous du jour sont répartis dans trois autres onglets. Le mot « tournée » désigne à la fois la collecte de fiches Terrain, le snapshot préchargé et le planning. Pour reprendre un relevé, il faut passer par Relevés puis faire défiler jusqu'à l'ouvrage parmi 52, sans mémoire de la dernière campagne.

**Impact pour l'agent.** L'agent peut suivre le plus gros bouton (collecte de fiches) au lieu des relevés dus ; chaque début de campagne coûte plusieurs défilements.

**Preuve (version 2.12.0).** MainActivity.kt:103 (currentScreen = TERRAIN par défaut). Capture 01 : « 27 % », « 3601 tâches restantes » et bouton orange « Commencer ma tournée », qui lance startTerrainBatch de tâches de complétude (MainActivity.kt:5107-5111). Capture 04 : le travail du jour (« 8 RDV ») se trouve dans Planning. Capture 02 et MainActivity.kt:2758-2815 : 52 cartes d'environ 200 px dans l'ordre alphabétique du serveur, sans recherche ni « reprendre » (alors que Terrain a un champ de recherche d'ouvrage, l.1331). l.2664 : « Aucune tournée préchargée » désigne le snapshot ; l'onglet Planning s'appelle « Agenda terrain ».

**Recommandation.** Architecture cible : 4 onglets plus l'accès Pointage. « Aujourd'hui » (prochain créneau de pointage, RDV du jour, « Relevés à faire : Ambanja 0/53, Reprendre », réparations en retard, état de synchro), « Relevés », « Terrain » (complétude, Carte, « Compléter les fiches » à la place de « tournée ») et « Réparations ». Court terme (S-M) : onglet par défaut = Relevés ou dernier onglet utilisé ; carte « Reprendre ma campagne » en tête du choix d'ouvrage ; champ de recherche (réutiliser l'approche de renderTerrainWorks) ; ouvrages en cours avant les non commencés ; renommer le CTA orange.

### COEUR-11 — En-têtes et retours incohérents d'une Activity à l'autre ; le menu ⋮ est une liste texte qui cache calculatrice, volumétrique et carte

- **Sévérité** : Mineur
- **Écran** : En-tête MainActivity, menu ⋮, Activities Pointage, Volume, Calculatrice, Recherche, Carte
- **Catégorie** : coherence · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Chaque écran compose son propre en-tête : deux glyphes de retour différents, trois tailles, une absence totale de flèche dans Volumétrique. L'en-tête de l'écran principal dit « Terrain » même sur Relevés ou Planning et affiche la version de l'appli à la place du périmètre. Les outils d'usage courant (Calculatrice, Workflow volumétrique) ne se trouvent que dans une liste texte sous ⋮, une zone petite et difficile à atteindre à une main. Volumétrique peut se croire hors ligne quand le reste de l'appli synchronise.

**Impact pour l'agent.** L'agent ne sait pas toujours où il est ni comment revenir, découvre mal les outils et ne voit pas l'état de la file hors de l'écran principal.

**Preuve (version 2.12.0).** MainActivity.kt:690-730 : titre fixe « Terrain » (l.702) sur tous les onglets (captures 02 et 04) ; seconde ligne « HERIZO · v2.11.0 » car perimeterLabel() retombe sur la version (l.1004) ; bouton « Recherche » textuel plus pastille de 38 dp plus ⋮ de 38×38 dp (< 48 dp). MainActivity.kt:5105-5130 : AlertDialog.setItems, texte seul, avec des doublons (« Carte terrain » = bouton Carte de la capture 01 ; « Synchroniser maintenant » et « Centre de synchronisation » alors que la pastille ouvre déjà le centre). Retours : PointageActivity.kt:158-170 (bandeau + « ← » 48×44 + titre 19 sp) ; AdvancedCalculatorActivity.kt:111 (« ← ») ; SearchActivity.kt:127-130 et SearchDetailActivity.kt:111 (« ‹ ») ; RecentInterventionsActivity.kt:77 (« ‹ » 52×48, sans contentDescription) ; VolumeActivity.kt:53-56 (aucun bouton retour, titre 23 sp ; « Retour » caché dans le dialogue « Outils », l.143-149). VolumeActivity.kt:128-131 exige NET_CAPABILITY_VALIDATED alors que MainActivity.kt:5507-5514 l'écarte volontairement. Aucune de ces Activities n'affiche la pastille de synchro.

**Recommandation.** Créer HydriaUi.screenHeader(activity, titre, sous-titre, onBack, trailing) : flèche 48×48 avec contentDescription « Retour », titre 20 sp, pastille de synchro optionnelle ; l'utiliser dans toutes les Activities, y compris Volume. Titre dynamique selon screenLabel(currentScreen) ; remplacer la seconde ligne par le périmètre ou le nom seul. Transformer le ⋮ (48 dp) en bottom sheet « Outils » avec pictogrammes et deux groupes : Outils (Calculatrice, Carte, Volumétrique) et Session (Synchroniser, Mise à jour, Se déconnecter). Mutualiser isOnline() (critère INTERNET uniquement) dans HydriaNetwork.

### COEUR-12 — Les parcours de relevé et de synchronisation n'existent qu'en français : le malgache ne couvre que la calculatrice

- **Sévérité** : Mineur
- **Écran** : Toute l'application (Relevés, Centre de synchro, erreurs de validation)
- **Catégorie** : i18n · **Effort** : L
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** La machinerie de localisation existe et la calculatrice est entièrement traduite, mais aucun écran du coeur de métier (relevé, synchro, erreurs, nav) ne l'utilise. Les règles partagées (ReadingValidation, QueueOverview) renvoient du texte français ou des erreurs en dur.

**Impact pour l'agent.** Un agent à l'aise surtout en malgache lit en français les consignes et erreurs les plus importantes (remarque obligatoire, index refusé, conflit), là où il faudrait justement le plus de clarté.

**Preuve (version 2.12.0).** res/values-mg/strings.xml : 160 chaînes, essentiellement la calculatrice et tools_and_session. MainActivity.kt n'appelle getString(R.string…) que 2 fois sur environ 5 600 lignes. Textes en dur : l.3345 « Remarque (optionnelle) », l.3689 « L'index doit être supérieur ou égal à $oldIndex », l.5170 « Travail en attente », QueueOverview.kt (typeLabel, status). Le message d'index affiche $oldIndex brut (« 130.67 ») alors que le reste utilise formatNumber (« 130,67 »).

**Recommandation.** Extraire par étapes les textes vers strings.xml, en commençant par le pilote Relevés + Centre de synchronisation. Faire renvoyer aux règles partagées des clés (enums) plutôt que du texte, mappées côté app. Uniformiser les nombres via formatNumber, dont le message d'index. Faire relire par un agent malgachophone ; en attendant, renforcer pictogrammes et couleurs d'état.


## Transverse : système de design, données, malgache, accessibilité

_Audit initial sur la version 2.12.0._

**Synthèse du domaine.** Le socle du système de design est sain : palette tokenisée (values/ et values-night/), deux thèmes pilotés par ressources, chiffres en monospace, filet de criticité, et un mode sombre très bien calibré (texte 16,7–18,2:1, accents 7,5–9,9:1, secondaire 8,2–8,9:1). Les écarts viennent de ce qui n'a pas suivi le socle. (1) Le malgache n'existe que dans la calculatrice : ≈ 75 % du texte visible est du français codé en dur, sans sélecteur de langue ni locales_config. (2) Il n'y a aucun formateur commun : montants, volumes, dates et pluriels sont rendus de six façons, dont la facture A4 volumétrique imprimée pour le client (« 12500.00 Ar », « Relevé du 2026-09-29 ») et les écrans Volume. (3) Le mode clair, censé être « lisible au soleil », reste à 3,4–4,4:1 pour les textes de ton et les puces, 3,0–3,3:1 pour le texte atténué et 1,35:1 pour les bordures de champs. (4) L'échelle typographique déclarée dans dimens.xml n'est utilisée nulle part : ≈ 28 tailles coexistent et 63 % des appels sont ≤ 13 sp, soit ≈ 11 sp effectifs à l'échelle 0,85 de l'appareil réel. (5) Des cibles de 30 à 40 dp subsistent sur des actions quotidiennes (puces de mode, pastille de synchro, menu ⋮). Presque tout se corrige dans HydriaVisuals.kt, colors.xml et un module de formatage partagé, sans toucher aux écrans un par un ; seule l'internationalisation exige un vrai chantier.

**À préserver :**

- Système de couleurs propre : 22 jetons lus depuis les ressources (HydriaColors.bind), thèmes clair et sombre auto via values/ et values-night/. Seuls 14 fichiers contiennent des couleurs en dur, surtout cartes et impressions.
- Mode sombre solide : texte principal 16,7–18,2:1, secondaire 8,2–8,9:1, cyan 9,9:1, success 9,0:1, warning 8,9:1, vase 7,5:1, error 6,5:1, texte sur accent plein 7,2–11,0:1. Les puces teintées restent à 5,3–8,1:1.
- Conception tonale cohérente : l'enum Tone avec toneColor/toneWash centralise urgence, succès et alerte. Le filet de criticité et le grand chiffre monospace donnent une hiérarchie lisible d'un coup d'œil.
- Bases d'accessibilité réelles : une trentaine de contentDescription sur les boutons-icônes (menu ⋮, recherche, retour, effacer, retirer carte), états « sélectionné » des onglets, description de la pastille de synchro et de la barre de progression. Cibles généreuses sur les actions principales : bouton primaire 64 dp, champs 56 dp, champ d'index 76 dp, barre d'onglets 74 dp.
- Les 161 clés MG de la calculatrice sont cohérentes avec le français : aucun placeholder %1$s décalé, un plurals correct, et une calculatrice entièrement traduite avec 180 appels R.string.
- Saisie décimale tolérante (replace(',', '.') sur 10 champs) et fuseau Indian/Antananarivo explicite dans le pointage et le volume. ReadingTicketFormat.amount produit un groupement propre « 12 500 Ar » et il est testé (ReadingTicketTest).
- Tickets de caisse bilingues avec libellés malgaches (FAKTIORA LAHARANA, TROSA TALOHA) : une bonne base à généraliser.

### TRANSVERSE-01 — Le malgache n'existe que dans la calculatrice : ≈ 75 % du texte visible reste en français codé en dur

- **Sévérité** : Majeur
- **Écran** : Toute l'application (menu de session, onglets, Terrain, Relevés, Réparations, Planning, Pointage, Volume, Recherche)
- **Catégorie** : i18n · **Effort** : L
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Un agent dont le téléphone est en malgache obtient un hybride : calculatrice en malgache, tout le reste en français. Rien dans l'appli ne permet de changer de langue ; le malgache n'est atteignable que si la langue système est « Malagasy ». Le module partagé (commonMain) ne peut pas utiliser R.string, donc les libellés métier de PlanningAgenda, RepairRules, QueueOverview et ReadingTicket sont figés en français ou en malgache selon le cas.

**Impact pour l'agent.** Des agents à littératie numérique variable, pour qui le malgache est la langue courante, doivent lire des phrases d'erreur, de statut et de consigne en français. Les états de synchronisation et de relevé sont ceux où l'on décide d'agir ou non.

**Preuve (version 2.12.0).** res/values/strings.xml : 172 clés ; res/values-mg/strings.xml : 161 clés, toutes calculatrice, salaire ou GPS. R.string. est appelé 180 fois dans calculator/AdvancedCalculatorActivity.kt et 3 fois ailleurs (HydriaWindow.kt:125 ; MainActivity.kt:5092 et 5112). Hors calculatrice, comptage par motif : ≈ 600 lignes de libellés en dur, dont MainActivity ≈ 280, NavigationTerrainActivity ≈ 82, RecentInterventionsActivity ≈ 66, VolumeActivity ≈ 39, SearchActivity ≈ 34, soit un taux de texte traduisible ≈ 23 % (estimation). Aucun localeConfig, setApplicationLocales ni sélecteur de langue (grep vide dans AndroidManifest.xml et build.gradle.kts). Menu de session MainActivity.kt:5092-5119 : titre « Fitaovana sy kaonty » (MG) au-dessus d'entrées en français (« Synchroniser maintenant », « Se déconnecter »). Il manque 11 clés gps_phone_* en MG. Mois et jours : shared/planning/PlanningAgenda.kt:25-27. Libellés d'état : HydriaVisuals.kt:334 (« à jour »). Les tickets imprimés sont en malgache en dur (shared/readings/ReadingTicket.kt:85-136) alors que l'écran est en français.

**Recommandation.** 1) Mécanisme : res/xml/locales_config.xml (fr, mg), android:localeConfig, AppCompatDelegate.setApplicationLocales et une entrée « Langue / Fiteny » dans showSessionMenu (MainActivity.kt:5088). 2) Extraction par ordre de visibilité : HydriaVisuals (syncChip, taskRow, accessibilité), libellés des onglets et du menu, titres et sous-titres des tâches Terrain (TerrainTaskDef), statuts de planning et de réparation, puis formulaires. 3) Pour shared/commonMain : une interface HydriaStrings fournie par chaque plateforme, ou remplacer les tableaux mois/jours par des tables FR et MG. 4) Ajouter les 11 clés gps_phone_*. 5) Activer le lint SetTextI18n/HardcodedText en erreur sur le nouveau code. Faire valider les termes MG par un agent terrain.

### TRANSVERSE-02 — Aucun formateur commun : montants, volumes et nombres sont rendus de six façons, y compris sur la facture A4 imprimée au client

- **Sévérité** : Majeur
- **Écran** : Workflow volumétrique (écrans et facture A4), Terrain, Relevés, tickets
- **Catégorie** : rendu donnees · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Chaque écran formate à sa manière : tantôt « 12 500 Ar », tantôt « 12500.00 Ar », tantôt « 12500 » ; les décimales sont virgule à l'écran, point dans les champs et sur le ticket ; les volumes affichent 0 ou 2 décimales selon la valeur ; les entiers ne sont pas groupés. Les sentinelles d'API ("N/A", "-", null) sont filtrées au cas par cas. Le document imprimé pour l'abonné est celui qui expose le plus de valeurs brutes.

**Impact pour l'agent.** Un montant à 7 chiffres sans séparateur (« 1234500.00 ») se lit mal en plein soleil et fait commettre des erreurs de pointage. Le client reçoit une facture A4 avec des dates ISO et des « .00 » alors que son ticket terrain est en format malgache.

**Preuve (version 2.12.0).** VolumePrinter.kt:57-73 imprime « À PAYER : ${invoice.getString("montant")} Ar », « Ancien index : … m³ » et « Relevé du ${date_releve} ». Le serveur envoie `'montant': format(Decimal,'f')` (« 12500.00 »), `str(ancienindex)` et `str(datereleve)` (backend/apps/billing/views_mobile_volume.py:70-76). VolumeActivity.kt:230, 231, 249, 258, 306, 320, 345, 380, 402 interpolent `${total} Ar` (BigDecimal, ex. « 37500.00 ») ou optString("montant"). Le ticket terrain, lui, affiche « 12 500 Ar » (ReadingTicketFormat.amount, ReadingTicket.kt:56). MainActivity.kt:1181 et 1191-1193 : « 3601 tâches restantes », « 1725 points », « 401 ouvrages » non groupés, alors que formatNumber (MainActivity.kt:5038-5040, 20 appels) groupe ailleurs en Locale.FRANCE. MainActivity.kt:1974 : « Index précédent : 130.67 · 2026-09-29 » (point décimal et date ISO) alors que le même flux affiche « 130,67 » ; 3590-3592 pré-remplit le champ avec un point. ReadingTicketFormat.quantity imprime « 53.00 m3 » (point, sans ³). VolumeActivity.kt:258 et 320 : le serveur renvoie `montant: null` pour une facture non calculable ; d'après le comportement d'org.json sur Android, optString("montant", "—") renvoie alors la chaîne « null » (cf. gardes `!= "null"` déjà en SearchDetailActivity.kt:543 et TerrainEditRules.kt:29) → « … · null Ar ». Valeur vide : « — » (20 occurrences), « - » (11), « ? » (5), « N/A » (5), « Non renseigné » (6).

**Recommandation.** Créer shared/src/commonMain/kotlin/mg/hydria/shared/format/HydriaFormat.kt en étendant ReadingTicketFormat (déjà testé, commonMain donc partagé avec Desktop) : ariary(Double|BigDecimal|String?) → « 12 500 Ar » avec U+00A0 ; m3(valeur, décimales) → « 130,67 m³ » (variante point réservée au ticket via un paramètre) ; count(n) groupé ; EMPTY = "—" ; cleanJson(String?) qui ramène "null", "N/A", "-" et vide à null. Y ajouter ensuite dateFr(iso) et plural(n, un, autres) (voir TRANSVERSE-07 et TRANSVERSE-09). Remplacer d'abord VolumePrinter.kt:57-73, VolumeRecapPrinter.kt:80-92, VolumeActivity.kt (9 sites) et MainActivity.kt:1181, 1191-1193, 1974, 3590-3592. Ajouter un test commonTest avec les cas 0, 1 234 567, négatif, null et « N/A ».

### TRANSVERSE-03 — Mode clair : textes de ton, puces et bordures loin de l'objectif 7:1 « au soleil »

- **Sévérité** : Majeur
- **Écran** : Tous les écrans en mode clair (puces de synchro, badges, boutons pleins, champs, cartes)
- **Catégorie** : accessibilite · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Le mode clair n'atteint même pas le 4,5:1 qu'il annonce pour les accents, et les petits textes teintés (la pastille « à jour », les badges de priorité, « Normale ») sont à 3,4–4,4:1. Les contours des champs et des cartes sont presque invisibles : 1,35:1 contre 3:1 attendu pour délimiter un composant interactif. Un même jeton sert au remplissage (barres) et au texte (chiffres de tâche), ce qui empêche de durcir l'un sans l'autre.

**Impact pour l'agent.** En plein soleil, les statuts en petites pastilles et les contours des champs s'effacent : l'agent ne voit plus où saisir ni si la synchronisation est à jour.

**Preuve (version 2.12.0).** Ratios WCAG calculés sur res/values/colors.xml (mode clair). Sur surface blanche : success 4,35, warning 4,44, vase 3,64, cyan 4,77, text_muted 3,27 (3,04 sur background), text_secondary 6,20. Texte de ton sur sa teinte (puces et badges, HydriaVisuals.kt:326-352 et 488-505) : success 3,42–3,66, warning 3,47–3,75, cyan 3,70–3,97, error 4,11–4,43, à 11–12,5 sp. Bouton plein : blanc sur cyan 4,77 (primaryButton, HydriaVisuals.kt:274-287) ; blanc sur vase 3,64. Bordures : outline #D2E0E4 sur blanc = 1,35:1 (champs styleInput:453, cartes card:247) ; surface contre fond = 1,08. colors.xml:22 affirme « contraste ≥ 4,5:1 sur hydria_surface », ce qui est faux pour success, warning et vase. En clair, MainActivity.kt:4476 colore les week-ends en text_muted. Mode sombre : conforme (voir points forts).

**Recommandation.** Dans values/colors.xml : hydria_text_secondary → #3A525C (8,3:1) ; hydria_text_muted → #52707C (5,3:1) et réservé au décoratif ; ajouter des jetons de texte hydria_cyan_text #0A5F6E (7,3), hydria_success_text #0F6B3F (6,6), hydria_warning_text #7A4A00 (7,5), hydria_vase_text #8F4600 (6,9), hydria_error_text #A32E22 (7,1), ainsi qu'un hydria_field_outline #7F9AA4 (3,0:1) pour les champs. Dans HydriaVisuals.kt : ajouter toneTextColor(tone) utilisé par badge, syncChip, taskRow et chip ; primaryButton prend cyanStrong en clair (blanc dessus : 7,3:1) et le texte « ink » sur vase ; styleInput utilise le nouvel outline. Corriger le commentaire de colors.xml:22. Aucun écran à modifier.

### TRANSVERSE-04 — Échelle typographique inutilisée : ≈ 28 tailles, 63 % des textes ≤ 13 sp, soit ≈ 11 sp à l'échelle 0,85 de l'appareil

- **Sévérité** : Majeur
- **Écran** : Tous les écrans (onglets, métadonnées, sous-titres de tâche, badges, libellés d'axe)
- **Catégorie** : esthetique · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Chaque écran choisit ses tailles au pas de 0,5 sp ; le jeton « body 13 / meta 12 » existe mais personne ne l'appelle. Le corps de texte dominant est déjà petit et devient très petit dès que l'utilisateur réduit la taille de police, comme sur l'appareil de référence. Les écrans 2.3 (Recherche, Navigation) et la calculatrice n'ont jamais été alignés.

**Impact pour l'agent.** Lecture pénible au soleil et à une main : sous-titres, dates, états et libellés d'onglets passent sous 10 sp effectifs, la taille où les agents plissent les yeux ou abandonnent la ligne.

**Preuve (version 2.12.0).** dimens.xml:31-39 définit 8 tailles (hydria_text_display … numeral_row), mais R.dimen n'est référencé qu'une fois dans toute l'appli (HydriaVisuals.kt:250, hydria_radius_card). Grep sur textSize = N et sur les appels text(…, Nf, bool, couleur) : ≈ 350 sites et ≈ 28 valeurs distinctes (9,5 ; 10 ; 10,5 ; 11 ; 11,5 ; 12 ; 12,5 ; 13 ; 13,5 ; 14 ; 14,5 ; 15 ; 15,5 ; 16 ; 17 ; 18 ; 19 ; 20 ; 21 ; 22 ; 24 ; 25 ; 26 ; 28 ; 29 ; 30 ; 34 ; 44). Répartition : ≈ 39 % des sites ≤ 12 sp, ≈ 63 % ≤ 13 sp ; les plus fréquents sont 13 sp (≈ 69) et 12 sp (≈ 67). Exemples : libellés des onglets 10,5 sp (MainActivity.kt:882, HydriaWindow.kt:170), badge 9,5 sp (MainActivity.kt:863) et « JOURS » 9,5 sp (MainActivity.kt:4190), surtitre 11 sp (HydriaVisuals.kt:477), sous-titre de tâche 11,5 sp (:398), puces 12 sp. À fontScale 0,85 : 12 sp → 10,2 sp ; 10,5 sp → 8,9 sp ; 9,5 sp → 8,1 sp. Le handoff lui-même fixe la métadonnée à 11,5–12 sp (README.md:375).

**Recommandation.** Définir 6 rôles et un seul point d'entrée : HydriaType.style(role) qui applique taille, graisse et couleur. Plancher proposé : méta 12 sp, corps 14 sp, titre de ligne 15 sp, titre de carte 17 sp, chiffre 24 sp, hero 44 sp, pas de taille < 11 sp. Rendre les rôles lisibles par dimens.xml (déjà déclarés) et remplacer les ≈ 350 sites par ordre de trafic : HydriaVisuals, onglets, Terrain, Relevés, Réparations, Planning. Option : plancher en pixels (taille effective ≥ 11 sp quel que soit fontScale) pour les rôles méta, par TypedValue.applyDimension ou textSize en COMPLEX_UNIT_PX. Ajouter une revue Lint « pas de textSize littéral ».

### TRANSVERSE-05 — Cibles tactiles de 30–40 dp sur des actions quotidiennes, contraires aux 48 dp du système de design

- **Sévérité** : Majeur
- **Écran** : Terrain (mode Tout/Par ouvrage/Autour), en-tête global, Recherche, Pointage, listes de tâches
- **Catégorie** : ergonomie · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Les actions principales (onglet, bouton, champ) respectent 56–74 dp, mais les contrôles secondaires utilisés à chaque ouverture (bascule du périmètre Terrain, pastille de synchro, menu de session) sont à 30–38 dp, avec peu d'espace entre cibles voisines.

**Impact pour l'agent.** Appui raté ou mauvaise puce touchée au pouce, avec gants ou sous le soleil ; les agents doivent viser. L'écran Terrain est l'accueil.

**Preuve (version 2.12.0).** Puces de mode Terrain : MainActivity.kt:1226-1231, hauteur forcée à dp(30) avec 6 dp d'écart entre puces. HydriaUi.chip : minHeight 34 dp (HydriaVisuals.kt:318), réutilisée par les onglets de la calculatrice, les onglets de Recherche (SearchActivity.kt:142) et les périodes (MainActivity.kt:1794). Pastille de synchronisation : 38 dp (MainActivity.kt:615-616 et HydriaVisuals.kt:339). Bouton ⋮ : 38 × 38 dp (MainActivity.kt:725-729). Effacer la recherche : 36 × 36 dp (SearchActivity.kt:187). « Ouvrir » des listes de tâches : 40 dp (MainActivity.kt:2351-2355). Retour du Pointage : 48 × 44 dp (PointageActivity.kt:163). Calculatrice : 40 dp (AdvancedCalculatorActivity.kt:482-486). dimens.xml:5 déclare hydria_target_min = 48 dp mais aucun code ne le lit.

**Recommandation.** Conserver la hauteur visuelle mais agrandir la zone tactile : dans HydriaUi.chip, minHeight 48 dp avec un InsetDrawable de 7 dp haut et bas autour du fond arrondi. Pour la pastille de synchro et le ⋮, passer à un conteneur 48 dp (padding transparent) ou utiliser TouchDelegate. Supprimer le dp(30) de MainActivity.kt:1227-1230. Remplacer les littéraux par R.dimen.hydria_target_min. Ajouter marginStart ≥ 8 dp entre puces.

### TRANSVERSE-06 — Texte atténué et états désactivés par transparence : des informations utiles tombent à 1,9–3,7:1

- **Sévérité** : Mineur
- **Écran** : Pointage, saisie de relevé, Planning, listes (hint de recherche, placeholder « 0 », jours)
- **Catégorie** : accessibilite · **Effort** : S
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Le jeton « atténué » est utilisé pour porter de l'information (jour du week-end, délai, hint, raison d'un blocage) alors qu'il est conçu pour du décoratif. La désactivation par transparence divise le contraste du libellé, qui est pourtant le seul endroit où le motif du blocage est écrit.

**Impact pour l'agent.** Un agent ne comprend pas pourquoi le bouton « Pointer » est grisé, ne voit pas le week-end sur le bandeau de dates, ni ce qui reste à saisir dans les lignes déjà traitées.

**Preuve (version 2.12.0).** text_muted : 3,27:1 sur surface en clair (colors.xml:20), 3,74:1 en sombre (values-night/colors.xml:19), et seulement 3,07–3,08:1 sur surface_raised dans les deux modes, soit le placeholder « 0 » du champ d'index (HydriaVisuals.kt:467). Même couleur pour le hint de recherche (HydriaVisuals.kt:456), le chevron des lignes, les abréviations de jours (MainActivity.kt:4472), les week-ends du bandeau de dates (:4476) et « JOURS » (:4190). Désactivation par alpha : PointageActivity.kt:522 met le bouton principal à 0,45 alors que son libellé donne la raison (« Trop loin pour pointer (xx m) », « Pointage possible à 15h ») : 1,91:1 en clair et 3,16:1 en sombre. Autres alpha : MainActivity.kt:3873 (points déjà relevés à 0,55), 4160 (réparations terminées à 0,75 → texte secondaire 3,56:1 et « ✓ » success 2,92:1 en clair), HydriaActivityCascade.kt:66 et 94.

**Recommandation.** 1) Dans HydriaUi : disabledButton(button) qui garde le texte à textSecondary opaque et ne change que le fond (surfaceRaised + contour), sans alpha ; l'utiliser pour pointButton (PointageActivity.kt:522) et les lignes terminées (MainActivity.kt:3873, 4160). 2) Relever text_muted à ≥ 4,5:1 sur surface_raised (sombre : #85A3AE = 6,2:1 ; clair : voir TRANSVERSE-03) et réserver le jeton aux chevrons. 3) Week-ends et jours : textSecondary + marqueur (point ou libellé) plutôt que simple atténuation.

### TRANSVERSE-07 — Cinq formats de date coexistent, dont des dates ISO brutes ; la date du jour ignore le fuseau Madagascar

- **Sévérité** : Mineur
- **Écran** : Planning, Pointage, Relevés, Réparations, Volume, fiches Recherche, facture A4
- **Catégorie** : rendu donnees · **Effort** : S
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Une même date apparaît sous des formes différentes d'un écran à l'autre, et les horodatages techniques ISO fuient dans l'interface et sur le document client. Les champs de date des formulaires se préremplissent avec l'heure de l'appareil et non celle de Madagascar.

**Impact pour l'agent.** Lecture hésitante des dates (« 2026-09-29 » contre « 29/09/2026 ») et, sur un téléphone mal réglé, une date de planning ou de campagne décalée d'un jour la nuit.

**Preuve (version 2.12.0).** « 12 octobre 2026 » (shared/planning/PlanningAgenda.kt:38-42) ; « lundi 12 octobre » (PointageActivity.kt:246) ; « 12/10/2026 » (displayIsoDate, MainActivity.kt:5042-5045) ; ISO brut : « Index précédent : 130.67 · 2026-09-29 » (MainActivity.kt:1974), « Dernière actualisation : $generated » avec generated_at ISO complet (MainActivity.kt:5375), « Dernière mise à jour : ${updated_at} » (SearchDetailActivity.kt:214), « données du ${generated_at.take(10)} » (VolumeActivity.kt:240), date des interventions (RecentInterventionsActivity.kt:169), lignes DiameX (VolumeActivity.kt:306), « Généré le : … » (VolumeRecapPrinter.kt:82), « FACTURE D'EAU · 2026-09 » (VolumePrinter.kt:56). Fuseau : MainActivity.kt:2708 et 4664 préremplissent la date avec SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date()) sans fuseau, alors que PointageRules.kt:22 et VolumeActivity.kt:28 utilisent Indian/Antananarivo. generated_at est du UTC (backend views_mobile_volume.py:205) ; .take(10) peut donner la veille entre 00:00 et 03:00 local.

**Recommandation.** Ajouter dans HydriaFormat : dateCourte(iso) → « 29/09/2026 », dateLongue(iso) → « 29 septembre 2026 » (tables FR et MG), heure(iso) → « 14:44 », avec conversion explicite vers Indian/Antananarivo. Remplacer les 9 sites cités, y compris les impressions. Centraliser « aujourd'hui » dans une fonction PointageRules.ZONE-aware (todayIso()) et supprimer SimpleDateFormat/Date(). Garder l'ISO uniquement dans les payloads.

### TRANSVERSE-08 — États portés par la couleur ou le signe seul : pastille « à jour » rouge hors ligne, « -224 JOURS » sans libellé

- **Sévérité** : Mineur
- **Écran** : En-tête de Pointage, carte de réparation, légende de carte
- **Catégorie** : coherence · **Effort** : S
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Deux implémentations de la pastille de synchronisation coexistent et l'une affiche un message contradictoire. Le délai des réparations mêle signe, couleur et mot unique : il faut deviner que le négatif signifie « en retard ».

**Impact pour l'agent.** Un agent hors réseau lit « à jour » et croit que ses données sont parties ; un « -224 JOURS » rouge ne dit pas s'il reste ou s'il manque du temps.

**Preuve (version 2.12.0).** HydriaVisuals.kt:326-351 (syncChip, utilisé par PointageActivity.kt:489) : tone ERROR dès que !online, mais le texte reste `if (pending > 0) pending.toString() else "à jour"` → « à jour » en rouge quand on est hors ligne sans file. MainActivity.updateStatus (:5462-5495) a dupliqué la logique et ajouté « hors ligne » et « … », donc les deux en-têtes divergent. MainActivity.kt:4168-4192 : retard affiché « -224 » en rouge, marge « 12 » en text_muted, sous le même mot « JOURS » (9,5 sp, :4188-4190). NavigationTerrainActivity.kt:1045-1050 : catégories de carte par pastille de couleur seule sur la légende.

**Recommandation.** Faire de HydriaUi.syncChip la seule implémentation (paramètres pending, online, syncing, textes via ressources) et l'appeler depuis MainActivity.updateStatus. Pour le délai : libellés « 224 j de retard » (rouge) et « dans 12 j » (neutre), sans signe négatif. Légende des catégories : ajouter la forme ou l'initiale (V, PE, EQ, RP) à côté de la couleur, comme le fait déjà SearchActivity.kt:754.

### TRANSVERSE-09 — Pluriels bricolés « (s) » sur ≈ 68 libellés, lus tels quels par TalkBack

- **Sévérité** : Mineur
- **Écran** : Terrain, Relevés, Réparations, Planning, Volume, Recherche, descriptions d'accessibilité
- **Catégorie** : rendu donnees · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Les pluriels sont inventés au cas par cas : « (s) » dans la majorité, vrais pluriels ailleurs. Cela ne se traduit pas vers le malgache (pas de marque de pluriel sur le nom) et TalkBack prononce « parenthèse s ».

**Impact pour l'agent.** Un compteur comme « 1 détail(s) » ou « 337 réparation(s) » paraît négligé, et les agents malvoyants entendent la parenthèse.

**Preuve (version 2.12.0).** Environ 68 occurrences hors calculatrice (MainActivity 43, VillageDetailRenderer 5, CommuneDetailRenderer 4, VolumeActivity 3, HydriaVisuals 3…). Exemples visibles : « 337 réparation(s) à faire · 122 ouvrage(s) » (MainActivity.kt:4090), « 94 planning(s) affiché(s) sur 94 » (:4365), « 53 point(s) restant(s) » (:2921), « 1 détail(s) » (:4225), « nom(s) · photo(s) PE · débit(s) » (:1344-1347). Descriptions d'accessibilité : HydriaVisuals.kt:348-349 et 414 (« $count restant(s) »). Ailleurs, des pluriels corrects à la main : « tâche/tâches restante(s) » (MainActivity.kt:1181), « an/ans » (:1359). Une seule ressource plurals dans le projet (calculator_saved_lines).

**Recommandation.** Ajouter HydriaFormat.plural(n, un, autres) (côté partagé) ou des plurals Android par libellé (réparation, ouvrage, planning, point, facture, photo, action). Traiter d'abord les 25 sites des écrans d'accueil et de liste : MainActivity.kt:2233, 2921, 4000-4002, 4090, 4225, 4365, HydriaVisuals.kt:348-349 et 414. Ajouter le nombre groupé via count(n) (TRANSVERSE-02).

### TRANSVERSE-10 — Système de design contourné : jetons de dimension non utilisés, ≈ 830 dp() littéraux, couleurs de carte du mode sombre figées

- **Sévérité** : Mineur
- **Écran** : Navigation/Carte, Recherche, Volume, Calculatrice, cartes en général
- **Catégorie** : coherence · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Les écrans refondus (accueil, relevé) respectent les jetons de couleur mais pas ceux de taille, de cible et d'espacement ; Recherche, Navigation et Calculatrice décrochent davantage. Des ressources de couleur existent mais ne sont pas utilisées.

**Impact pour l'agent.** Rythme et densité varient d'un écran à l'autre : mêmes cartes à 14 ou 16 dp, mêmes champs à 52 ou 56 dp. Une future retouche (dimensions, mode clair) oblige à changer des centaines de lignes.

**Preuve (version 2.12.0).** Dimens non lus : hydria_target_*, hydria_text_*, hydria_gap*, hydria_gutter, hydria_card_padding, hydria_accent_bar (un seul R.dimen utilisé, HydriaVisuals.kt:250). Appels dp(…)/dpi(…) : MainActivity 244, SearchActivity 126, NavigationTerrainActivity 90, AdvancedCalculatorActivity 87, PointageActivity 71… soit ≈ 830. Rayons littéraux : 10, 12, 13, 14, 16, 17, 18, 19, 20 dp dans les appels rounded(). HydriaUi.card utilise 16 dp (dimen) mais accentedCard 14 dp en dur (HydriaVisuals.kt:263). Quatre copies locales de text(value, size, bold, color) (MainActivity.kt:5533, CommuneDetailRenderer.kt:239, SearchDetailActivity.kt:578, VillageDetailRenderer.kt:183). hydria_map_* (colors.xml:41-44) n'est référencé nulle part ; NavigationTerrainActivity.kt:1045-1050 (catColor) et SearchActivity.kt:754 recodent les valeurs du mode sombre (#9B8AFB, #55D9E7, #F29A38, #58D594), soit 1,68–2,83:1 sur blanc en mode clair pour les pastilles de légende.

**Recommandation.** Remplacer les littéraux par les ressources existantes, en commençant par HydriaVisuals.kt (rayons, accentedCard) puis les helpers locaux text() déplacés vers HydriaType.style(role). Câbler hydria_map_* via une fonction HydriaColors.mapCategory(category). Ajouter une règle Lint « pas de dp littéral ≥ 28 hors HydriaVisuals ». Reprendre les écrans Recherche et Navigation dans cet ordre.

### TRANSVERSE-11 — Structure TalkBack absente : aucun titre déclaré, aucune région vivante, descriptions qui masquent le contenu

- **Sévérité** : Mineur
- **Écran** : Tous les écrans, lignes de tâche et retours d'état
- **Catégorie** : accessibilite · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Les boutons-icônes sont bien décrits, mais le texte de titre n'est pas marqué comme titre, les retours d'action sont éphémères et les lignes composites cachent leur sous-titre à TalkBack.

**Impact pour l'agent.** Un utilisateur de TalkBack ne peut pas sauter de section en section et rate les confirmations d'enregistrement ; la ligne de tâche ne dit pas pourquoi elle est en retard.

**Preuve (version 2.12.0).** Grep : isAccessibilityHeading / setAccessibilityHeading : 0 occurrence ; accessibilityLiveRegion / announceForAccessibility : 0 ; ViewCompat : 0. Les confirmations et erreurs passent par Toast (MainActivity.kt:5575 et ≥ 79 appels toast("…")). HydriaVisuals.kt:414 : la ligne de tâche remplace tout son contenu par `"$title, $count restant(s)"`, donc le sous-titre (« Échéance de mesure dépassée ») n'est jamais annoncé et le « (s) » est lu. 6 SwitchCompat construits sans libellé propre (MainActivity.kt:1200, 2933, 2998, 3055, 4059, 4070). Points d'amélioration relevés par ailleurs : ≈ 38 caractères emoji ou symboles servent d'icônes (« 📷 », « ⭐ », « ✓ », « › ») ; « › » est correctement masqué (HydriaVisuals.kt:408).

**Recommandation.** Ajouter HydriaUi.sectionTitle(text) qui appelle ViewCompat.setAccessibilityHeading(view, true) et l'utiliser pour les titres de page et d'écran ; construire la description de taskRow avec le sous-titre (« $title, $subtitle, $count »). Passer les confirmations à une Snackbar ou ajouter announceForAccessibility dans toast(). Donner un contentDescription ou un libellé associé aux 6 interrupteurs et remplacer « 📷 » et « ⭐ » par des drawables avec description.

### TRANSVERSE-12 — Polices Archivo et Roboto Mono téléchargées au premier lancement : repli définitif en sans-serif et mono large

- **Sévérité** : Mineur
- **Écran** : Tout le premier lancement hors ligne, appareils sans Google Play Services
- **Catégorie** : performance percue · **Effort** : S
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Dans le cas où l'agent installe l'APK puis ouvre l'appli sans réseau, toute la session utilise les polices de repli, avec des chiffres plus larges qui débordent des colonnes (cf. compteurs déjà signalés). La promesse « arrive plus tard » n'est pas implémentée.

**Impact pour l'agent.** Mise en page différente selon que la police est arrivée ou non, et risque accru de chiffres coupés sur les téléphones d'entrée de gamme.

**Preuve (version 2.12.0).** res/font/archivo.xml et roboto_mono.xml : fournisseur com.google.android.gms.fonts, aucun .ttf dans res/. Le commentaire d'archivo.xml indique que ResourcesCompat.getFont peut renvoyer null au premier lancement et que HydriaType « retombe sur sans-serif jusqu'à l'arrivée d'Archivo » ; or HydriaType.bind (HydriaVisuals.kt:116-119) lit la police une seule fois par Activity (runCatching…getOrNull) sans callback de téléchargement. Repli numérique : Typeface.MONOSPACE (HydriaVisuals.kt:130), plus large que Roboto Mono. L'appli est offline-first et distribuée par APK (Hydria-Terrain-*.apk).

**Recommandation.** Embarquer les deux polices dans res/font (Archivo et Roboto Mono 400/600/700 ou leurs variantes variables, ≈ 400 Ko) et supprimer fontProviderQuery ; garder HydriaType.bind comme aujourd'hui, sans runCatching. Ajouter un test d'instrumentation qui vérifie que HydriaType.numeral() n'est pas MONOSPACE.


## Écran Terrain : complétude et collecte

_Audit initial sur la version 2.11.0._

**Synthèse du domaine.** L'écran Terrain reprend bien la structure de la refonte « Lisible au soleil » : carte de complétude, deux actions, puces de filtre, lignes `taskRow` à chiffre en monospace et filet de couleur. Le travail hors ligne est sérieux : chaque action est mise en file, l'écran se met à jour tout de suite et la synchro part seule.

En revanche, la chaîne de collecte présente deux risques critiques pour les données :
1. **GPS sans contrôle.** Le GPS d'un point est la première position reçue, peut-être une position réseau, sans seuil de précision, sans confirmation et sans délai maximal sous Android 10 ou moins.
2. **Conflits artificiels en série.** Les actions lancées depuis le Terrain envoient la version `updated_at` de l'ancien snapshot au lieu de `TerrainEditRules.baseVersion`. Deux actions sur le même point (GPS puis photo, ou photo puis nom) produisent donc un « conflit » 409 au moment de la synchro.

Plusieurs composants ont été dimensionnés pour la maquette (47 tâches, 12 ouvrages) et ne tiennent pas avec les données réelles (3 601 tâches, 401 ouvrages) :
- la colonne de chiffres de 44 dp coupe « 1282 » en deux lignes ;
- « Commencer ma tournée » enchaîne 3 434 tâches triées par catégorie puis par ordre alphabétique d'ouvrage ;
- la liste de photos construit 1 627 cartes d'un coup ;
- la vue « Par ouvrage » est une impasse.

La série de saisie impose un dialogue « Continuer » avant chaque élément. Elle n'a pas de bouton « Passer » et se fige après une annulation ou un échec. Le geste Retour du système ferme l'application, car aucun `OnBackPressedCallback` n'existe. Le pourcentage de complétude ne bouge pas hors ligne, alors que le nombre de tâches restantes baisse.

Les formulaires de débit et de compteur de tête n'ont pas de libellé visible, puisque l'indice disparaît dès la saisie. La date se tape au format AAAA-MM-JJ et les erreurs arrivent dans un toast générique.

Causes des observations visuelles :
- **Obs. 1 (« 128 / 2 »)** : colonne de largeur fixe 44 dp, alors qu'un chiffre Roboto Mono 24 sp fait environ 12 dp, soit environ 47 dp pour 4 chiffres même à l'échelle 0,85.
- **Obs. 2 (coins colorés)** : `cornerRadii` carrés à droite sur la couche filet.
- **Obs. 3 (« Toul », « Par ouvrag »)** : faux gras probable (déduction), car seule la graisse Archivo 400 est demandée au fournisseur Google Fonts. Les puces font aussi 30 dp de haut.
- **Obs. 12 (libellés gris)** : à nuancer. Le texte secondaire #9FBAC4 sur #0E2029 donne environ 8:1, ce qui est conforme. Le vrai problème est la taille (12 sp × 0,85 ≈ 10 sp) et le gris atténué des indices (#5D7C88), à environ 3,7:1.

**À préserver :**

- Hors ligne réel : chaque action Terrain passe par `store.enqueue` et une mise à jour locale immédiate (`TerrainRepository.applyLocal*`), puis la synchro se relance si le réseau est disponible ; les toasts annoncent « x action(s) en attente ».
- Contrôle avant enregistrement pour les mesures : les boîtes « Résultat immédiat » (débit, tendance, variation, moyenne) et « Comparaison immédiate » (écart tête/aval, classement, recommandation) proposent « Corriger » avant d'écrire quoi que ce soit (MainActivity.kt:1297-1312, 1372-1387).
- Le bouton positif est surchargé dans `setOnShowListener`, donc la boîte reste ouverte en cas d'erreur ; la virgule décimale est acceptée (`replace(',', '.')`) ; `workPicker.error` est posé directement sur le champ en faute.
- `HydriaUi.taskRow` sert de composant unique : chiffre monospace aligné à droite, urgence portée par le filet et non par le fond, ligne terminée non cliquable, `contentDescription` « titre, n restant(s) », chevron caché aux lecteurs d'écran.
- Recherche de liste insensible aux accents (`Normalizer` NFD), recherche multi-mots, compteur « x résultat(s) sur N » ; les éléments masqués sont décochés pour éviter un traitement invisible.
- Règles métier dans le module partagé (TerrainTaskRules, TerrainMeasurementEngine, TerrainEditRules), donc testables et communes au bureau ; la variante tablette en 2 volets avec tableau et sélection multiple suit la maquette 4a.
- Photos compressées (1280 px, JPEG 80, moins de 5 Mo) ; le chemin de la photo en cours est sauvegardé dans `onSaveInstanceState`, ce qui protège contre la destruction du processus par l'appareil photo.
- Palette jour/nuit tirée des ressources ; le texte secondaire en mode sombre (#9FBAC4 sur #0E2029, environ 8:1) est conforme, et le texte sur accent plein (#07151D sur cyan ou vase) est très contrasté.
- Bascule de périmètre élargi faite par copie superficielle (correctif de blocage ANR documenté dans shared TerrainRules.perimeter).

### TERRAIN-01 — Le GPS d'un point est la première position reçue, sans seuil de précision, sans confirmation et sans délai maximal

- **Sévérité** : Majeur (initialement Critique)
- **Écran** : Terrain › Coordonnées à compléter / Commencer ma tournée › capture GPS
- **Catégorie** : feedback etats · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** La toute première position fournie est écrite comme coordonnées définitives du point. Ce peut être une position réseau cellulaire (souvent ±500 m à 2 km en zone rurale si le GPS est coupé) ou un premier fix GPS à ±50 m. L'agent ne voit pas la précision avant l'enregistrement, n'a ni indicateur d'attente (un toast de 3,5 s, puis plus rien) ni bouton Annuler. Sous Android 8 à 10 (minSdk 26), `requestSingleUpdate` peut ne jamais répondre sous un toit en tôle : la série reste bloquée sans retour. Rien ne vérifie que l'agent est bien au point : enchaîner la tournée depuis le bureau pose la position du bureau sur chaque point.

**Impact pour l'agent.** Coordonnées fausses durablement pour 1 282 points sans GPS ; elles alimentent ensuite la carte, les itinéraires, les tournées et le filtre « Autour ». L'erreur est invisible après coup et coûteuse à retrouver.

**Preuve (version 2.11.0).** MainActivity.kt:1942-1945 `manager.isProviderEnabled(LocationManager.GPS_PROVIDER) -> GPS_PROVIDER … NETWORK_PROVIDER -> NETWORK_PROVIDER` ; 1952 `toast("Recherche de la position GPS en cours…")` ; 1965-1972 `store.enqueue("terrain_data", … .put("latitude", location.latitude) … .put("accuracy", …))` sans test sur `location.accuracy` ; 1978 la précision n'apparaît qu'après coup dans le toast « GPS enregistré · … précision ±X m » ; 2018 `requestSingleUpdate(provider, …)` (API 26-29) sans délai maximal ; 1954-1955 échec → simple toast, la série s'arrête. Maquette 4a : « Relever le GPS ici » / « Trop loin » non implémentés.

**Vérification sur 2.12.0.** MainActivity.kt:2576-2659 acquirePointLocation : 2579-2580 GPS puis repli NETWORK_PROVIDER ; 2601-2615 `.put("latitude", location.latitude) … .put("accuracy", location.accuracy.toDouble())` sans test de précision, toast « GPS enregistré · … précision ±X m » après coup ; 2652-2658 `getCurrentLocation(provider, null, …)` (API 30+) / `requestSingleUpdate(provider, …)` sans délai ni annulation (API 26-29). Même schéma dans acquireEquipmentGps (l. 305-349). — Défaut client inchangé : première position écrite telle quelle, aucun seuil de précision (aucune constante équivalente dans TerrainEditRules ; seul le calculateur a GPS_TARGET_ACCURACY_M), pas de feuille de capture, pas de bouton Annuler/Réessayer, NETWORK_PROVIDER toujours accepté pour les coordonnées d'un point. Un `getCurrentLocation` API 30+ a un délai système (~30 s) mais pas `requestSingleUpdate` (API 26-29). Atténuation apparue côté backend : views_preparation_tournee.py:1446/1508 appellent terrain_points.controle_distance_gps (terrain_points.py:80-102, 2 km point d'eau / 3 km équipement du village desservi, refus 422 `gps_trop_loin`, sauf rôles autorisés ou village sans coordonnées). Cela borne le scénario « position du bureau sur chaque point » mais pas l'imprécision (fix réseau ±500 m–2 km ou premier fix ±50 m passent). Aucun traitement de ce code 422 côté app. Sévérité abaissée de critique à majeur à cause de ce garde-fou serveur ; reste à faire : seuil de précision + feuille de capture + délai max.

**Recommandation.** Pour la catégorie "gps", remplacer `acquirePointLocation` par une feuille de capture (dialogue programmatique) :
- écouter `requestLocationUpdates(GPS_PROVIDER, 1000, 0f)` pendant 60 s au plus, avec un `Handler` comme délai maximal pour l'API inférieure à 30 ;
- afficher la précision en gros (`HydriaType.numeral` 34 sp, « ± 23 m ») en vert si ≤ 10 m, orange si ≤ 25 m, rouge au-delà, ainsi que le village et l'ouvrage du point ;
- n'activer « Enregistrer cette position » qu'en dessous d'un seuil (15 m, constante partagée dans TerrainEditRules) ;
- proposer aussi « Réessayer », « Passer ce point » et « Arrêter la série » ;
- refuser `NETWORK_PROVIDER` pour les coordonnées d'un point (le garder pour « Autour »).

### TERRAIN-02 — Deux actions sur le même point dans une série créent un « conflit » artificiel à la synchro

- **Sévérité** : Majeur (initialement Critique)
- **Écran** : Terrain › série (abonné, GPS, photo)
- **Catégorie** : workflow · **Effort** : S · quick win
- **Statut** : Partiellement corrigé en 2.12.0

**Constat.** Hors ligne, cas normal en brousse, GPS, nom et photo d'un même point partent avec la même version de base. Le serveur accepte la première action, modifie `updatedat`, puis répond 409 aux suivantes. En ligne aussi, la file de série tient des objets dont `updated_at` n'est jamais rafraîchi. Les actions refusées remontent en « Conflit » dans le centre de synchro avec seulement « Comparer » : « Corriger » n'existe que pour les relevés (4567-4578).

**Impact pour l'agent.** Photos et noms collectés sur place restent bloqués en conflit. L'agent ne comprend pas pourquoi son travail est refusé ; s'il abandonne, le travail est perdu.

**Preuve (version 2.11.0).** MainActivity.kt:1854 `.put("base_updated_at", item.optString("updated_at"))` (abonné), 1972 (GPS en série) et 193 (photo en série), alors que les chemins Relevés utilisent `TerrainEditRules.baseVersion(store.pending(), "point_eau", pointId, …)` (199-201, 1986-1988). TerrainEditRules.kt:22-29 : « renvoyer l'ancienne version ferait refuser la seconde opération en « conflit ». On n'envoie alors pas de version. » Serveur views_preparation_tournee.py:1374 `if point.updatedat > base_updated_at and not force_sync:` → 409. La série garde les JSONObject de l'ancien snapshot (MainActivity.kt:1801) même après `store.snapshot = tour.body` (894).

**Vérification sur 2.12.0.** MainActivity.kt:213-216 `terrainBaseVersion(item, equipment)` = TerrainEditRules.baseVersion(store.pending(), …) utilisé en 237 (photo en série), 2489 (abonné), 2608 (GPS en série), 328 (GPS équipement) ; TerrainRepository.kt:129-154 `applyServerVersion` reporte `server_updated_at` dans le snapshot après envoi réussi (appelé MainActivity.kt:1036) ; mais MainActivity.kt:155 `terrainBatchQueue` garde les JSONObject de l'ancien snapshot, remplacé par `store.snapshot = tour.body` (≈l. 1088) dans afterQueue. — Corrigé : les trois chemins de série n'envoient plus l'ancienne version quand une opération du même point est déjà en file (cas hors ligne décrit par le constat), et le serveur exempte déjà photo_point du 409 (views_preparation_tournee.py:1411). Reste : en ligne, après la première synchro de la série, le snapshot est remplacé (le hash snapshot_version change) alors que la file de série garde les anciens objets ; applyServerVersion met alors à jour les nouveaux objets, pas ceux de la file. Une 2e opération `update_point` sur le même point (ex. abonné après GPS dans « Commencer ma tournée », ou formulaire abonné enchaîné après une photo) repart avec un `updated_at` périmé et peut être refusée en 409. Le centre de synchro offre désormais « Forcer l'envoi » dans la boîte de comparaison (MainActivity.kt:5431-5441), ce qui permet une sortie ; « Corriger » reste réservé aux relevés (5309-5314). Pas de test partagé du scénario GPS+photo+nom. Sévérité abaissée de critique à majeur (cas hors ligne résolu, résidu conditionnel).

**Recommandation.** Calculer la version comme le font les Relevés, dans les trois chemins Terrain (showSubscriberForm, branche `pendingTerrainCategory == "gps"` d'acquirePointLocation, branche série de pointPhotoLauncher) : `TerrainEditRules.baseVersion(store.pending(), if (equipment) "equipement" else "point_eau", id, item.optString("updated_at"))`. Ajouter un test partagé : « GPS + photo + nom sur le même point hors ligne → seule la 1re opération porte une version ».

### TERRAIN-03 — « Commencer ma tournée » lance 3 434 tâches triées par catégorie puis par ordre alphabétique, sans aperçu

- **Sévérité** : Majeur
- **Écran** : Terrain › Commencer ma tournée
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** La tournée parcourt d'abord tous les GPS manquants des 401 ouvrages par ordre alphabétique, puis toutes les photos de points, puis les équipements. Un même point est donc visité deux ou trois fois à des moments très éloignés (GPS en tâche 12, photo 1 500 tâches plus tard). Le bouton n'affiche aucun aperçu (nombre, ouvrages, distance) et ignore la position de l'agent. Les mesures de débit en retard (90) et jamais faites (77), en rouge en tête d'écran, sont exclues sans le dire.

**Impact pour l'agent.** L'action principale de l'écran est inutilisable sur un vrai périmètre. Les agents l'abandonnent pour les listes par catégorie, et le « 1 / 3434 » décourage.

**Preuve (version 2.11.0).** MainActivity.kt:1051-1054 `text = "Commencer ma tournée" … setOnClickListener { startTerrainBatch(TerrainRules.buildTourTasks(terrain)) }` sans confirmation ; shared TerrainTaskRules.kt:21-22 `listOf("gps", "subscriber", "point_photo", "equipment_photo").forEach { category -> works.forEach { …` ; serveur views_preparation_tournee.py:699 `.order_by('nom_ouvrage')`. Capture 01 : 1282 + 0 + 1627 + 525 = 3 434 tâches, les 167 débits étant exclus. Titre de la boîte : « PE-xxx · 1 / 3434 » (1776). Maquette 4a : « Trier · distance », « Enchaîner les 21 ».

**Vérification sur 2.12.0.** shared/src/commonMain/kotlin/mg/hydria/shared/terrain/TerrainTaskRules.kt:21-33 `listOf("gps","subscriber","point_photo","equipment_photo").forEach { category -> works.forEach …` ; MainActivity.kt:5107-5110 `"Commencer ma tournée" to { … startTerrainBatch(TerrainRules.buildTourTasks(terrainForPerimetre(rawTerrain))) }` sans confirmation ni aperçu ; backend views_preparation_tournee.py:720 `.order_by('nom_ouvrage')`. — L'ordre (catégorie puis ouvrage alphabétique), l'absence d'aperçu/plafond/tri par distance et l'exclusion silencieuse des débits sont inchangés. Changement d'exposition : le gros bouton primaire a disparu de l'écran Terrain ; « Commencer ma tournée » (et « Carte terrain ») ne sont plus que des entrées du menu « Outils et session » (MainActivity.kt:5105-5111), donc moins découvrables ; les listes par catégorie offrent « Tout traiter en série (N) » (l. 2135) mais avec le même défaut d'ordre. Sévérité gardée à majeur mais exposition réduite.

**Recommandation.** Réécrire `buildTourTasks` dans shared :
- regrouper par point (GPS, puis photo, puis nom consécutifs), puis par ouvrage ;
- trier par distance au téléphone si une position est connue, sinon par ouvrage le moins complet.

Avant de lancer, afficher une feuille « Ma tournée » :
- choix : ouvrage le plus proche, un village, un ouvrage ;
- aperçu du type « 23 tâches · 3 ouvrages » ;
- inclusion des débits dus pour ces ouvrages ;
- série plafonnée à un ouvrage ou un village (environ 50 tâches au plus).

### TERRAIN-04 — Série : un dialogue « Continuer / Fermer » à chaque élément, pas de « Passer », et la série se fige

- **Sévérité** : Majeur
- **Écran** : Terrain › traitement en série
- **Catégorie** : ergonomie · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Chaque élément impose de lire une boîte (nom d'ouvrage, type brut, « Action : Photographier ») puis de toucher « Continuer » : environ 1 600 taps de plus pour les seules photos. La boîte ne dit pas où se trouve le point, alors que le village figure dans le snapshot, et n'affiche pas la progression. Sans « Passer », un point introuvable ou fermé oblige à « Fermer », ce qui abandonne la série tout en laissant la file en mémoire : un « x / N » périmé réapparaît plus tard sur une action isolée. Annuler l'appareil photo, refuser une permission ou un GPS indisponible arrête la série sans message ni reprise.

**Impact pour l'agent.** Rythme cassé à chaque point, séries abandonnées, et l'agent ne sait plus où il en est ni quoi faire pour reprendre.

**Preuve (version 2.11.0).** MainActivity.kt:1775-1796 `AlertDialog … .setMessage("${work.optString("nom")}\n${item.optString("type")}\n\nAction : $action") .setPositiveButton("Continuer") … .setNegativeButton("Fermer", null)` ; `terrainBatchQueue` n'est jamais vidée sur « Fermer » (1799-1809) et 1773 réutilise `batchPosition` pour une action isolée ultérieure ; photo annulée (`success == false`, 179) ou position nulle (1954) : `finishTerrainBatchTask` n'est pas appelé. README du handoff l. 262-263 : « enchaîne les prises : appareil photo → point suivant, sans repasser par la liste ».

**Vérification sur 2.12.0.** MainActivity.kt:2393-2425 showTerrainItem : AlertDialog `.setPositiveButton("Continuer") … .setNegativeButton("Fermer", null)`, message `${work nom}\n${item type}\n\nAction : $action`, aucun « Passer » ; 2427-2437 startTerrainBatch ; unique `terrainBatchQueue.clear()` en 2428 (jamais sur « Fermer ») ; 2406 `batchPosition` réutilisé pour une action isolée ; 223-271 onPointPhotoResult / 2590-2591 : photo annulée ou position nulle n'appellent pas finishTerrainBatchTask. — Aucun correctif. Aggravation mineure : les photos passent désormais par un 2e dialogue choosePhotoSource « Prendre une photo / Choisir dans la galerie » (l. 1420-1436) avant la caméra, et une photo suivie d'un nom manquant enchaîne en plus le formulaire abonné (l. 266-271). La file non vidée bloque aussi les rafraîchissements d'écran conditionnés par `terrainBatchQueue.isEmpty()` (l. 275, 335, 2649). Pas de barre de série persistante, pas de bilan « faites/passées ».

**Recommandation.** - Remplacer l'AlertDialog par une barre de série persistante en bas (`terrainTaskPage` accepte déjà une `action`) : « 12 / 48 · PE-042 — Ampasika », avec des boutons 64 dp « Photographier / Relever le GPS / Saisir le nom », « Passer » et « Arrêter ».
- Lancer la caméra directement pour les photos.
- Après une annulation ou un échec, rester sur l'élément avec « Réessayer / Passer ».
- Vider `terrainBatchQueue` sur « Arrêter » et dès qu'on quitte l'écran.
- Terminer par un bilan « 9 faites · 3 passées ».

### TERRAIN-05 — Les compteurs à 4 chiffres passent à la ligne (« 128 / 2 », « 162 / 7 »)

- **Sévérité** : Majeur
- **Écran** : Terrain › lignes À compléter
- **Catégorie** : rendu donnees · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** Un chiffre Roboto Mono mesure environ 0,6 em, soit environ 12 dp à 24 sp avec l'échelle de police 0,85 : 4 chiffres font donc environ 47 dp, plus que 44 dp. À l'échelle 1,0 on atteint environ 58 dp. La colonne a été taillée sur la maquette (6, 21, 14), pas sur 1 282 / 1 627 / 525. Le TextView sans `maxLines` passe à la ligne au lieu de rétrécir.

**Impact pour l'agent.** L'agent lit « 128 » points sans GPS au lieu de 1 282. La ligne grossit et l'alignement des chiffres, qui est tout l'intérêt du monospace, est perdu.

**Preuve (version 2.11.0).** HydriaVisuals.kt:379-386 `text = if (count > 0) count.toString() … textSize = 24f … typeface = HydriaType.numeral(700) … }, LinearLayout.LayoutParams(dpi(context, 44f), LinearLayout.LayoutParams.WRAP_CONTENT))` ; dimens.xml `hydria_numeral_column 44dp` ; dump 13_terrain_scroll.xml `text="1282" bounds="[54,795][128,887]"` (74 px = 44 dp de large, 92 px de haut = 2 lignes). Captures 01 et 13.

**Vérification sur 2.12.0.** HydriaVisuals.kt:372-386 (taskRow) `text = if (count > 0) count.toString() else "✓" … textSize = 24f … typeface = HydriaType.numeral(700) … LinearLayout.LayoutParams(dpi(context, 44f), WRAP_CONTENT)` sans maxLines ni autosize ; res/values/dimens.xml:30 `hydria_numeral_column 44dp`. — Code strictement inchangé. Quatre chiffres en Roboto Mono 24 sp (~14 dp par chiffre) dépassent 44 dp, d'où le retour à la ligne (1282 → « 128 / 2 ») ; le constat reposait sur le dump d'écran de la 2.11.0 et rien ne l'a modifié depuis. Non revérifié à l'exécution.

**Recommandation.** Dans `HydriaUi.taskRow`, au choix :
- `maxLines = 1`, largeur `WRAP_CONTENT` et `minWidth = 44dp` (le titre est déjà en poids 1) ;
- largeur fixe de 56 dp avec `TextViewCompat.setAutoSizeTextTypeUniformWithConfiguration(view, 14, 24, 1, TypedValue.COMPLEX_UNIT_SP)` ;
- format compact au-delà de 999 (« 1,3 k ») via une fonction partagée, en gardant la valeur exacte dans `contentDescription`.

### TERRAIN-06 — Carte de complétude : le % ne bouge pas hors ligne, et les compteurs (des totaux) se lisent comme des restes

- **Sévérité** : Majeur
- **Écran** : Terrain › carte COMPLÉTUDE DE MON PÉRIMÈTRE
- **Catégorie** : rendu donnees · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** Après 50 photos prises hors ligne, l'écran affiche « 3551 tâches restantes » mais toujours « 27 % », et la barre ne bouge pas avant la prochaine synchro réussie : le chiffre principal ne récompense pas le travail fait. Le pourcentage n'est expliqué nulle part : il compte 2 éléments par point, plus le nom attendu, les équipements et les captages, soit 3 601 manques sur environ 4 900 éléments. Les trois compteurs, sans verbe ni séparateur, tout en monospace sous la barre, se lisent « il reste 1725 points ».

**Impact pour l'agent.** Pas de retour de progression en zone sans réseau. Confusion entre totaux et restes, et un chiffre de 27 % que personne ne sait expliquer.

**Preuve (version 2.11.0).** MainActivity.kt:980 `val completion = stats.optInt("completion_score", 100)` ; TerrainRepository.kt:120-123 ne fait que `globalStats.put(statKey, (globalStats.optInt(statKey) - 1)…)`, `completion_score` n'est jamais recalculé (idem 41-42 pour les débits) ; MainActivity.kt:1020-1022 `terrainCounter("${stats.optInt("total_ouvrages")} ouvrages")` entièrement en mono 600 ; le commentaire de 1120 dit « Somme des informations terrain restant à compléter », ce qui est faux (ce sont des totaux). Serveur views_preparation_tournee.py:666-678 : score = (points×2 + noms attendus + équipements + captages − manques) / applicable. Capture 01 : « 27 % · 3601 tâches restantes · 401 ouvrages 1725 points 616 équip. ».

**Vérification sur 2.12.0.** MainActivity.kt:1151 `val completion = stats.optInt("completion_score", 100).coerceIn(0, 100)` ; grep « completion_score/completionScore » : seules des lectures (l. 1151, 1350, 1446, 2383), aucun recalcul ; TerrainRepository.kt:121-124 ne décrémente que les compteurs ; MainActivity.kt:1191-1193 `terrainCounter("${stats.optInt("total_ouvrages")} ouvrages")` etc., terrainCounter (l. 1279-1286) en `numeral(600)` ; commentaire l. 1279 « Somme des informations terrain restant à compléter » toujours faux. — Le % reste figé tant qu'une synchro n'a pas rechargé le snapshot, alors que « N tâches restantes » (remainingTasks) baisse hors ligne ; pas de TerrainTaskRules.completionScore dans shared ; compteurs toujours des totaux, sans verbe, tout en monospace ; aucune explication du pourcentage. Backend inchangé (views_preparation_tournee.py:696, 884).

**Recommandation.** - Ajouter `TerrainTaskRules.completionScore(works)` dans shared, avec la formule du serveur ; toutes les données nécessaires sont déjà dans le snapshot (`subscriber_name_expected`, `debit_source_applicable`).
- Recalculer le score dans `applyLocalTerrainCompletion` / `applyLocalFlowMeasurement`, ou à l'affichage dans `renderTerrain`.
- Reformuler : « sur 401 ouvrages · 1 725 points · 616 équipements », chiffres en `numeral` et libellés en `display` comme dans la maquette 1a.
- Ajouter une ligne d'aide « % des informations attendues complétées » et corriger le commentaire de `terrainCounter`.

### TERRAIN-07 — Formulaires Débit source et Compteur de tête : libellés qui disparaissent, date ISO à taper, erreurs génériques

- **Sévérité** : Majeur
- **Écran** : Terrain › Débit source / Compteur de tête (boîtes de dialogue)
- **Catégorie** : ergonomie · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Les unités (L/s, litres, secondes) et les noms des champs ne vivent que dans l'indice, qui disparaît dès la saisie. La date est la seule de l'écran au format AAAA-MM-JJ, à taper au clavier texte, alors qu'ailleurs on affiche 12/10/2026. Les erreurs arrivent dans un toast générique sans désigner le champ, alors que le sélecteur, lui, utilise `.error` (1273). L'index précédent est brut (« .0 », date ISO). Le nouvel index n'utilise pas `styleNumeralInput`, contrairement au relevé. Clavier ouvert sur 948 dp, les 7 éléments du formulaire débit peuvent passer sous le clavier (déduction).

**Impact pour l'agent.** Saisie de litres dans le champ L/s, dates mal tapées refusées sans explication, allers-retours en plein soleil. Le contraste des indices est insuffisant dehors.

**Preuve (version 2.11.0).** MainActivity.kt:4802-4806 `field(hintValue) … hint = hintValue` : l'indice est le seul libellé ; 1225 et 1333 `field("Date (AAAA-MM-JJ)").apply { setText(LocalDate.now().toString()) }`, d'où « 2026-10-12 » affiché sans libellé ; 1276 `LocalDate.parse(...)` strict, date future acceptée ; 1285 `toast("Renseignez une date et un débit, ou un volume…")` et 1365 `toast("Date ou index invalide…")` ; 1341 `"Index précédent : ${previous.optDouble("nouvel_index")} · ${previous.optString("date")}"`, soit « 1234.0 · 2026-09-01 » ; 1245-1250 champs désactivés à `alpha 0.45` mais visibles ; 1299/1374 bouton « Enregistrer offline » puis toast « …hors ligne » même en ligne ; formulaires `vertical()` hors ScrollView (1221, 1330) ; indice `textMuted` #5D7C88 sur #0E2029 (values-night) ≈ 3,7:1.

**Vérification sur 2.12.0.** MainActivity.kt:1553-1557 `field("Date (AAAA-MM-JJ)").apply { setText(LocalDate.now().toString()) }`, `field("Débit direct (L/s)")`, `field("Volume mesuré (litres)")`, `field("Temps (secondes)")` (indice seul, field() = hint, l. 5544-5548) ; 1604 `LocalDate.parse(...)` strict ; 1613 et 1998 toasts génériques ; 1627 « Enregistrer offline » / 1637 « enregistrée hors ligne » ; 1974 `"Index précédent : ${previous.optDouble("nouvel_index")} · ${previous.optString("date")}"` ; 1967 nouvel index sans styleNumeralInput ; 1549 et 1963 `vertical(padding = 16)` passé à setView sans scroll ; values-night/colors.xml:19 hydria_text_muted #5D7C88. — Seule évolution : un RadioGroup « Débit direct / Volume + temps » avec la phrase « Choisissez une seule méthode de mesure » (l. 1558-1591) clarifie le choix, mais les champs inactifs restent visibles à alpha 0,45 au lieu d'être masqués, et le formulaire est plus long sans ScrollView. Libellés-indices, date ISO tapée, erreurs sans champ ciblé, index précédent brut (« .0 », date ISO), toast « hors ligne » même en ligne et contraste des indices en sombre sont inchangés.

**Recommandation.** - Créer un helper `labeledField(label, unit)` : `label()` (MainActivity.kt:4801) au-dessus, suffixe d'unité à droite.
- Remplacer la date tapée par un `DatePickerDialog` affichant « 12/10/2026 », avec maxDate = aujourd'hui.
- Afficher les erreurs sur le champ (`field.error`) avec `HydriaFeedback.shake`.
- Masquer (`GONE`) les champs de la méthode non choisie.
- Formater l'index précédent avec `formatDecimal(…, 2)` et une date dd/MM/yyyy ; `styleNumeralInput` pour le nouvel index.
- Envelopper le formulaire dans `scroll()`.
- Bouton « Enregistrer » et toast adapté à `isOnline()`.
- Remonter `hydria_text_muted` en sombre à 4,5:1 au moins (par exemple #7D9AA6).

### TERRAIN-08 — Compteur de tête : remplacement impossible et analyse trompeuse dans les cas limites

- **Sévérité** : Majeur
- **Écran** : Terrain › Relevé compteur de tête › Comparaison immédiate
- **Catégorie** : rendu donnees · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Un index plus bas (compteur remplacé, remis à zéro, relevé précédent erroné) est refusé sans issue : le champ « Explication éventuelle » ne permet pas de passer outre. Un volume de tête nul avec 40 m³ consommés en aval est classé « Bon · Les volumes restent proches ». Pour le premier relevé, le volume total est présenté comme une moyenne journalière.

**Impact pour l'agent.** L'agent reste bloqué devant un compteur neuf, ce qui rend la tâche impossible. Des fuites ou un compteur arrêté passent pour normaux.

**Preuve (version 2.11.0).** MainActivity.kt:1364 `if (selectedDate == null || indexValue == null || indexValue < previousIndex || …)` → toast ; shared TerrainMeasurementEngine.kt:48 `require(newIndex >= previousIndex)` ; 51 `val percent = if (volumeHead != 0.0) abs(gap / volumeHead * 100) else 0.0`, puis 53 `percent < 5 -> "Bon"` ; 66 `if (days > 0) volumeHead / days else volumeHead`, affiché « Moyenne : … m³/jour » (MainActivity.kt:1371) alors que `days = 0` sans historique (1369).

**Vérification sur 2.12.0.** MainActivity.kt:1997-2000 `if (selectedDate == null || indexValue == null || indexValue < previousIndex || …) toast("Date ou index invalide. Le nouvel index doit être supérieur ou égal au précédent.")` ; shared/…/terrain/TerrainMeasurementEngine.kt:48 `require(newIndex >= previousIndex)`, 51 `val percent = if (volumeHead != 0.0) abs(gap / volumeHead * 100) else 0.0` puis 53 `percent < 5 -> "Bon"`, 66 `if (days > 0) volumeHead / days else volumeHead` ; MainActivity.kt:2002 `days = … else 0` et 2004 « Moyenne : … m³/jour ». — Logique métier inchangée : aucune sortie pour un compteur remplacé ou remis à zéro (le champ « Explication » ne contourne rien) ; volume de tête nul avec aval > 0 classé « Bon » ; premier relevé présenté comme moyenne journalière. Aucun champ `head_meter_reading` dédié au remplacement n'a été ajouté.

**Recommandation.** Dans shared `headMeter` :
- volumeHead = 0 et aval > 0 → « Anormal · compteur de tête arrêté ? » ;
- moyenne journalière `null` sans date précédente, affichée « — ».

Dans le formulaire :
- case « Compteur remplacé / remis à zéro » qui rend l'explication obligatoire et envoie un indicateur dédié (à prévoir côté API `head_meter_reading`) au lieu de bloquer ;
- message sur le champ « Minimum attendu : 1 234,00 ».

### TERRAIN-09 — Fiche abonné : le téléphone accepte un nom que le serveur considère encore comme manquant

- **Sévérité** : Majeur
- **Écran** : Terrain › Noms d'abonnés › formulaire
- **Catégorie** : coherence · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** La tâche « nom manquant » existe justement parce que le champ contient « 0341234567 » ou « N/A ». Le formulaire pré-remplit cette valeur et l'agent peut toucher « Enregistrer » sans rien changer : le compteur local baisse (« Nom enregistré · la liste locale est à jour »), le serveur réenregistre la valeur invalide, et la tâche réapparaît à la synchro suivante. Le téléphone est accepté sous n'importe quelle forme. Le titre ne rappelle ni le village ni l'ouvrage.

**Impact pour l'agent.** Faux sentiment d'avoir terminé, tâches qui reviennent, données d'abonnés non conformes.

**Preuve (version 2.11.0).** MainActivity.kt:1829 `field("Nom de l’abonné").apply { setText(item.optString("nom")) }` ; 1845 seule règle `if (subscriberName.isBlank())` ; 1856 `applyLocalTerrainCompletion`, qui met `has_subscriber_name = true` (TerrainRepository.kt:114) ; 1830-1832 téléphone sans contrôle ; 1837 titre = code seul. Serveur views_preparation_tournee.py:713-719 : un nom est invalide s'il vaut `n/a`, `na`, `inconnu` ou `non renseigne`, ou s'il ne contient que des chiffres (`normalized_name.replace(' ', '').isdigit()`).

**Vérification sur 2.12.0.** MainActivity.kt:2467-2492 showSubscriberForm : `field("Nom de l’abonné").apply { setText(item.optString("nom")) }`, seule règle `if (subscriberName.isBlank())` (l. 2480), téléphone `InputType.TYPE_CLASS_PHONE` sans contrôle, `applyLocalTerrainCompletion(store, item, work, "subscriber")` (l. 2491), titre `item.optString("code")` (l. 2471) ; backend views_preparation_tournee.py:732-739 et 1078-1080 `_nom_abonne_renseigne` : refuse n/a, na, inconnu, non renseigne et les valeurs uniquement numériques. — Aucune règle portée dans shared (pas de TerrainEditRules.isValidSubscriberName). L'agent peut enregistrer sans rien changer une valeur que le serveur juge invalide : la tâche baisse localement puis réapparaît à la synchro suivante. Côté serveur, `update_point` ne rejette toujours que le nom vide (l. 1422-1425), ce qui crédite même des points quand l'ancien nom était invalide.

**Recommandation.** - Porter la règle du serveur dans shared (`TerrainEditRules.isValidSubscriberName`) et l'appliquer ici, avec une erreur sur le champ : « Un nom de personne est attendu, pas un numéro ».
- Afficher la valeur actuelle invalide en texte d'aide et laisser le champ vide.
- Si cette valeur ressemble à un numéro, proposer de la déplacer dans Téléphone.
- Valider le format malgache (10 chiffres en 03x) et l'afficher groupé.
- Titre : « PE-042 · Ampasika (village) ».

### TERRAIN-10 — Liste d'une catégorie : toucher coche au lieu d'ouvrir, ouverture cachée en appui long, et Retour ferme l'app

- **Sévérité** : Majeur
- **Écran** : Terrain › liste « Photos de points manquantes » (téléphone)
- **Catégorie** : ergonomie · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** Sur téléphone, la sélection multiple, pensée pour la tablette (4a), devient le chemin principal. Toucher une carte ne fait que la cocher. Pour traiter un seul point, il faut cocher puis « Traiter la sélection (1) », ou découvrir un appui long qu'aucun indice visuel ne signale. Le geste Retour d'Android 15 ferme MainActivity au lieu de revenir à « À compléter » : recherche et sélection sont perdues.

**Impact pour l'agent.** Désorientation, sortie involontaire de l'application en marchant, taps inutiles pour l'action la plus courante (« je suis devant ce point, je le traite »).

**Preuve (version 2.11.0).** MainActivity.kt:1658 `container.setOnClickListener { check.isChecked = !check.isChecked }` ; 1659 `container.setOnLongClickListener { showTerrainItem(...) }` ; 1477-1479 `secondaryButton("← Retour")` dans le contenu ; aucune occurrence de `OnBackPressedCallback` / `onBackPressed` dans app/src (recherche Grep) ; 1515 puce « Tout » (= tout cocher), homonyme du filtre « Tout » (1069) ; puces de 32 dp (1519). README l. 309-311 : « Le traitement par lot est un raccourci, jamais le seul chemin ».

**Vérification sur 2.12.0.** MainActivity.kt:2291 `container.setOnClickListener { check.isChecked = !check.isChecked }` et 2292 `setOnLongClickListener { showTerrainItem(...) }` (même schéma en tablette 2367-2368, avec un bouton « Ouvrir ») ; 2110-2112 `secondaryButton("← Retour")` dans le contenu ; 2148 puce « Tout » = tout cocher, 2152 hauteur 32 dp ; grep OnBackPressedCallback / onBackPressed / onBackPressedDispatcher dans app/src : aucune occurrence. — Inchangé : sur téléphone, toucher une carte ne fait que cocher, l'ouverture d'un seul point passe par l'appui long ou par cocher puis traiter. Seul ajout : sans sélection, le bouton affiche « Tout traiter en série (N) » (l. 2135), ce qui n'ouvre pas non plus un point isolé. Aucun callback de retour : le geste Retour quitte MainActivity au lieu de fermer la catégorie ou la fiche ouvrage.

**Recommandation.** - En largeur COMPACT, toucher une carte doit ouvrir l'élément (ou lancer directement l'action).
- Réserver la case à cocher à l'EXPANDED (`asTable`) ou à un mode « Sélectionner » explicite.
- Enregistrer `onBackPressedDispatcher.addCallback(this) { … }` qui ferme dans l'ordre la série, `terrainCategory`, puis le mode works/nearby avant de laisser l'activité se terminer.
- Renommer la puce de sélection « Tout cocher ».

### TERRAIN-11 — Listes et sauvegardes construites d'un bloc sur le fil principal

- **Sévérité** : Majeur
- **Écran** : Terrain › listes de catégorie, Par ouvrage, enregistrement en série
- **Catégorie** : performance percue · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Ouvrir une catégorie ou « Par ouvrage » construit des milliers de vues d'un coup, ce qui contribue au voile et au spinner de l'observation 5. Chaque saisie de série sérialise et réécrit tout le snapshot (plusieurs Mo, déduction), puis compresse la photo sur le fil UI. Sur un téléphone d'entrée de gamme, cela donne un gel perceptible entre deux points.

**Impact pour l'agent.** L'app paraît figée, l'agent touche de nouveau (double action) et un ANR est possible sur les gros périmètres.

**Preuve (version 2.11.0).** MainActivity.kt:1538-1582 crée une carte (CheckBox, 2 TextView, 3 écouteurs) par élément dans un ScrollView, soit 1 627 vues pour les photos et 1 282 pour le GPS (capture 13) ; 1168-1204 crée 401 cartes avec `SparklineView` ; TerrainRepository.kt:124 `store.snapshot = snapshot` après chaque action → TerrainDatabase.kt:376-388 `val raw = value.toString()` du snapshot entier, réécrit en blocs dans une transaction ; MainActivity.kt:180 `compressPointPhoto` (décodage et JPEG) exécuté dans le callback sur le fil UI.

**Vérification sur 2.12.0.** MainActivity.kt:2171-2216 une carte (CheckBox + 2 TextView + écouteurs) par élément ajoutée dans le ScrollView ; 1339-1378 une carte avec SparklineView par ouvrage (401) sans pagination ; TerrainRepository.kt:125 `store.snapshot = snapshot` après chaque action → OfflineStore.kt:360-364 → TerrainDatabase.kt:376-388 / HydriaSnapshotGateway.kt:30-46 `value.toString()` du snapshot entier réécrit par blocs dans une transaction ; MainActivity.kt:224 `runCatching { compressPointPhoto(photoFile) }` dans le callback ActivityResult (fil UI) ; 205-206 copie de galerie `copyTo` aussi sur le fil UI. — Rien n'a été déplacé sur `executor` ni paginé. La copie de photo depuis la galerie (nouvelle option) ajoute de l'E/S sur le fil UI. Le risque ANR reste une déduction (non mesuré), mais le commentaire de TerrainRules.perimeter (« bloquait le fil principal … (ANR) ») montre que le problème s'est déjà produit sur gros périmètres.

**Recommandation.** - Passer `renderTerrainTaskList` et `renderTerrainWorks` sur un RecyclerView à vues programmatiques, ou paginer (« 50 premiers + Afficher plus »).
- Déplacer `store.snapshot = …` et `compressPointPhoto` sur `executor`, avec retour par `runOnUiThread`.
- À terme, mettre à jour les compteurs et les drapeaux en SQL par ligne plutôt que réécrire le JSON complet.

### TERRAIN-12 — « Par ouvrage » et « Autour » ne débouchent sur aucune action

- **Sévérité** : Mineur (initialement Majeur)
- **Écran** : Terrain › Par ouvrage / Autour
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Partiellement corrigé en 2.12.0

**Constat.** Depuis la vue par ouvrage, on ne peut ni lister ni enchaîner les tâches de cet ouvrage. La carte ouvre une boîte sans action utile, sauf pour le débit. Il n'y a pas de tri par complétude ou par distance, et le % n'est pas coloré selon un seuil. « Autour » demande de relancer la position à chaque fois.

**Impact pour l'agent.** L'agent qui arrive dans un village ne peut pas dire « montre-moi et enchaîne tout ce qui manque ici », alors que c'est son besoin le plus naturel.

**Preuve (version 2.11.0).** MainActivity.kt:1166-1205 : 401 cartes dans l'ordre alphabétique du serveur, sans recherche ni tri ; 1199-1202, toucher une carte → `showTerrainWork` : 1748-1757 AlertDialog « x % complet / n point(s) » avec « MESURER LE DÉBIT » ou « OK » ; 1171-1177 manques résumés en texte (« 3 GPS · 2 nom(s) · 5 photo(s) PE ») ; 1184 badge toujours INFO sauf à 100 % ; 1407-1418 « Autour » exige « Ma position » à chaque visite (`nearbyLocation` en mémoire seulement) et exclut GPS et débits (1429, 1434-1435). Maquette 2a : % coloré selon un seuil, chips de manques.

**Vérification sur 2.12.0.** MainActivity.kt:1331-1397 champ « Rechercher un ouvrage (nom ou code) » ; 1370-1374 toucher une carte ouvre renderTerrainWorkDetail (l. 1439-1533) : liste des points et équipements avec boutons GPS / Abonné / Photo (statusButton → startTerrainItemAction, l. 1405-1417), recherche de points, boutons débit ; showTerrainWork (l. 2378) n'est plus appelé. Mais l. 1355 `HydriaUi.badge(…, if (completion == 100) Tone.SUCCESS else Tone.INFO)` ; 1040-2090 « Autour » : bouton « Ma position » (l. 2040-2047), `nearbyLocation` en mémoire, tâches limitées à abonné / photo (l. 2067-2079). — Corrigé pour l'essentiel : la fiche ouvrage permet de lister les tâches d'un ouvrage et d'agir directement, et la recherche par ouvrage existe. Restent : aucun « Enchaîner les N tâches de cet ouvrage », pas de tri par complétude ou distance, badge de % toujours INFO sauf 100 %, « Autour » sans position automatique ni mémorisation et sans GPS ni débits. Sévérité abaissée de majeur à mineur.

**Recommandation.** - Toucher une carte d'ouvrage ouvre la liste de ses tâches : réutiliser `renderTerrainTaskList` avec un filtre `ouvrageId`, plus « Enchaîner les N tâches de cet ouvrage ».
- Ajouter un champ de recherche et un tri (moins complet d'abord, ou plus proche).
- Colorer le badge selon un seuil (vert ≥ 90, orange ≥ 60, rouge en dessous), comme en 2a.
- Pour « Autour », demander la position automatiquement à l'entrée si la permission est accordée, et mémoriser la dernière position 10 minutes.

### TERRAIN-13 — Premier écran : 3,5 tâches visibles, barre de mesures permanente en environ 10 sp, tâche terminée au milieu

- **Sévérité** : Mineur
- **Écran** : Terrain › accueil
- **Catégorie** : ergonomie · **Effort** : S
- **Statut** : Partiellement corrigé en 2.12.0

**Constat.** Avant la première tâche viennent le pointage (≈ 59 dp), la complétude (≈ 152 dp), deux boutons de 64 dp et les filtres. En bas, 79 dp sont réservés à deux actions rares (mesures périodiques), écrites dans le plus petit texte de l'écran : le contraste de 8:1 est bon, la taille ne l'est pas. La ligne « Noms d'abonnés ✓ Terminé » occupe un créneau entre deux tâches à faire, sans l'atténuation prévue. Les sous-titres sont statiques (« Échéance de mesure dépassée ») là où la maquette donnait un contexte (« 3 captages »). Les deux primaires concurrents viennent de la maquette : c'est un choix assumé, mais à rediscuter.

**Impact pour l'agent.** Défilement à chaque visite, actions rares sur-représentées, et une tâche terminée aussi visible qu'une tâche à faire.

**Preuve (version 2.11.0).** MainActivity.kt:966 `pointageShortcut()` avant la carte ; 1088 `if (taskAction == null) taskAction = terrainMeasureBar(terrain)` ; 1132-1141 `secondaryButton("Débit source").apply { textSize = 12f … }` (× 0,85 ≈ 10 sp) ; dump 13 : barre `[0,1310][720,1445]` = 79 dp fixes ; 1145-1163 ordre figé des lignes ; HydriaVisuals.kt:372 aucune atténuation quand `count == 0` (README : « opacity 0.7 ») ; 1045-1055 deux boutons primaires pleins. Capture 01 : première ligne de tâche à y = 828 sur 1612.

**Vérification sur 2.12.0.** MainActivity.kt:920 pointageShortcut() défini mais plus appelé (grep : aucune utilisation) ; Terrain n'a plus ni « Commencer ma tournée » ni « Carte » en boutons primaires (déplacés dans le menu, l. 5106-5111) ; en revanche l. 1196 `terrainPointsCard()` (« MES POINTS TERRAIN », compteur 34 sp) ajoutée avant les filtres ; 1247 `if (taskAction == null) taskAction = terrainMeasureBar(terrain)` avec 3 boutons `textSize = 12f` (l. 1291-1305, zone fixe 56 dp + 12 dp de marge, l. 2093-2101) ; 1307-1326 ordre figé des 6 lignes et sous-titres statiques ; HydriaVisuals.kt:372-386 aucune atténuation quand count == 0. — Corrigés : le raccourci Pointage (désormais un onglet de navigation) et les deux boutons primaires concurrents ont quitté l'accueil. Restent valides : barre de mesures permanente en petit texte (maintenant 3 boutons), ligne « Terminé » non atténuée ni repliée entre deux tâches à faire, sous-titres statiques. Une carte « points terrain » de ~80 dp a pris la place libérée.

**Recommandation.** - Déplacer « Débit source » et « Compteur de tête » en `taskRow` « Mesures périodiques » dans la liste, ou dans la fiche ouvrage, et libérer le bas.
- Trier : tâches à faire d'abord, terminées en fin à `alpha 0.7` ou repliées sous « Terminé (1) ».
- Compacter le raccourci Pointage en dehors des créneaux proches.
- Sous-titres dynamiques (« dans 37 ouvrages »).
- Envisager « Carte » en bouton secondaire avec icône pour ne garder qu'un primaire.

### TERRAIN-15 — Puces de filtre : dernière lettre rognée, 30 dp de haut, mélange Archivo et Roboto

- **Sévérité** : Mineur
- **Écran** : Terrain › rangée À compléter (Tout / Par ouvrage / Autour), listes
- **Catégorie** : accessibilite · **Effort** : S
- **Statut** : Vérifié en 2.12.0

**Constat.** Déduction : le faux gras épaissit les glyphes sans augmenter leur largeur mesurée, donc dans un TextView `WRAP_CONTENT` serré la dernière lettre est coupée (observation 3). Les puces font 30 dp : en dessous des 48 dp minimum et même des 34 dp prévus. Les sous-écrans du Terrain (Par ouvrage, listes) passent en Roboto via `text()`, d'où une typographie mêlée.

**Impact pour l'agent.** Libellés tronqués, cibles difficiles à toucher en marchant ou avec des gants, finition incohérente d'un écran à l'autre.

**Preuve (version 2.11.0).** res/font/archivo.xml `app:fontProviderQuery="name=Archivo&amp;weight=400"` (seule graisse téléchargée) ; HydriaVisuals.kt:127-129 `Typeface.create(base, weight.coerceIn(1, 1000), false)` → graisses 600/700 synthétisées ; MainActivity.kt:1071-1073 `minHeight = dp(30)` et `LayoutParams(WRAP_CONTENT, dp(30))`, alors que `chip()` pose 34 dp (HydriaVisuals.kt:318) et que dimens fixe `hydria_target_min 48dp` ; MainActivity.kt:4797 `text()` en `Typeface.create("sans-serif", …)` pour les cartes d'ouvrage et de tâche. Capture 01 : « Toul », « Par ouvrag ».

**Vérification sur 2.12.0.** res/font/archivo.xml `app:fontProviderQuery="name=Archivo&amp;weight=400"` (une seule graisse) ; HydriaVisuals.kt:127-133 `Typeface.create(base, weight.coerceIn(1, 1000), false)` (graisses 600/700 synthétisées) ; MainActivity.kt:1226-1229 filtres Tout / Par ouvrage / Autour : `minHeight = dp(30)` et `LayoutParams(WRAP_CONTENT, dp(30))` alors que HydriaUi.chip pose 34 dp (HydriaVisuals.kt:318) et dimens `hydria_target_min 48dp` ; MainActivity.kt:5533-5540 `text()` en `Typeface.create("sans-serif", …)` pour les cartes d'ouvrage, de tâche et de fiche. — Aucun changement. Les puces d'autres écrans sont à 32-34 dp, celles du Terrain à 30 dp. Le rognage de la dernière lettre reste une déduction (faux gras non compté dans la mesure du TextView), non revérifié à l'exécution ; les cibles tactiles trop petites et le mélange Archivo/Roboto sont, eux, confirmés par le code.

**Recommandation.** - Déclarer une famille par graisse (`archivo_600.xml`, `archivo_700.xml` avec `weight=600/700` dans la requête), ou embarquer le TTF variable dans res/font, et sélectionner la famille dans `HydriaType.display()`.
- Puces de 40 dp visibles avec une zone tactile de 48 dp (padding vertical ou TouchDelegate).
- Faire passer `text()` par `HydriaType.display()`.

### TERRAIN-14 — accentedCard : coins colorés parasites en haut et en bas à droite

- **Sévérité** : Cosmétique (initialement Mineur)
- **Écran** : Terrain › lignes de tâche, raccourci Pointage (toutes les accentedCard)
- **Catégorie** : esthetique · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** La couche « filet » est en réalité un rectangle de couleur pleine largeur. Ses coins droits, carrés, dépassent derrière les coins arrondis du corps : chaque carte montre deux éclats de couleur à droite. L'observation 2 est confirmée.

**Impact pour l'agent.** La règle « la criticité est à gauche » est brouillée et l'écran le plus vu de l'app paraît non fini.

**Preuve (version 2.11.0).** HydriaVisuals.kt:262-270 `cornerRadii = floatArrayOf(radius, radius, 0f, 0f, 0f, 0f, radius, radius)` (coins haut-droit et bas-droit carrés) puis `setLayerInset(1, dpi(context, 3f), 0, 0, 0)` sur un corps `rounded(…, 14f, …)` arrondi aux quatre coins. Captures 01 et 13 : éclats rouges, orange, verts et cyan à droite de chaque ligne et du raccourci Pointage.

**Vérification sur 2.12.0.** HydriaVisuals.kt:262-270 accentedCard : `cornerRadii = floatArrayOf(radius, radius, 0f, 0f, 0f, 0f, radius, radius)` sur la couche barre pleine largeur, puis `LayerDrawable(arrayOf(bar, body))` avec `setLayerInset(1, dpi(context, 3f), 0, 0, 0)` et un corps `rounded(…, 14f, …)` arrondi aux quatre coins. — Code inchangé : les coins haut-droit et bas-droit carrés de la couche barre dépassent derrière les coins arrondis (14 dp) du corps, d'où deux éclats colorés à droite de chaque accentedCard (lignes de tâche). Confirmé par lecture du code ; pas de capture refaite. Défaut purement visuel, classé cosmétique.

**Recommandation.** Couche barre avec `cornerRadius = radius` sur les quatre coins : le corps décalé de 3 dp la recouvre alors exactement à droite. Variante : vraie bande de 3 dp (`setLayerGravity(0, Gravity.START)`, `setLayerWidth(0, 3dp)`) et `clipToOutline` avec un `ViewOutlineProvider` arrondi.


## Réparations et Planning

_Audit initial sur la version 2.11.0._

**Synthèse du domaine.** Le domaine Réparations / Planning repose sur une base métier solide : règles partagées en KMP avec tests, cascade Groupe > Type > Activité, règles de cible et de composants reprises du serveur, verrouillage des plannings validés. Ses principaux risques ne sont pas visuels : ils touchent l'intégrité des données saisies sur le terrain.

Quatre constats critiques :
1. L'éditeur présélectionne d'office le premier employé dans l'ordre alphabétique et la première activité. Les contrôles « Sélectionnez un employé / une activité » ne peuvent donc jamais se déclencher.
2. Le statut « planifie », posé par l'import Excel et absent des choix du serveur, s'affiche tel quel. Pire : il est réécrit en « En cours » à chaque modification.
3. Les créations et modifications faites hors ligne n'apparaissent nulle part avant la synchro. Elles ne portent aucune clé d'idempotence, d'où des doublons et des retours en arrière silencieux.
4. Le formulaire de 10 à 11 champs vit dans un AlertDialog qui se ferme sans confirmation (toucher hors du cadre, geste retour d'Android 15). Les erreurs ne s'affichent qu'en toast.

Côté lecture, la liste des Réparations est écrasée par trois boutons pleine largeur par carte (environ 60 % de la hauteur d'une carte) et par des groupes entièrement dépliés : 60 interventions sur Ankazondandy, soit environ 23 écrans avant le deuxième ouvrage. Elle est aussi reconstruite en entier, de façon synchrone (environ 5 700 vues). Conséquences : voile au changement d'onglet, figeage après « Terminer » et après chaque synchro, perte de la position de défilement.

Côté Planning, l'en-tête fixe (titre, pointage, bouton) occupe la moitié de l'écran. La carte de pointage annonce « Aucun planning aujourd'hui » à côté de « 8 RDV » le même jour.

« Marquer terminée » est confirmé mais anonyme et irréversible. Le serveur valide la réparation et écrase « Suite à donner ».

Le reste relève de la lisibilité et de la finition :
- chiffre de retard « -224 » ambigu, qui déborde de sa colonne de 46 dp dès l'échelle de police 1,0 (même cause que l'observation 1) ;
- textMuted à environ 3,7:1 ;
- badge « 99+ » rogné en « 99 » ;
- bande de jours sans trous visibles, sans mois et sans repère « aujourd'hui » ;
- coins parasites des cartes ;
- textes en dur, non traduits en malgache.

Les corrections les plus rentables sont de petits changements dans MainActivity et HydriaVisuals : dialogue non annulable, sélecteur de date, en-tête qui défile, message de confirmation explicite avec possibilité d'annuler, colonne de retard en largeur adaptative. Elles peuvent précéder les chantiers de fond : superposition des actions en attente et idempotence côté serveur, rendu paresseux de la liste.

**À préserver :**

- Garde-fou avant l'action irréversible : « Marquer terminée » ouvre une confirmation (MainActivity.kt:3612-3623). L'action est mise en file avec un retour sonore et un toast qui distingue « en cours d'envoi » de « hors connexion ». La fin est reflétée tout de suite via pendingCompletionIds (opacité 0,75, conforme à la maquette).
- La cascade Groupe > Type d'activité > Activité (HydriaActivityCascade) remplace une longue liste « Type - Activité ». La flèche ▾ y est redessinée pour qu'on voie une liste déroulante, et la cascade se verrouille sur un planning validé.
- Autocomplétion d'ouvrage insensible aux accents (AutocompleteMatch.normalize). Une frappe exacte est résolue à la perte du focus, avec une erreur en ligne « Choisissez un ouvrage dans la liste » (MainActivity.kt:4207-4209).
- Les règles de l'activité sont reprises du serveur : cible et composants obligatoires, composant unique, types admis. Les libellés « — obligatoire » / « (un seul) » sont dynamiques et les messages d'état vide sont utiles. La cible et les composants restent conservés si l'activité change. Le client n'envoie jamais de cible quand les options ne sont pas chargées, ce qui évite d'effacer des données côté serveur.
- Planning validé : l'ouvrage et l'activité sont verrouillés, un texte explicatif s'affiche et le serveur applique la même règle (cohérence client/serveur).
- Réparations regroupées par ouvrage, avec localisation, ligne « À traiter en premier » colorée par criticité et nombre d'interventions. Le mode « Hors périmètre · consultation » est explicite et ne propose aucune action.
- Bande de jours synchronisée dans les deux sens avec le défilement (suivi du défilement, défilement doux, case centrée). Ses contentDescription sont complètes (date, nombre de RDV, férié, week-end), et les badges Férié / Week-end apparaissent sur les sections.
- Logique métier dans le module partagé et testée (PlanningAgenda, RepairOverview, RepairFormRules, PlanningViewModel). Les sous-filtres se réinitialisent en cascade et les rappels parasites du Spinner sont neutralisés. Les filtres sont repliés par défaut, avec le nombre de filtres actifs dans le bouton.
- Retard en chiffre principal monospace et filet coloré à gauche, conformes au handoff : la criticité se lit d'un coup d'œil dans une liste.
- Le pointage est intégré à l'agenda : créneau en cours ou prochain, état par planning (✓ / ✗ / à pointer) et nombre de pointages en attente d'envoi.

### REP_PLAN-03 — Saisies hors ligne invisibles, réédition sur valeurs périmées et créations non idempotentes (doublons)

- **Sévérité** : Critique
- **Écran** : Éditeur, liste Réparations, agenda Planning
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Trois défauts se cumulent :
1. Une réparation ou un planning créé hors ligne n'apparaît ni dans l'agenda ni dans la liste avant une synchro réussie. L'agent croit à un échec et ressaisit.
2. Après une modification hors ligne, « Modifier » se pré-remplit depuis le snapshot, donc avec les anciennes valeurs. Une seconde correction (par ex. la remarque) renvoie l'ancienne date ou l'ancien employé et annule la première.
3. Sur réseau intermittent, un POST réussi côté serveur mais expiré côté client (readTimeout 120 s) est rejoué : comme aucune clé ne l'identifie, il crée un doublon.

**Impact pour l'agent.** Doublons de plannings et de réparations, retours en arrière silencieux de corrections : exactement ce que l'offline-first doit éviter.

**Preuve (version 2.11.0).** MainActivity.kt:4245-4249 `PlanningsRepository.enqueueSave(store, payload); dialog.dismiss(); toast(…); updateStatus(); if (isOnline()) synchronize()` : ni rendu ni fusion des actions en attente (idem l.4275-4279). Seules les fins de réparation sont reflétées (l.3411 `pendingCompletionIds`). HydriaApi.kt:272-273 : la liste des champs envoyés (`"id", "employe_id", …, "composants_ids"`) n'inclut pas `local_uuid`. Backend views_preparation_tournee.py:1149-1151 `planning = Planning(); created = True`, sans clé d'idempotence, contrairement aux photos (l.1292-1294).

**Vérification sur 2.12.0.** MainActivity.kt:4892-4896 et 4922-4926 `…enqueueSave(store, payload); dialog.dismiss(); toast(…); updateStatus(); if (isOnline()) synchronize()` sans fusion dans les listes (seul pendingCompletionIds, l.4048/989, reflète les fins) ; HydriaApi.kt:298-299 liste de champs sans `local_uuid` ; HydriaApi.kt:318 `readTimeout = 120_000` ; views_preparation_tournee.py:1187 `planning = Planning()` sans clé d'idempotence (local_uuid n'existe que pour pointage GPS et photos). — Les trois défauts sont intacts. 1) Une saisie hors ligne n'apparaît ni dans l'agenda ni dans la liste tant que la synchro n'a pas abouti (l'éditeur se pré-remplit depuis le snapshot). 2) Une seconde modification hors ligne repart des anciennes valeurs et peut annuler la première. 3) Un POST abouti côté serveur mais expiré côté client est rejoué et crée un doublon. Je conserve critique car c'est le cœur de la promesse hors ligne de l'app et la ressaisie (donc le doublon) est le réflexe prévisible de l'agent.

**Recommandation.** Créer dans commonMain une fonction `PendingOverlay.apply(items, pending)`, à côté de RepairOverview. Elle fusionne les payloads `save_planning` / `save_repair` (par `id`, ou comme éléments provisoires pour les créations) avec un badge « En attente d'envoi ». L'utiliser dans renderRepairs, dans renderPlannings et comme source de `existing` dans showPlanningEditor, puis rafraîchir l'écran après l'enqueue.

Idempotence : ajouter `local_uuid` à savePlanningLike et à HydriaPlanningsClient.savableFields. Côté serveur, le stocker (champ `client_uuid` unique sur Planning) et renvoyer le planning existant en cas de rejeu.

### REP_PLAN-01 — Éditeur : employé et activité présélectionnés d'office (1er dans l'ordre alphabétique)

- **Sévérité** : Majeur (initialement Critique)
- **Écran** : Dialogue Nouvelle réparation / Nouveau planning (showPlanningEditor)
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Partiellement corrigé en 2.12.0

**Constat.** En création, le formulaire sélectionne silencieusement le premier employé de la base par ordre alphabétique, et non l'agent connecté (l'app ne mémorise que store.employeeName, l.408). Il sélectionne aussi la première activité du premier type du premier groupe. Les validations « Sélectionnez un employé / une activité » sont donc inatteignables. Un agent qui ne règle que l'ouvrage et la date puis touche « Enregistrer » crée une réparation au nom d'un collègue, avec une activité arbitraire. Le serveur l'accepte : employé de la même base, activité autorisée (l.1102-1118). Risque secondaire : l'autocomplétion n'affiche que le nom de l'ouvrage (l.4010), sans commune, et la résolution à la perte du focus prend la première correspondance exacte. Deux ouvrages homonymes seraient indiscernables (à vérifier dans les données).

**Impact pour l'agent.** Plannings et réparations attribués au mauvais agent ou à la mauvaise activité. Pointage, primes, statistiques et doublons calculés par activité sont faussés, sans que personne ne s'en aperçoive sur le terrain.

**Preuve (version 2.11.0).** MainActivity.kt:4035 `selectById(employeeSpinner, employees, existing?.optString("employe_id").orEmpty())` : en création, l'id est vide, donc position -1, puis repli `fallback: Int = 0` (l.4031-4034). Backend views_preparation_tournee.py:110 : `.order_by('nom_employe')`. HydriaActivityCascade.kt:47-48 `fill(groupSpinner, tree.map { it.name }, 0); fillTypes(0, 0)` puis l.91 `spinner.setSelection(selection…)`. Résultat : PlanningFormRules (PlanningViewModel.kt:27-28, `draft.employeeId == null`, `draft.activityId == null`) ne peut jamais se déclencher.

**Vérification sur 2.12.0.** MainActivity.kt:4681-4682 `selectById(employeeSpinner, employees, existing?.optString("employe_id") ?: employees.firstOrNull { it.optBoolean("moi") }?.optString("id").orEmpty())` + views_preparation_tournee.py:972 `'moi': item.id == employe.id`. Reste : HydriaActivityCascade.kt:47-48 `fill(groupSpinner, tree.map { it.name }, 0); fillTypes(0, 0)` ; MainActivity.kt:4655 libellés d'ouvrage = `optString("nom")` seul. — Corrigé : l'employé connecté est désormais présélectionné en création (drapeau « moi » ajouté côté serveur et lu dans l'éditeur). Non corrigé : la cascade présélectionne toujours le 1er groupe, 1er type, 1re activité (aucun placeholder « Choisir »), donc ACTIVITY de PlanningFormRules/RepairFormRules reste inatteignable et un agent peut enregistrer une réparation avec une activité arbitraire. L'autocomplétion d'ouvrage n'affiche toujours que le nom, sans commune (planning_ouvrages = {id, nom}). Sévérité abaissée de critique à majeur car le risque d'attribution au mauvais agent a disparu.

**Recommandation.** 1. Côté serveur, ajouter `employe_id` dans `utilisateur` (views_preparation_tournee.py:988). Dans showPlanningEditor, présélectionner cet employé, avec repli par correspondance sur store.employeeName.
2. Ajouter à HydriaActivityCascade un paramètre `placeholder: Boolean`, vrai en création : chaque niveau commence par « — Choisir — » et selectedActivity vaut null tant que l'agent n'a pas choisi. La règle partagée ACTIVITY redevient effective.
3. Construire les libellés d'ouvrage sous la forme « Nom · Commune » (le serveur enrichit references.ouvrages).

### REP_PLAN-02 — Statut « planifie » affiché brut et réécrit en « En cours » à chaque modification

- **Sévérité** : Majeur (initialement Critique)
- **Écran** : Planning : carte d'agenda et dialogue Modifier
- **Catégorie** : rendu donnees · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** get_statut_display() renvoie le code brut quand il n'appartient pas aux choix : le libellé « planifie » (minuscule, sans accent) s'affiche donc tel quel. Il est en orange gras sous le badge orange « À réaliser » : deux signaux d'alerte pour l'état nominal. Plus grave : sur un planning importé, « Modifier » ne retrouve pas ce statut dans la liste et retombe sur « En cours ». Le moindre enregistrement, même pour corriger une remarque ou une date, réécrit silencieusement le statut. La liste elle-même affiche « Termine / Annule / Reporte » sans accents (libellés du modèle).

**Impact pour l'agent.** Statut illisible et alarmant au quotidien. Altération silencieuse du statut de chaque planning importé qu'un agent touche.

**Preuve (version 2.11.0).** MainActivity.kt:3969-3971 `"${planning.optString("statut", …)}$specialDay$proof", 13f, true, if (planningDone) … else HydriaColors.warning`. Backend views_preparation_tournee.py:283 `'statut': planning.get_statut_display()`. models.py:165-170 : STATUS_CHOICES vaut en_cours/termine/annule/reporte, sans 'planifie'. planning/views.py:4944 : l'import Excel écrit `'statut': statut if statut else 'planifie'`. MainActivity.kt:4040 `selectById(statusSpinner, statuses, existing?.optString("statut_code").orEmpty())` replie sur la position 0, « En cours ». Le serveur refuse tout autre code (l.1104-1105). Capture 04_planning : « planifie » en orange gras sous le badge « À réaliser ».

**Vérification sur 2.12.0.** MainActivity.kt:4614-4616 affiche `planning.optString("statut", …)` brut en gras orange sous le badge « À réaliser » ; MainActivity.kt:4687 `selectById(statusSpinner, statuses, existing?.optString("statut_code")…)` replie sur la position 0 ; views_preparation_tournee.py:284 `planning.get_statut_display() if planning.statut …` ; models.py:165-170 STATUS_CHOICES = en_cours/termine/annule/reporte (non accentués) ; views.py:4944 `'statut': statut if statut else 'planifie'`. — Aucun changement. Un planning importé avec le code « planifie » s'affiche tel quel (get_statut_display renvoie le code brut) et « Modifier » retombe sur « En cours » puis le réécrit à l'enregistrement (le serveur refuse tout code hors liste, views_preparation_tournee.py:1141). Les libellés « Termine / Annule / Reporte » restent sans accents. Je ramène à majeur : l'effet ne touche que les lignes dont le statut est hors liste (import Excel), mais la réécriture silencieuse est réelle.

**Recommandation.** Côté serveur : ajouter ('planifie', 'Planifié') aux STATUS_CHOICES, accentuer les libellés et accepter ce code dans `_save_mobile_planning`.

Côté client : créer dans commonMain une table `PlanningStatusLabels` (code → libellé FR/MG), utilisée par planningAgendaCard et par le Spinner. Dans showPlanningEditor, si `statut_code` est absent de `statuses`, l'insérer en tête comme option « Planifié (actuel) » pour le préserver. Dans la carte, ne plus répéter le statut nominal en orange : texte textSecondary, l'orange étant réservé à « Reporté » et au retard.

### REP_PLAN-04 — Formulaire de 10-11 champs dans un AlertDialog fermable sans confirmation ; erreurs en toast

- **Sévérité** : Majeur (initialement Critique)
- **Écran** : Dialogue Nouvelle réparation / Nouveau planning / Modifier
- **Catégorie** : ergonomie · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** L'éditeur enchaîne Employé, Ouvrage, [Groupe], Type, Activité, Cible, Composants, Date, Statut, [Priorité] et Remarque, soit environ deux hauteurs d'écran à faire défiler dans un AlertDialog standard. Plusieurs gestes le ferment sans avertissement et perdent toute la saisie : toucher la zone voilée, la touche retour, ou le geste retour depuis le bord (Android 15, fréquent quand on fait défiler d'une main). Les erreurs de validation (règles d'activité, ouvrage obligatoire, employé) arrivent en toast en bas de l'écran, souvent masqué par le clavier et éphémère, sans amener l'agent jusqu'au champ fautif.

**Impact pour l'agent.** Saisie perdue en marchant, ressaisie complète. Erreurs non comprises, donc abandon ou contournement.

**Preuve (version 2.11.0).** MainActivity.kt:4194-4203 `AlertDialog.Builder(this)…setView(scroll(form))…setNegativeButton("Annuler", null)…create()` : ni setCancelable(false) ni setCanceledOnTouchOutside(false). Seul le dialogue l.3327 le fait. Les erreurs passent par `toast(message)` (l.4216-4219, 4233, 4273) ; seuls la date (`dateField.error`) et l'ouvrage ont une erreur en ligne.

**Vérification sur 2.12.0.** MainActivity.kt:4841-4850 `AlertDialog.Builder(this).setTitle(…).setView(scroll(form)).setNegativeButton("Annuler", null).setPositiveButton("Enregistrer", null).create()` sans setCancelable(false) (seul le dialogue l.3964 le fait) ; erreurs en `toast(...)` l.4865, 4880, 4920 ; seuls dateField.error (l.4879, 4919) et workPicker.error (l.4855) sont en ligne. — Inchangé, et le formulaire est plutôt plus long qu'en 2.11.0 (cascade 3 niveaux, cible, composants, date, statut, priorité, remarque). Un toucher sur la zone voilée ou un geste retour ferme le dialogue et perd toute la saisie ; les erreurs de règles d'activité, d'employé ou d'activité arrivent en toast. Pas de brouillon sauvegardé. Ramené à majeur : perte de saisie en cours, pas de corruption de données.

**Recommandation.** Court terme (S) :
- `dialog.setCanceledOnTouchOutside(false)` et `setCancelable(false)` ;
- un drapeau `dirty`, positionné par des TextWatcher et les listeners de Spinner ;
- le bouton Annuler et le retour demandent « Abandonner la saisie ? » si le formulaire est modifié ;
- erreurs en ligne : un bandeau Tone.ERROR en tête de `form`, défilement jusqu'au champ, `requestFocus()` et `HydriaFeedback.shake`.

Moyen terme : sortir l'éditeur du dialogue vers une vue plein écran, comme le formulaire de relevé, avec une barre « Enregistrer » fixe en bas.

### REP_PLAN-05 — « Marquer terminée » : bouton dominant, confirmation anonyme, aucune annulation, « Suite à donner » écrasée

- **Sévérité** : Majeur
- **Écran** : Réparations, carte d'intervention
- **Catégorie** : workflow · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** La maquette 2a prévoit un bouton teinté (fond sombre, texte cyan). Ici, le bouton est l'élément le plus saillant de chaque carte, en cyan plein sur 52 dp. La confirmation ne nomme ni l'ouvrage, ni l'activité, ni la date, alors que des dizaines de cartes identiques se suivent (60 « Fanarahamaso » sur Ankazondandy) : confirmer la mauvaise est plausible.

Après confirmation, la carte disparaît (si « terminées » est masqué) et rien ne permet d'annuler : pas de snackbar, l'action en attente n'est pas retirable, la réouverture serveur n'est pas exposée. Le serveur passe estvalide à True (« Validée ») et écrase le texte « Suite à donner ». Ni bilan ni photo ne sont proposés à ce moment.

Quand on affiche les terminées, toutes portent « part à la prochaine synchronisation », même celles synchronisées depuis des mois.

**Impact pour l'agent.** Clôtures erronées irréversibles depuis le terrain. Perte des consignes « Suite à donner ». Fausse information sur l'état de synchronisation.

**Preuve (version 2.11.0).** MainActivity.kt:3608-3610 `text = "✓ Marquer terminée"; HydriaUi.primaryButton(this, HydriaColors.cyan)` et l.3614 `.setMessage("Marquer cette intervention comme terminée ?")`. Backend views_reparations_apis.py:1411-1414 `estvalide = True; statut = 'termine'; suiteadonner = 'Termine'`. L'endpoint `api_marquer_reparation_non_terminee` (l.1441) n'est pas utilisé par l'app. « Supprimer de la file » n'existe qu'en cas d'erreur (MainActivity.kt:4540-4558). l.3603-3606 : « Terminée · part à la prochaine synchronisation » pour toute réparation terminée. Captures 07/08 : cartes « Fanarahamaso · Normale » identiques et consécutives, chacune avec un bouton cyan plein.

**Vérification sur 2.12.0.** MainActivity.kt:4249-4266 `text = "✓ Marquer terminée"; HydriaUi.primaryButton(this, HydriaColors.cyan)` … `.setMessage("Marquer cette intervention comme terminée ?")` … `matchWrap(52, top = 12)` ; MainActivity.kt:4241-4243 « Terminée · part à la prochaine synchronisation » pour toute réparation terminée ; views_reparations_apis.py:1411-1413 `estvalide = True; statut = 'termine'; suiteadonner = 'Termine'` ; aucune référence Android à `non-terminee` (grep vide). — Inchangé : bouton cyan plein de 52 dp, confirmation anonyme (ni ouvrage, ni activité, ni date), aucune annulation après coup (pas de snackbar, la réouverture serveur api_marquer_reparation_non_terminee n'est pas appelée par l'app), « Suite à donner » écrasée par « Termine », libellé « part à la prochaine synchronisation » affiché même pour des réparations synchronisées depuis longtemps. Nuance : une réparation terminée reste complétable (photos, date, employé, remarque via addRepairExtraButtons), mais cela ne remplace pas une annulation.

**Recommandation.** - Message explicite : « Terminer « Fanarahamaso » sur Ankazondandy (prévue le 02/03/2026) ? ».
- Bouton en style tonal : `secondaryButton(active = true)`, ou un nouveau `HydriaUi.tonalButton`.
- Après confirmation, bandeau de 6 s « Réparation terminée · Annuler » qui appelle `store.remove(local_uuid)` tant que l'action n'est pas partie.
- Proposer « + photo / bilan » dans le dialogue.
- Distinguer « part à la prochaine synchronisation » (en attente) de « Terminée le JJ/MM » (synchronisée).
- Serveur : ne plus écraser une valeur `suiteadonner` non vide, et exposer une action « Rouvrir » sur les cartes terminées.

### REP_PLAN-06 — Liste Réparations : en-tête envahissant, 3 boutons pleine largeur par carte, groupes entièrement dépliés, aucune recherche

- **Sévérité** : Majeur
- **Écran** : Réparations (liste)
- **Catégorie** : ergonomie · **Effort** : M
- **Statut** : Partiellement corrigé en 2.12.0

**Constat.** Le handoff (README §4) prévoyait des chips Échues / Hors périmètre / Terminées, des sections « EN RETARD » et « SYNCHRONISATION EN ATTENTE », et une seule action par carte. L'implémentation empile à la place deux interrupteurs, des filtres géographiques, des groupes par ouvrage entièrement dépliés et trois boutons pleine largeur par carte. « Photo » et « Modifier » ont été ajoutés après le handoff. Quand toutes les priorités valent « Normale », le tri « les plus critiques en premier » devient « les plus anciennes en premier » : des tâches de routine non clôturées depuis mars monopolisent le haut de la liste. Ni recherche par ouvrage ou activité, ni filtre « en retard » ou « aujourd'hui ». Le libellé « 1 détail(s) » est du jargon interne.

**Impact pour l'agent.** Impossible de retrouver vite la réparation du jour. Défilement interminable, fatigue, risque de traiter de l'obsolète au lieu de l'urgent.

**Preuve (version 2.11.0).** MainActivity.kt:3417-3446 : bouton 54 dp, carte « OPTIONS D'AFFICHAGE » à 2 SwitchCompat, résumé de périmètre et bouton de filtres de 50 dp, tous avant la liste. l.3499-3502 : toutes les réparations du groupe sont rendues dépliées. l.3608-3635 : trois Button (52, 48 et 48 dp). RepairOverview.kt:21-29 : tri par criticité maximale, puis date minimale. Capture 07 : la 1re carte commence à y≈1065 sur 1445 px. Capture 08 : une carte fait ≈460 px, dont ≈275 px de boutons. « 60 INTERVENTIONS » sur Ankazondandy, soit ≈60 × 480 px ≈ 29 000 px (≈23 écrans) avant le 2e ouvrage.

**Vérification sur 2.12.0.** Corrigé en partie : MainActivity.kt:5009-5028 champ « Rechercher un ouvrage… » (PlanningViewModel.kt `setQuery`, filtre `query`). Intact : MainActivity.kt:4054-4081 bouton 54 dp + carte « OPTIONS D’AFFICHAGE » à 2 SwitchCompat ; 4029-4030 résumé de périmètre + bouton de filtres 50 dp (5027-5029) ; 4136-4139 tous les groupes entièrement dépliés ; 4249-4283 trois Button (52, 48, 48 dp) par carte ; 4225 `"$it détail(s)"` ; RepairOverview.kt:19-30 tri criticité puis date minimale. — Une recherche libre par nom d'ouvrage a été ajoutée (2.11.x/2.12), toujours visible hors du panneau de filtres : c'est le seul point corrigé. L'en-tête reste envahissant, les groupes ne sont pas repliables, chaque carte garde trois boutons pleine largeur, le tri « les plus anciennes en premier » quand les priorités sont toutes « Normale » est inchangé, il n'y a toujours ni filtre « en retard » ni « aujourd'hui », et « détail(s) » reste du jargon.

**Recommandation.** 1. Remplacer la carte d'options par une rangée de `HydriaUi.chip` (Échues n · Aujourd'hui · Hors périmètre · Terminées) et un champ de recherche (AutocompleteMatch sur ouvrage et activité). Les filtres géographiques passent dans le panneau Filtres.
2. Carte : un seul bouton tonal « ✓ Terminer », plus un bouton icône ⋮ de 48 dp ouvrant Photo / Modifier, ou deux boutons-icônes côte à côte.
3. Replier les groupes : afficher les 2 plus urgentes, puis « Voir les 58 autres » au toucher. Calculer cet aperçu dans RepairOverview (`group.preview`).
4. Tri : à criticité égale, faire remonter les échéances proches. Isoler les retards de plus de 90 jours dans une section « Anciennes non clôturées » à trier.

### REP_PLAN-07 — Reconstruction complète et synchrone de la liste : voile au changement d'onglet, figeages, défilement perdu

- **Sévérité** : Majeur
- **Écran** : Réparations (et Planning) ; changement d'onglet
- **Catégorie** : performance percue · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Cela explique l'observation 5 : le voile couvre la construction synchrone de milliers de vues sur un téléphone d'entrée de gamme. Il y a plus pénalisant : après « Terminer » en ligne, l'écran est reconstruit deux fois (immédiatement, puis après la synchro), chaque fois sans voile, donc l'interface fige plusieurs secondes. Le ScrollView neuf repart en haut : l'agent perd sa place dans une liste de 337 éléments après chaque clôture ou chaque bascule d'option. L'agenda Planning est reconstruit de même après chaque synchro automatique.

**Impact pour l'agent.** Application perçue comme lente ou plantée. Retour en haut de liste après chaque action, donc défilement à recommencer.

**Preuve (version 2.11.0).** MainActivity.kt:517-527 `withScreenTransition` (voile puis `post { block() }`), appelé l.747. renderRepairs construit toutes les vues en une fois (l.3465-3505 : ≈15 vues et 3 Button par réparation, soit ≈337 × 17 ≈ 5 700 vues) dans un ScrollView neuf (l.3507 `content.addView(scroll(page))`). `renderCurrentScreen()` est appelé directement, sans voile, après « Terminer » (l.3621), après chaque interrupteur (l.3430, l.3441) et en fin de synchro (l.919). Capture 03_reparations : voile et spinner central.

**Vérification sur 2.12.0.** MainActivity.kt:678-688 withScreenTransition (voile puis `loadingOverlay.post { block() }`), utilisé l.908 (onglets) ; renderRepairs MainActivity.kt:4102-4141 construit toutes les vues d'un coup puis `content.addView(scroll(page))` l.4144 ; scroll() l.5528 crée un ScrollView neuf ; renderCurrentScreen() direct sans voile après « Terminer » (l.4262), les interrupteurs (l.4067, 4078) et en fin de synchro (l.1091) ; aucune restauration de scrollY (grep vide hors listener agenda). — Inchangé : liste entièrement reconstruite de façon synchrone (pas de RecyclerView ni de pagination), deux reconstructions après « Terminer » en ligne (immédiate puis après synchro), position de défilement perdue après chaque clôture, bascule d'option ou synchro. Seule la nouvelle recherche (l.5014-5017) ne reconstruit que la zone de résultats, ce qui n'atténue pas le défaut général.

**Recommandation.** - Mémoriser `scrollY` par Screen avant `content.removeAllViews()` et le restaurer dans `post {}`.
- Après « Terminer », mettre la carte à jour sur place (alpha, remplacement des actions) au lieu d'appeler renderCurrentScreen.
- Rendu paresseux : 20 groupes, puis ajout par paquets en fin de défilement. À terme, RecyclerView avec un ViewHolder qui réutilise repairActivityCard.
- Ne pas reconstruire après une synchro si la réponse est `not_modified` et que la file n'a pas changé.

### REP_PLAN-08 — Planning : en-tête fixe (titre, carte de pointage, bouton) qui occupe la moitié de l'écran

- **Sévérité** : Majeur
- **Écran** : Planning (agenda)
- **Catégorie** : ergonomie · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** Le titre, le sous-titre, la carte « POINTAGE DU JOUR » (avec son bouton de 50 dp) et le bouton « Nouveau planning » (54 dp) sont hors du ScrollView. La bande de jours suit. L'agenda ne dispose que d'environ 615 px. Le résumé de périmètre, « Afficher les filtres » et le compteur s'y ajoutent : on voit à peine une carte d'activité au premier écran. La maquette 2a prévoit un simple bouton « + » à côté du titre, la bande de jours directement en dessous.

**Impact pour l'agent.** Agenda lu par un trou de serrure. Défilement constant, et la bande de jours est la seule partie utile du haut de l'écran.

**Preuve (version 2.11.0).** MainActivity.kt:3650-3657 `screen.addView(vertical(padding = 18).apply { addView(title(…)); addView(subtitle(…)); addView(planningPointageCard()…); addView(primaryButton("Nouveau planning")…, matchWrap(54, top = 10)) }, matchWrap())`, puis la bande (l.3670). Seul `planningScroll` défile (l.3674, poids 1). Capture 04 : bloc fixe de y≈195 à ≈830 px sur ≈1 250 px utiles ; 1re carte vers y≈1190.

**Vérification sur 2.12.0.** MainActivity.kt:4295-4303 `screen.addView(vertical(padding = 18).apply { addView(title("Agenda terrain")); addView(subtitle(…)); addView(planningPointageCard(), matchWrap(top = 2)); addView(primaryButton("Nouveau planning")…, matchWrap(54, top = 10)) }, matchWrap())` puis bande de jours (dateScroller) ; seul `planningScroll` (poids 1) défile ; le bouton du pointage mesure 50 dp (l.4568). — Bloc d'en-tête toujours hors du ScrollView : titre, sous-titre, carte POINTAGE DU JOUR avec bouton, bouton « Nouveau planning » de 54 dp, puis bande de jours. La zone d'agenda reste réduite ; la nouvelle recherche, le résumé de périmètre et le bouton de filtres se trouvent dans le corps défilant (addSharedFilters(body, …)) et réduisent encore la place utile au premier écran.

**Recommandation.** - Déplacer titre, sous-titre, carte de pointage et bouton dans `body`, la partie qui défile ; seule la bande de jours reste collée en haut.
- Remplacer le bouton pleine largeur par un bouton icône « + » de 48 dp dans la ligne de titre, comme sur la maquette 2a.
- Réduire la carte de pointage à une ligne d'état cliquable quand aucun créneau n'est en cours.
- Ranger « Périmètre affiché… » dans le panneau des filtres.

### REP_PLAN-09 — Pointage du jour : « Aucun planning aujourd'hui » affiché à côté de « 8 RDV » le même jour

- **Sévérité** : Majeur
- **Écran** : Planning, carte POINTAGE DU JOUR
- **Catégorie** : coherence · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** La carte parle implicitement des plannings de l'agent, alors que l'agenda montre par défaut toute l'équipe (base et subordonnés). L'agent lit « aucun planning aujourd'hui, ajoutez-le » juste au-dessus de 8 rendez-vous du jour. Le message l'invite à créer un planning, qui sera le plus souvent un doublon. Rien ne distingue non plus ses propres cartes de celles des collègues.

**Impact pour l'agent.** Confusion sur « ce que je dois faire aujourd'hui », créations en double, pointage impossible faute de comprendre la condition.

**Preuve (version 2.11.0).** MainActivity.kt:3907-3908 `"Aucun planning aujourd'hui : ajoutez-le pour pouvoir pointer."`, alimenté par `PointageStore.cachedToday` (plannings de l'agent connecté, l.3874). L'agenda filtre par défaut sur « Tous les employés » (PlanningViewModel.kt:102 ; l.3715). Capture 04 : le même écran montre « LUNDI 12 octobre 2026 · 8 RDV » (Retour d'avance · Équipe : RODIN).

**Vérification sur 2.12.0.** MainActivity.kt:4552-4553 `lines.isEmpty() -> "Aucun planning aujourd'hui : ajoutez-le pour pouvoir pointer."` alimenté par PointageStore.cachedToday (l.4519) ; PlanningViewModel.kt:116 `options(…, "Tous les employés")` avec employeeId = "" par défaut (l.8-9) ; en-tête de jour `"${dayPlannings.size} RDV"` (MainActivity.kt:4404). — Inchangé : la carte parle des plannings de l'agent connecté alors que l'agenda affiche par défaut toute l'équipe (base et subordonnés), sans signe distinguant les cartes de l'agent de celles des collègues (seulement « Équipe : nom »). Le message peut donc contredire « N RDV » juste en dessous et pousse à créer un doublon. Niveau bas de la catégorie majeur.

**Recommandation.** - Libellé : « Aucun planning à votre nom aujourd'hui (8 RDV pour l'équipe) ».
- Bouton « Ajouter mon planning du jour » qui ouvre l'éditeur avec l'agent et la date du jour présélectionnés.
- Dans l'agenda, filtre employé par défaut sur l'agent (via `employe_id`, cf. REP_PLAN-01) ou chip « Moi / Équipe ».
- Marquer les cartes de l'agent (badge « Moi »).

### REP_PLAN-10 — Date saisie en texte libre AAAA-MM-JJ, contrôle syntaxique seulement

- **Sévérité** : Majeur
- **Écran** : Éditeur réparation / planning, champ Date
- **Catégorie** : ergonomie · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** Le champ est un EditText texte libre au format ISO, avec clavier alphabétique. « 2026-02-30 » ou « 2026-13-01 » passent la validation client et sont mis en file hors ligne. Le serveur les refuse à la synchro, des heures plus tard, et l'erreur n'apparaît que dans le centre de synchronisation, loin du contexte. Une inversion jour/mois plausible (« 2026-03-02 » au lieu de « 2026-02-03 ») n'est pas détectée. Le format diffère de toutes les dates affichées dans l'app.

**Impact pour l'agent.** Fautes de date, actions bloquées en file, interventions planifiées le mauvais jour.

**Preuve (version 2.11.0).** MainActivity.kt:4017-4020 `field("Date (AAAA-MM-JJ)").apply { setText(… ?: SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())) }`, libellé « Date » l.4187. Validation par motif seulement : PlanningViewModel.kt:29 et RepairFormRules.kt:31 `matches(Regex("\\d{4}-\\d{2}-\\d{2}"))`. Le serveur rejette les dates impossibles (views_preparation_tournee.py:1100-1101). Ailleurs, les dates s'affichent « 02/03/2026 » (l.3569) ou « 12 octobre 2026 » (l.3755).

**Vérification sur 2.12.0.** MainActivity.kt:4662-4665 `field("Date (AAAA-MM-JJ)").apply { setText(… ?: SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())) }` (EditText mono-ligne, aucun inputType ni DatePicker) ; PlanningViewModel.kt:32 et RepairFormRules.kt:31 `matches(Regex("\\d{4}-\\d{2}-\\d{2}"))` ; views_preparation_tournee.py (rejet serveur des dates impossibles) ; centre de synchro MainActivity.kt:5282-5296 : une action en erreur ne peut qu'être supprimée. — Inchangé : champ texte libre au format ISO, contrôle purement syntaxique (« 2026-02-30 » ou « 2026-13-01 » passent), rejet seulement à la synchro, et l'entrée en erreur n'est pas corrigeable depuis le centre de synchro (« Supprimer de la file » uniquement). Le format reste différent des dates affichées (dd/MM/yyyy, « 12 octobre 2026 »).

**Recommandation.** - Rendre le champ non saisissable (`isFocusable = false`) et ouvrir un `DatePickerDialog` au toucher, avec la date existante ou celle du jour.
- Afficher « lundi 12 octobre 2026 » et conserver l'ISO en interne.
- Dans PlanningFormRules.validate (commonMain), remplacer le motif par `runCatching { LocalDate.parse(date) }` ; RepairFormRules s'en sert déjà via la validation de base.
- Option : avertir si la date est à plus de 30 jours dans le passé.

### REP_PLAN-11 — Chiffre de retard : signe ambigu, colonne qui déborde, libellés à contraste insuffisant, statut « En cours » trompeur

- **Sévérité** : Majeur
- **Écran** : Réparations, colonne de retard des cartes
- **Catégorie** : rendu donnees · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** Quatre problèmes :
1. Signe : « -224 » veut dire 224 jours de retard, alors qu'une échéance future s'affiche « 5 ». C'est l'inverse de la convention « J-5 » (5 jours avant), et rien n'indique « retard ». Le signe vient de la maquette (« -9 »), c'est un choix assumé, mais il n'est pas légendé.
2. Largeur : à l'échelle de police 1,0, « -224 » mesure environ 82 px pour 78 px disponibles et passe à la ligne (« -22 / 4 »). C'est la même cause que les compteurs Terrain (observation 1) ; à 1,15-1,3, fréquent sur ces téléphones, tout nombre à 3 chiffres déborde.
3. Contraste : textMuted #5D7C88 sur #0E2029 ≈ 3,7:1 en sombre, et #7A929B sur blanc ≈ 3,3:1, sous les 4,5:1 requis en plein soleil.
4. Toutes les interventions en retard affichent « En cours · 02/03/2026 » alors que personne n'y travaille.

Nuance sur l'observation 12 : textSecondary #9FBAC4 sur la surface atteint ≈8,2:1, ce qui est conforme. Les boutons secondaires paraissent faibles à cause de leur taille (13 sp × 0,85 ≈ 11 sp) et d'un gris qui évoque l'état désactivé.

**Impact pour l'agent.** Mauvaise lecture du retard (urgence comprise à l'envers), chiffres coupés selon la taille de police, libellés invisibles au soleil.

**Preuve (version 2.11.0).** MainActivity.kt:3533-3539 `overdue > 0 -> "-$overdue"; else -> (-overdue).toString()` dans `LayoutParams(dp(46), WRAP_CONTENT)` (l.3557), en mono 22 sp. « JOURS » en 9,5 sp `textMuted` (l.3551-3555) ; la couleur du futur est aussi textMuted (l.3547). Backend l.328 `'Planifiée' if date_mg > date_reference else 'En cours'`. Capture 08 : « -224 » occupe ≈70 px sur 78 px de colonne (46 dp × 1,7) à l'échelle 0,85.

**Vérification sur 2.12.0.** MainActivity.kt:4170-4176 `overdue > 0 -> "-$overdue"; else -> (-overdue).toString()` en mono 22 sp, colonne `LayoutParams(dp(46), WRAP_CONTENT)` l.4194 ; « JOURS » 9,5 sp textMuted l.4187-4193 ; res/values-night/colors.xml `hydria_text_muted #5D7C88` (3,74:1 sur #0E2029) et values/colors.xml `#7A929B` (3,27:1 sur blanc) ; views_preparation_tournee.py:329 `'Planifiée' if date_mg > date_reference else 'En cours'`. — Les quatre points subsistent. Signe « -224 » non légendé, inverse de la convention « J-5 ». Largeur : 4 caractères en Roboto Mono 22 sp font environ 50 dp (0,6 em par caractère moins l'espacement) pour 46 dp : tout retard à 3 chiffres passe à la ligne. Contrastes de textMuted inchangés et sous 4,5:1. Toute intervention en retard affiche « En cours · date ».

**Recommandation.** - Colonne en `wrap_content` avec `minWidth = dp(46)`, `maxLines = 1`, et autosize 14-22 sp via TextViewCompat.
- Libellés calculés dans le module partagé (`RepairDetails.overdueLabel`) : « 224 j » avec la légende « RETARD » en couleur d'erreur, « dans 5 j » pour le futur, « AUJ. » pour le jour même.
- Réserver textMuted au décoratif : textSecondary pour « JOURS » et les jours de week-end.
- Si le retard est positif, afficher « En retard · prévue le 02/03/2026 » au lieu du « En cours » du serveur.

### REP_PLAN-12 — Textes en dur non traduits en malgache, pluriels « (s) », coquilles et doublons de noms

- **Sévérité** : Majeur
- **Écran** : Réparations, Planning, éditeur
- **Catégorie** : i18n · **Effort** : L
- **Statut** : Vérifié en 2.12.0

**Constat.** Le domaine ne peut pas s'afficher en malgache malgré values-mg/strings.xml. Le partagé impose aussi « LUNDI », « octobre ». Les compteurs utilisent le motif « (s) » au lieu de vrais pluriels, et on trouve du jargon interne : « détail(s) », « RDV », « Préchargez une tournée ». Il y a une faute d'accord (« Réparation enregistré »), et le nom de l'assigné est répété dans la liste des participants.

**Impact pour l'agent.** Compréhension réduite pour les agents plus à l'aise en malgache ou peu lettrés, impression d'outil inachevé.

**Preuve (version 2.11.0).** Tous les libellés sont des littéraux : MainActivity.kt:3415-3416, 3609, 3614, 3651-3652, 4196-4198… res/values/strings.xml (174 lignes) ne contient aucune clé réparation ou planning ; MainActivity n'appelle `getString(R.string…)` que 2 fois. Côté partagé, PlanningAgenda.kt:24-27 fige les jours et mois en français. Exemples : l.4277 `"Réparation enregistré…"` ; l.3588 `"$it détail(s)"` ; l.3577-3578 `listOf(repair.optString("assigne_a"), repair.optString("participants"))` qui donne « Équipe : LANJA · LANJA, NOELA » (capture 07).

**Vérification sur 2.12.0.** MainActivity.kt n'appelle `getString(R.string…)` que l.5092 et 5112 ; res/values/strings.xml ne contient aucune clé réparation/planning ; PlanningAgenda.kt (shared) liste figée `weekdays`, `shortWeekdays`, `months` en français ; MainActivity.kt:4924 `"Réparation enregistré…"`, 4225 `"$it détail(s)"`, 4404 `"… RDV"`, 4044/4289 « Préchargez une tournée… », 4214-4216 `listOf(assigne_a, participants)` sans dédoublonnage. — Inchangé : tous les textes de ces écrans sont des littéraux français (donc values-mg/strings.xml sans effet), jours et mois figés dans le module partagé, pluriels en « (s) », jargon (« détail(s) », « RDV »), faute d'accord « Réparation enregistré », et l'assigné répété dans la liste des participants (« Équipe : LANJA · LANJA, NOELA »).

**Recommandation.** - Extraire les chaînes dans strings.xml et values-mg, avec `<plurals>` et getQuantityString pour les compteurs.
- PlanningAgenda : recevoir les tables de jours et de mois de la plateforme, ou d'une table FR/MG en commonMain.
- Corriger « enregistrée ».
- Retirer de `participants` les noms déjà présents dans `assigne_a` (même chose dans planningAgendaCard).
- Remplacer « détail(s) » par « ligne(s) de matériel / avance ».

### REP_PLAN-13 — Bande de jours : jours vides absents, ni mois ni repère « aujourd'hui », puces de charge toutes orange, agenda tout empilé

- **Sévérité** : Mineur
- **Écran** : Planning, bande de jours et agenda
- **Catégorie** : rendu donnees · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Un jour sans RDV n'a pas de case : deux jours non consécutifs paraissent adjacents. Au passage d'un mois, rien ne l'indique. Aujourd'hui n'est plus repérable dès qu'on sélectionne un autre jour. La puce passe à l'orange dès 3 RDV, donc presque partout : elle ne dit plus rien et banalise la couleur d'alerte. L'agenda empile les 94 plannings au lieu de montrer la journée sélectionnée comme sur la maquette. L'absence de colonne d'heures est en revanche justifiée : l'API mobile n'envoie que la date (views_preparation_tournee.py:264).

**Impact pour l'agent.** Lecture temporelle approximative (trous, mois), signal de charge inutile, longue liste à parcourir.

**Preuve (version 2.11.0).** MainActivity.kt:3728-3746 : une case par `agenda.days`, donc seulement les jours qui ont des RDV (PlanningAgenda.kt:63 `groupBy { dateKey(it.date) }`). l.3802-3806 `count >= 3 -> HydriaColors.warning`. l.3819-3834 : seul l'état sélectionné est stylé, aucun repère « aujourd'hui ». La case ne porte que l'abréviation et le numéro (l.3787-3801), pas le mois. l.3748-3770 : toutes les journées sont empilées. README §5 : agenda d'une journée et colonne d'heures. Capture 04 : 7 puces orange identiques.

**Vérification sur 2.12.0.** MainActivity.kt:4373 `agenda.days.forEach` (une case par jour portant des RDV) ; planningDayCell MainActivity.kt:4447-4451 `count >= 3 -> warning; count >= 1 -> cyan` ; restyle l.4464-4478 (seul l'état sélectionné est stylé, aucune marque « aujourd'hui », la case n'affiche que abréviation + numéro) ; sections de tous les jours empilées l.4393-4415. — Inchangé : les jours sans RDV n'ont pas de case, aucun repère de mois ni d'aujourd'hui, puce orange dès 3 RDV (seuil peu discriminant), agenda empilé au lieu d'une vue de la journée sélectionnée. L'absence de colonne d'heures reste justifiée (l'API n'envoie que la date).

**Recommandation.** - Générer des jours continus, d'aujourd'hui à +14 j ou du minimum au maximum : les jours vides sont désaturés et non cliquables.
- Surtitre du mois (« OCT ») sur le premier jour de chaque mois.
- Anneau cyan permanent de 2 dp sur aujourd'hui.
- Charge en 1 à 3 points neutres, l'orange étant réservé à la surcharge (par ex. 5 RDV ou plus).
- Bascule « Jour / Liste » pour n'afficher que la journée sélectionnée.

### REP_PLAN-14 — Badge de l'onglet Réparations : « 99+ » rogné en « 99 », sens incohérent (« en retard » vs toutes à faire)

- **Sévérité** : Mineur
- **Écran** : Barre d'onglets, onglet Réparations
- **Catégorie** : feedback etats · **Effort** : S
- **Statut** : Vérifié en 2.12.0

**Constat.** Le badge affiche « 99 », lu comme un nombre exact, alors que l'écran annonce « 337 réparation(s) à faire ». Il chevauche l'icône et reste allumé en permanence : ce n'est plus un signal. Le lecteur d'écran annonce des réparations « en retard » qui n'en sont pas.

**Impact pour l'agent.** Indicateur ignoré ou mal compris ; l'urgence réelle n'est pas mise en avant.

**Preuve (version 2.11.0).** MainActivity.kt:713-717 : badge dans un `FrameLayout` dimensionné sur l'icône de 22 dp, avec `marginEnd = dp(-8)`. La partie qui dépasse est coupée (clipChildren par défaut), « 99+ » devient « 99 ». l.821 `if (repairsBadge > 99) "99+"`. l.826-831 : compte toutes les réparations non terminées du périmètre, alors que l'accessibilité annonce `", $repairsBadge en retard"` (l.813). Maquette 2a : badge « 2 » = échues. Captures 04/07.

**Vérification sur 2.12.0.** MainActivity.kt:866-889 badge dans `iconWrap` (FrameLayout, WRAP_CONTENT calé sur l'icône de 22 dp) avec `marginEnd = dp(-8)` ; aucun clipChildren=false dans le projet (grep vide) ; l.982 et 5504 `if (count > 99) "99+"` ; repairsBadgeCount l.987-994 compte toutes les réparations non terminées du périmètre ; l.974 accessibilité `", $repairsBadge en retard"`. — Inchangé : la partie du badge qui dépasse l'icône est rognée par le parent (« 99+ » devient « 99 »), le compteur désigne toutes les réparations à faire (pas les échues) et reste allumé en permanence, et le lecteur d'écran annonce « en retard » à tort. Rendu non vérifié sur appareil, conclusion tirée du code resté identique.

**Recommandation.** - Compter uniquement les réparations échues (`RepairRules.overdueDays(repair) > 0`) ou critiques, en cohérence avec le texte d'accessibilité.
- `clipChildren = false` sur `iconWrap` et sur le conteneur (ou une marge de fin sur iconWrap), avec le badge ancré en haut à droite par translation, pour que « 99+ » reste entier.

### REP_PLAN-15 — Finitions : coins parasites des cartes accentuées, listes sans flèche, champ Remarque non stylé, thème de dialogue ignoré

- **Sévérité** : Cosmétique
- **Écran** : Cartes Réparations / Planning, éditeur, filtres
- **Catégorie** : esthetique · **Effort** : S
- **Statut** : Vérifié en 2.12.0

**Constat.** La barre colorée sous chaque carte accentuée a des coins droits carrés : la surface arrondie ne les recouvre pas, d'où les triangles colorés en haut et en bas à droite (cause de l'observation 2). Dans l'éditeur, certaines listes déroulantes ont une flèche (cascade) et d'autres non (employé, cible, statut, priorité, filtres) : ces dernières ressemblent à des cases inertes. La Remarque garde le style Material par défaut au milieu de champs Hydria. Les dialogues n'héritent ni de la surface élevée ni de la police définies dans l'overlay. L'emoji d'appareil photo détonne à côté des icônes vectorielles.

**Impact pour l'agent.** Impression de finition inégale ; affordance des listes déroulantes incohérente dans un même formulaire.

**Preuve (version 2.11.0).** HydriaVisuals.kt:262-270 : `bar.cornerRadii = floatArrayOf(radius, radius, 0f, 0f, 0f, 0f, radius, radius)` (coins droits carrés), sous un `body` arrondi décalé de 3 dp à gauche (`setLayerInset(1, dpi(3f), 0, 0, 0)`) : les coins droits de la barre débordent. HydriaVisuals.kt:514-517 : `styleSpinner` remplace le fond, donc plus de flèche. Seule HydriaActivityCascade.kt:108-118 redessine « ▾ » ; employeeSpinner, targetSpinner, statusSpinner, prioritySpinner et les 4 filtres (MainActivity.kt:4292-4295) n'en ont pas. MainActivity.kt:4023-4029 : `EditText(this)` sans `styleInput`. themes.xml définit `materialAlertDialogTheme`, mais le code utilise `androidx.appcompat.app.AlertDialog` (l.38), donc l'overlay Hydria n'est pas appliqué. Emoji « 📷 » (l.3627). Captures 07/08 : triangles cyan aux coins droits.

**Vérification sur 2.12.0.** HydriaVisuals.kt:262-270 `cornerRadii = floatArrayOf(radius, radius, 0f, 0f, 0f, 0f, radius, radius)` sous un body inset de 3 dp (coins droits de la barre non recouverts) ; HydriaVisuals.kt:514-517 styleSpinner sans flèche (flèche « ▾ » redessinée seulement dans HydriaActivityCascade.kt) ; MainActivity.kt:4668 `val remarkField = EditText(this)` sans styleInput ; MainActivity.kt:38 `import androidx.appcompat.app.AlertDialog` alors que themes.xml:25 ne définit que `materialAlertDialogTheme` ; MainActivity.kt:4275 `"📷 Ajouter des photos"`. — Les cinq finitions sont inchangées : triangles colorés aux coins droits des cartes accentuées, listes déroulantes sans flèche (employé, cible, statut, priorité, filtres), champ Remarque au style Material par défaut, overlay de dialogue Hydria non appliqué avec AlertDialog appcompat, emoji d'appareil photo.

**Recommandation.** - Barre : `cornerRadius = radius` sur les quatre coins, pour que le corps la masque à droite.
- Factoriser l'enveloppe à flèche de HydriaActivityCascade.addLevel en `HydriaUi.dropdown(spinner)` et l'utiliser partout.
- Appliquer `HydriaUi.styleInput` à la Remarque.
- Passer à `MaterialAlertDialogBuilder`, ou déclarer `alertDialogTheme` dans Theme.HydriaApp.
- Remplacer « 📷 » par une icône vectorielle `ic_camera`.


## Pointage

_Audit initial sur la version 2.11.0._

**Synthèse du domaine.** Le pointage repose sur une base technique solide : le serveur fait foi, le mode hors ligne prend le relais avec un contrôle local, les envois sont idempotents, la position simulée est détectée et le bouton reste dans une barre fixe dont le libellé dit pourquoi on ne peut pas pointer. Le problème principal n'est pas visuel, il est dans le parcours. La case « prévu », placée juste à côté du statut du créneau en cours, ressemble à l'action de pointer, et le serveur l'initialise à faux. Comme elle n'est déclarable que pendant le créneau lui-même, les rappels ne se déclenchent presque jamais, un créneau non pointé n'est jamais compté « manqué » et les compteurs d'équipe affichent mécaniquement « 0/0 ». Le serveur ne cochant « prévu » qu'au moment d'un pointage validé, le ratio vaut 0/0 ou n/n. Deux trous du mode hors ligne touchent directement la paie et les données : (1) un pointage mis en file puis refusé à la synchronisation (refus HTTP 422) disparaît sans message, alors que l'écran l'avait affiché en vert ; (2) un planning ajouté hors ligne n'apparaît pas, ce qui pousse à le recréer et fabrique des doublons. Sur l'observation 6 : l'écran est une Activity séparée lancée par un faux onglet, sans barre de navigation, avec un en-tête et une pastille de synchro différents. La carte suit la connectivité et non le thème : style Liberty clair en ligne, fond noir sans routes hors ligne. Le bouton grisé obtient son effet par une transparence de 0,45 sur le cyan principal, soit environ 3:1 de contraste pour la seule information utile (« possible à 15h »). Sans planning, ce bouton redevient actif à 15h alors que le serveur refusera. Gains rapides : distinguer visuellement les états du bouton, gérer les autorisations GPS avec un accès aux réglages, corriger le périmètre de la pastille de synchro et afficher un même résumé d'état sur l'accueil, la page Planning et l'onglet. La correction des coins colorés de accentedCard tient en une ligne. Les chantiers de fond sont le modèle « prévu » (décision produit + serveur), le journal des pointages avec reçu, le planning provisoire hors ligne et l'intégration de l'écran dans MainActivity.

**À préserver :**

- Le serveur fait foi (heure serveur en ligne) ; hors ligne, un verdict local mène à un refus net ou à une mise en file. L'agent n'est jamais bloqué par le réseau (PointageActivity.kt:657-697). Les envois sont idempotents grâce à local_uuid.
- Contrôles anti-fraude et de qualité avant l'envoi : position simulée (isMock), précision ≤ 100 m, position GPS de moins de 60 s (PointageActivity.kt:634-648).
- Le bouton principal reste dans une barre fixe en bas quel que soit le défilement (l.214-233). Son libellé explique la cause du blocage : prochain créneau, distance trop grande, pas de pointage pour ces plannings (l.517-524).
- La ligne de statut GPS est lisible : précision, distance au village le plus proche, verdict coloré (l.594-625).
- Les échecs de rafraîchissement sont décrits honnêtement : hors ligne, serveur injoignable, session expirée (401), accès refusé (403), erreur HTTP (PointageRules.refreshFailureNote). L'agent ne confond pas une panne avec le réseau.
- Si le téléphone n'a pas OpenGL ES 3, la carte est omise avec une note explicative au lieu d'un plantage natif (l.175-182). Les gestes de la carte restent utilisables dans le ScrollView (l.184-191).
- Rappels 100 % locaux (AlarmManager inexact, sans Firebase ni réseau), reprogrammés au redémarrage. Ils sont supprimés si le créneau est déjà fait ou passé, ou si les notifications sont coupées (PointageReminders).
- Un refus définitif du serveur (HTTP 422) n'est pas rejoué indéfiniment par la file de synchronisation (PointageSync.kt:26-30).
- La modification de planning depuis le pointage respecte la règle du serveur (planning validé : ni activité ni ouvrage modifiable) via les règles partagées PlanningFormRules.
- Retour sonore et haptique au succès et à l'échec. La liste de l'équipe est triée par nombre de pointages manqués.

### POINTAGE-02 — « Prévu » ne se déclare que pendant le créneau : rappels inertes et pointages manqués jamais comptés

- **Sévérité** : Critique
- **Écran** : Pointage, rappels, section « Mon équipe »
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Les trois indicateurs « prévu » valent faux par défaut. Le seul moyen de les régler n'apparaît que dans le créneau ouvert. Le calendrier de 8 jours qui alimente les rappels est donc presque vide : un créneau ne devient « prévu » qu'une fois pointé, quand le rappel n'a plus d'utilité. Un créneau jamais pointé reste « non_prevu » et n'est jamais classé « manqué ». Le ratio de l'équipe compare des créneaux pointés à des créneaux pointés : il vaut 0/0 ou n/n.

**Impact pour l'agent.** Les agents ne reçoivent pas de rappel. Les superviseurs lisent « Aucun pointage manqué » alors que des agents n'ont pas pointé : les données de présence sont mal lues et les absences ne sont pas suivies.

**Preuve (version 2.11.0).** PointageActivity.kt:302-303 `// seul le créneau de l'heure actuelle est affiché` puis `if (c.optString("type") != actuel?.type) continue` : hors créneau, aucune case n'est affichée. PointageReminders.kt:36-49 triggers ne programme que les créneaux où `day.optBoolean(creneau.type)` est vrai. backend services_pointage.py:286-289 `if not prevu: return 'non_prevu'` est évalué avant `'manque'`. :100-102 le serveur ne passe `prevu` à vrai qu'au moment d'un pointage validé. :374-375 nb_ok et nb_manques. Aucun autre écran, web ou mobile, n'écrit `prevu_*` (vérifié par grep). Capture 05 : « Aucun pointage manqué » et « 0/0 ».

**Vérification sur 2.12.0.** app/pointage/PointageActivity.kt:308-309 `// seul le créneau de l'heure actuelle est affiché` + `if (c.optString("type") != actuel?.type) continue` ; PointageReminders.kt:42 `if (!day.optBoolean(creneau.type)) return@forEach` ; backend services_pointage.py:286-287 `if not prevu: return 'non_prevu'` (avant 'manque') et :264-265 `setattr(pl, champ_prevu, True)` au seul pointage validé — Revérifié côté app et serveur : les trois `prevu_*` valent faux par défaut. Le seul écrivain hors pointage est l'API `declarer` (mobile_api_pointage.py:146), appelée seulement depuis la case visible pendant le créneau ouvert. Aucun autre écran web ou mobile n'écrit ces champs (grep sur py/html/js : aucun). `calendrier_prevus` omet donc presque tous les jours, les rappels ne partent pas, un créneau jamais pointé reste « non_prevu » et jamais « manque », et `nb_manques` reste à 0. Le défaut est structurel et neutralise deux fonctions livrées (rappels et suivi des manqués) : critique conservé. Le correctif est une décision produit puis serveur + app.

**Recommandation.** Décision produit, puis mise en œuvre. (1) Serveur : initialiser prevu_* à la création du planning selon l'activité (par exemple matin et après-midi pour une activité de terrain), ou considérer comme prévus par défaut les créneaux des plannings qui exigent un pointage. (2) Application : dans PointageActivity, afficher les trois créneaux de chaque planning, avec un interrupteur « prévu » modifiable tant que le créneau n'est pas terminé, et ajouter les mêmes interrupteurs dans showPlanningEditor. (3) Rappels : un jour qui a des plannings avec pointage mais aucun créneau prévu doit déclencher au minimum les rappels du matin et de l'après-midi.

### POINTAGE-03 — Un pointage hors ligne refusé plus tard disparaît sans explication, et aucun reçu n'est conservé

- **Sévérité** : Critique
- **Écran** : Pointage – zone de résultat et carte de planning
- **Catégorie** : feedback etats · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Le vert de réussite s'affiche avant toute validation. Quand le serveur refuse ensuite le pointage (distance, horaire, aucun planning), le refus est enregistré mais jamais montré. Le compteur d'attente retombe à zéro et la pastille indique « à jour ». L'écran ne conserve ni heure, ni distance, ni précision du pointage.

**Impact pour l'agent.** L'agent croit avoir pointé et le découvre au moment de la fiche d'indemnité du mois. Il n'a aucun reçu pour contester. Une session expirée est présentée à tort comme un problème de réseau.

**Preuve (version 2.11.0).** PointageSync.kt:26-30 `result.status == 422 -> PointageStore.resolve(uuid, PointageStore.REFUSE, …message…)` puis `HydriaApi.Result(200, … .put("success", true).put("refused", true))` : la file de synchronisation considère l'opération réussie. Le champ Entry.message (PointageStore.kt:21) n'est lu nulle part dans l'interface : seul PointageReminders.kt:98 filtre REFUSE. PointageActivity.kt:694-695 affiche « Pointage enregistré sur le téléphone. Il sera envoyé et validé… ». l.284-286 la carte passe en vert (SUCCESS) avec « ✓ Pointage enregistré sur ce planning », même pour un pointage seulement en file (markPointed appelé l.693). l.662-676 : une réponse 401 ou 500 alors que le réseau fonctionne bascule aussi vers la file, avec « dès que le réseau sera disponible ».

**Vérification sur 2.12.0.** app/pointage/PointageSync.kt:26-30 `result.status == 422 -> PointageStore.resolve(uuid, PointageStore.REFUSE, …)` puis `HydriaApi.Result(200, … .put("refused", true))` ; PointageStore.kt:21 Entry.message jamais lu par l'UI ; PointageActivity.kt:699 `creneau?.let { markPointed(null, … ) }` + :290-292 carte verte « ✓ Pointage enregistré sur ce planning » ; :668-695 un 401/500 en ligne bascule vers la file — Aucun correctif : `grep PointageStore.` montre que ni `message` ni le statut REFUSE ne sont affichés (seul PointageReminders.kt:98 filtre REFUSE). Après un refus à la synchro, le compteur retombe à 0 et la pastille indique « à jour ». Mitigation déjà présente en 2.11.0 et non citée : la ligne du créneau affiche « ⏳ En attente d'envoi » (pendingTypes l.305-310) et la zone de résultat est orange, donc seule la phrase verte du haut de carte est trompeuse. Le fond du constat (refus jamais montré, pas de reçu avec heure, distance, précision) reste vrai. La fréquence est réduite par le contrôle local avant mise en file, mais les refus non détectables localement (sans planning, village sans coordonnées) restent silencieux et touchent l'indemnité.

**Recommandation.** Ajouter un bloc « Mes pointages aujourd'hui » dans renderToday(), construit à partir de PointageStore.todayEntries(account). Chaque ligne porte un HydriaUi.badge (⏳ en attente / ✓ validé / ✗ refusé, avec le message du serveur) ainsi que l'heure de capture, la distance et la précision, à stocker dans Entry dès addPending. Mettre en évidence le planning en file avec le ton WARNING (« ⏳ Enregistré à 15:12 – en attente de validation ») et réserver SUCCESS aux pointages validés par le serveur. Dans la branche 422 de PointageSync.send, publier une notification « Pointage de 15:12 refusé : <motif> » qui ouvre le pointage. Dans onPointer, distinguer 401 et 5xx du hors ligne en réutilisant refreshFailureNote.

### POINTAGE-01 — La case « prévu » ressemble à l'action de pointer

- **Sévérité** : Majeur (initialement Critique)
- **Écran** : Pointage – carte de planning, ligne du créneau en cours
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Pendant un créneau, la seule ligne de la carte est une case native libellée « Après-midi  15h00-18h00 », suivie d'un statut « — ». Cocher la case n'enregistre aucun pointage GPS : elle envoie seulement une déclaration (`pointage_prevu`). Après un vrai pointage, l'application coche elle-même cette case, ce qui renforce l'idée que « case cochée = pointé ».

**Impact pour l'agent.** Un agent peu à l'aise avec le numérique coche la case, la voit cochée, croit avoir pointé et ne touche jamais le bouton du bas. Aucun pointage n'est validé : le créneau n'est pas indemnisé (calculer_fiche_indemnite ne paie que les pointages VALIDÉS). Décocher après un pointage envoie prévu=false au serveur.

**Preuve (version 2.11.0).** PointageActivity.kt:309-314 `CheckBox … text = "${c.optString("label")}  ${c.optString("fenetre")}"; isChecked = c.optBoolean("prevu")` : le mot « Prévu » n'existe que dans contentDescription (l.315). l.470-478 statutLabel ne traite pas "non_prevu" et affiche `else -> "—"`. backend apps/planning/models.py:194 `prevu_matinee = models.BooleanField(default=False)` : le cas par défaut est donc une case vide suivie de « — ». l.718 markPointed coche la case après un pointage. l.729-730 cocher pendant le créneau fait passer le statut à `a_venir` (« À venir »). Non visible sur la capture 05 (aucun planning) : déduction depuis le code.

**Vérification sur 2.12.0.** app/pointage/PointageActivity.kt:315-319 `CheckBox … text = "${c.optString("label")}  ${c.optString("fenetre")}" … isChecked = c.optBoolean("prevu")` ; :476-484 statutLabel sans cas "non_prevu" (`else -> "—"`) ; :724 markPointed `c.put("prevu", true)` ; backend apps/planning/models.py:194 `prevu_matinee … default=False` — Code inchangé depuis 2.11.0 (les numéros ont seulement glissé d'environ +6). La case native « prévu » reste la seule ligne du créneau en cours, le mot « Prévu » n'est que dans contentDescription, et le statut par défaut affiche « — ». Cocher envoie seulement `pointage_prevu` (declarePrevu l.731-740). Le serveur ne paie que les pointages validés (services_pointage.py:441, calculer_fiche_indemnite). Sévérité ramenée de critique à majeur : le gros bouton « Pointer ma position · après-midi » reste très visible en bas, et après avoir coché, le statut repasse à « À pointer maintenant » en orange après refresh, ce qui contredit « j'ai pointé ». Le risque de confusion et de perte d'indemnité subsiste.

**Recommandation.** Dans planningCard(), remplacer la CheckBox par une ligne de statut en lecture seule : un titre « APRÈS-MIDI · 15h–18h » (HydriaUi.overline) et un HydriaUi.badge au texte explicite (« À pointer maintenant », « ✓ Pointé à 15:12 », « ⏳ En attente d'envoi », « ✗ Manqué », « Non déclaré – vous pouvez pointer »). Ajouter "non_prevu" à statutLabel. Déplacer la déclaration des créneaux prévus dans un contrôle séparé, formulé en mots (« Je serai sur place : Matin / Après-midi / Nuit »), fait de HydriaUi.chip actifs ou inactifs, jamais placé à côté du statut du créneau en cours (voir POINTAGE-02).

### POINTAGE-04 — Planning ajouté hors ligne : l'écran affiche toujours « Aucun planning », d'où des doublons

- **Sévérité** : Majeur (initialement Critique)
- **Écran** : Pointage – dialogue « Ajouter un planning aujourd'hui »
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Hors ligne, le cas normal sur le terrain, le nouveau planning est seulement mis en file. L'écran continue d'inviter à l'ajouter, et le bouton principal reste sur « Pointage possible à 15h » comme s'il n'existait pas.

**Impact pour l'agent.** L'agent recommence l'ajout et N plannings identiques sont créés à la synchronisation. Il ne voit pas non plus son planning pour pointer.

**Preuve (version 2.11.0).** PointageActivity.kt:435 `store.enqueue("save_planning", …)` puis l.446 `else existing?.let { applyLocalPlanningEdit(…) }` : pour un nouveau planning (existing == null), rien n'est ajouté à today["plannings"]. l.449 affiche « Planning enregistré sur le téléphone… ». renderToday l.249-250 continue d'afficher « Aucun planning enregistré pour vous aujourd'hui. Ajoutez-le ci-dessous pour pouvoir pointer. » et le bouton « + Ajouter… » reste en place (l.264). l.426-428 : sans existingId, chaque envoi crée un nouveau planning. Même message visible sur la capture 05 (en ligne).

**Vérification sur 2.12.0.** app/pointage/PointageActivity.kt:441 `store.enqueue("save_planning", …)` ; :452 `else existing?.let { applyLocalPlanningEdit(…) }` (rien si existing == null) ; :454-455 « Planning enregistré sur le téléphone… » ; :255-256 « Aucun planning enregistré pour vous aujourd'hui. Ajoutez-le ci-dessous… » ; :270 bouton « + Ajouter » toujours présent — Code inchangé. Un nouveau planning créé hors ligne n'est pas inséré dans `today.plannings` : l'écran continue d'inviter à l'ajouter et le bouton principal ne le prend pas en compte. Côté serveur, `_save_mobile_planning` ne déduplique pas à la création (pas de local_uuid), donc chaque ajout répété crée un doublon. Sévérité ramenée de critique à majeur : le résultat orange « enregistré sur le téléphone » est affiché, ce qui limite la répétition, et l'impact est un doublon de données, pas une perte d'indemnité. La correction proposée (planning provisoire local_pending) reste pertinente.

**Recommandation.** Après la mise en file d'un nouveau planning, insérer dans today.plannings un objet JSON provisoire : planning_id = UUID local, libellés d'activité et d'ouvrage, villages tirés des références du snapshot quand ils existent, créneaux générés depuis PointageRules.CRENEAUX avec un statut calculé localement, local_pending=true. Appeler PointageStore.saveToday puis renderToday. Afficher un badge « En attente d'envoi » sur cette carte et masquer « Modifier » jusqu'à la synchronisation. Si un save_planning du jour est déjà en file, demander confirmation avant d'en ajouter un autre.

### POINTAGE-05 — L'onglet « Pointage » ouvre un écran hors de la navigation

- **Sévérité** : Majeur
- **Écran** : Barre du bas et rail tablette → PointageActivity
- **Catégorie** : coherence · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Le premier onglet n'est jamais sélectionné : le toucher ouvre un plein écran sans barre du bas, avec un autre en-tête (sans logo, sans Recherche, avec une pastille au sens différent) et une flèche de retour. Ouvert depuis un rappel, l'écran est la racine de la tâche : « retour » quitte l'application.

**Impact pour l'agent.** Le modèle « un onglet = une section » est cassé. Après avoir pointé, il faut revenir en arrière avant d'aller aux Relevés : une étape de plus, souvent d'une main en marchant. Depuis une notification, l'agent atterrit hors de l'application.

**Preuve (version 2.11.0).** MainActivity.kt:79-81 `// C'est un raccourci vers PointageActivity…, jamais un écran courant`. l.740-743 `if (screen == Screen.POINTAGE) { … openPointage() }`. l.754-756 `startActivity(Intent(this, …PointageActivity::class.java))`. l.815 l'élément est annoncé « Pointage, onglet ». PointageActivity.kt:154-166 en-tête propre avec `secondary("←") { finish() }` et aucune barre de navigation. PointageReminders.kt:120-123 la notification lance PointageActivity seule (FLAG_ACTIVITY_NEW_TASK). Passage de la capture 04 à la capture 05.

**Vérification sur 2.12.0.** app/MainActivity.kt:79-81 `// C'est un raccourci vers PointageActivity… jamais un écran courant` ; :635-637 et :901-903 `if (screen == Screen.POINTAGE) { … openPointage() }` ; :915-917 startActivity(PointageActivity) ; :1118 `Screen.POINTAGE -> Unit` ; pointage/PointageActivity.kt:163 `secondary("←") { finish() }` ; PointageReminders.kt:121 `Intent(…PointageActivity…).addFlags(FLAG_ACTIVITY_NEW_TASK)` ; AndroidManifest.xml:56-57 sans parentActivityName — Inchangé. L'onglet Pointage ouvre toujours une Activity plein écran sans barre du bas, avec son propre en-tête. Depuis la notification, l'écran est la racine de la tâche (aucun TaskStackBuilder, aucun parentActivityName dans le manifeste), donc « retour » quitte l'application.

**Recommandation.** Cible : afficher le pointage dans MainActivity comme les autres écrans. Extraire l'interface et la logique de PointageActivity dans une classe PointageScreen(activity, store) qui expose `view`, onResume, onPause et onDestroy, et transmet le cycle de vie de la MapView. L'appeler depuis renderCurrentScreen() pour Screen.POINTAGE et supprimer les cas particuliers l.474, 740 et 946. À court terme, si l'Activity est conservée : ne plus la présenter comme un onglet (la retirer de la barre et s'appuyer sur la carte de l'accueil et une action « Pointer » avec indicateur d'état). Pour la notification, utiliser un TaskStackBuilder avec MainActivity comme parent (parentActivityName dans le manifeste).

### POINTAGE-06 — Bouton principal grisé : information clé à ~3:1 de contraste, et fausse promesse sans planning

- **Sévérité** : Majeur
- **Écran** : Pointage – barre fixe du bas
- **Catégorie** : accessibilite · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** L'état désactivé garde l'identité du bouton principal, simplement estompée : il paraît actionnable mais terni. Le texte, qui porte la seule information « quand », est à environ 3:1, et la fin de la fenêtre (18h) n'apparaît pas. Sans planning, le bouton devient actif à 15h alors que le serveur refusera, et hors ligne le pointage partira en file puis sera refusé sans message (POINTAGE-03).

**Impact pour l'agent.** Message illisible au soleil, et ambiguïté entre « pas encore » et « bloqué ». L'agent sans planning est invité à pointer en vain.

**Preuve (version 2.11.0).** PointageActivity.kt:515-516 `pointButton.isEnabled = … ; pointButton.alpha = if (pointButton.isEnabled) 1f else 0.45f` appliqué sur HydriaUi.primaryButton (HydriaVisuals.kt:274-285 : fond cyan #55D9E7, texte onAccent #07151D). Superposés au fond backgroundDeep #050F14, on obtient un fond ≈ #296A73 et un texte ≈ #061218, soit un contraste ≈ 3,1:1 (calcul). l.520-521 libellé `"Pointage possible à ${it.debut.hour}h (${it.label.lowercase()})"`. l.514 sansPointage exige `length() > 0` : sans aucun planning, le bouton redevient actif à 15h. Capture 05 : « Pointage possible à 15h (après-midi) » sous la note « Aucun planning… ».

**Vérification sur 2.12.0.** app/pointage/PointageActivity.kt:520-522 `sansPointage = today?.optJSONArray("plannings")?.let { it.length() > 0 } == true && !pointageAttendu(today)` ; `pointButton.alpha = if (pointButton.isEnabled) 1f else 0.45f` ; :526-527 `"Pointage possible à ${it.debut.hour}h (${it.label.lowercase()})"` — Inchangé. Contraste revérifié par calcul en thème sombre (cyan #55D9E7, texte #07151D, fond #050F14, alpha 0,45) : environ 3,1:1. En thème clair (le thème est DayNight), c'est pire : fond #0E7E90 et texte blanc à 0,45 sur #FFFFFF donnent environ 1,9:1, alors que l'usage visé est la lecture au soleil. Sans aucun planning (`length() == 0`), `sansPointage` reste faux : le bouton redevient actif pendant un créneau et le serveur refusera. La fin de fenêtre n'est pas indiquée et il n'y a pas de bouton « Ajouter mon planning ».

**Recommandation.** Dans updatePointButton(), remplacer la transparence par trois états visuels. (a) Pointage possible : primaryButton. (b) Attente ou blocage : style HydriaUi.secondaryButton, texte en HydriaColors.text à pleine opacité avec une icône (horloge ou position), par exemple « Prochain pointage : après-midi 15h–18h · dans 2 h 16 » ou « Trop loin : 4,2 km de Sahavola (max. 3 km) ». (c) Aucun planning alors que les données du jour sont à jour : bouton secondaire actif « Ajouter mon planning pour pointer », qui appelle showPlanningEditor(null). Ne jamais appliquer de transparence au texte.

### POINTAGE-07 — Autorisations GPS et notifications : demandes concurrentes, boucle possible, aucun recours

- **Sévérité** : Majeur
- **Écran** : Pointage – ouverture de l'écran
- **Catégorie** : feedback etats · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** L'écran enchaîne deux demandes système sans explication, n'aide pas à sortir d'un refus et ne propose pas d'activer la localisation quand elle est coupée. Demander une autorisation dans onResume expose à une boucle si le refus est définitif.

**Impact pour l'agent.** L'agent est bloqué sans savoir quoi faire : il doit trouver seul les réglages Android. Un message d'erreur trompeur s'affiche à la première ouverture. La boucle possible consomme batterie et données.

**Preuve (version 2.11.0).** PointageActivity.kt:132-134 POST_NOTIFICATIONS est demandée dans onCreate, puis l.915-919 ACCESS_FINE_LOCATION à chaque onResume. l.123-124 en cas de refus : `gpsStatus.text = "Localisation refusée : autorisez-la pour pointer."`, sans bouton. TerrainLocationController.kt:23-25 « GPS indisponible » et l.40 « Localisation désactivée », sans action proposée. l.921 refresh() (appel réseau) à chaque onResume. Déduction, non observée : à la 1re ouverture sous Android 13+, la seconde demande arrive pendant la première et est rejetée, ce qui affiche « Localisation refusée » à tort ; après un refus définitif, la fenêtre système transparente provoque onPause puis onResume, donc une nouvelle demande et un nouveau rafraîchissement réseau, en boucle.

**Vérification sur 2.12.0.** app/pointage/PointageActivity.kt:133-135 POST_NOTIFICATIONS demandée dans onCreate ; :921-925 ACCESS_FINE_LOCATION relancée à chaque onResume si non accordée ; :125 `gpsStatus.text = "Localisation refusée : autorisez-la pour pointer."` sans bouton ; :927 refresh() à chaque onResume ; navigation/location/TerrainLocationController.kt:23-25 « GPS indisponible » sans action — Inchangé. Aucun intent de réglages dans l'application : grep ACTION_APPLICATION_DETAILS_SETTINGS, ACTION_LOCATION_SOURCE_SETTINGS, ACTION_CHANNEL_NOTIFICATION_SETTINGS et shouldShowRequestPermissionRationale ne donne rien. Le refus et la localisation coupée n'offrent donc aucun recours. Les deux demandes concurrentes sous Android 13+ et la boucle onPause/onResume après un refus définitif restent des déductions plausibles, non observées. Le défaut certain est l'absence de recours et de garde « une seule demande ».

**Recommandation.** Demander la localisation une seule fois par session de l'écran (indicateur booléen). Enchaîner la demande de notifications dans le rappel de résultat de la localisation, ou la reporter après le premier pointage réussi avec une phrase d'explication. Détecter un refus définitif avec shouldShowRequestPermissionRationale et afficher une note() au ton ERROR avec un bouton principal « Ouvrir les réglages » (Settings.ACTION_APPLICATION_DETAILS_SETTINGS). Si la localisation est coupée, proposer « Activer la localisation » (Settings.ACTION_LOCATION_SOURCE_SETTINGS). Limiter refresh() à un appel toutes les 30 s.

### POINTAGE-08 — Pastille « à jour » du pointage : périmètre trompeur et pastille non cliquable

- **Sévérité** : Majeur
- **Écran** : Pointage – en-tête (et raccourci de l'accueil)
- **Catégorie** : feedback etats · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** Un pointage de nuitée fait à 20h30 et non envoyé apparaît « à jour » le lendemain matin. Une modification de planning hors ligne aussi. La pastille annonce une action qui n'existe pas.

**Impact pour l'agent.** L'agent croit tout envoyé et ne cherche pas de réseau, voire efface les données ou change de téléphone : son travail peut être perdu.

**Preuve (version 2.11.0).** PointageActivity.kt:480-484 `HydriaUi.syncChip(this, PointageStore.pendingCount(account), isOnline())`. PointageStore.kt:108-113 : todayEntries ne garde que la date du jour, et pendingCount ne compte que les pointages. Les opérations save_planning (l.435) et pointage_prevu (l.732), pourtant dans la même file, ne sont pas comptées. Aucun setOnClickListener sur la pastille, alors que syncChip (HydriaVisuals.kt) annonce « toucher pour ouvrir le centre de synchronisation » dès qu'il y a des éléments en attente. MainActivity.kt:768 réutilise ce compteur sur l'accueil. Capture 05 : « à jour ».

**Vérification sur 2.12.0.** app/pointage/PointageActivity.kt:488-489 `HydriaUi.syncChip(this, PointageStore.pendingCount(account), isOnline())` ; PointageStore.kt:108-114 `todayEntries` filtre la date du jour et `pendingCount` ne compte que PENDING ; PointageActivity.kt:441 (save_planning) et :738 (pointage_prevu) enfilés mais non comptés ; HydriaVisuals.kt:326-353 syncChip sans OnClickListener ; MainActivity.kt:929 réutilise ce compteur — Inchangé. Un pointage non envoyé de la veille ou une opération `save_planning` ou `pointage_prevu` en file ne sont pas comptés : la pastille indique « à jour ». Son contentDescription annonce « toucher pour ouvrir le centre de synchronisation » alors qu'aucun clic n'est branché dans l'écran Pointage.

**Recommandation.** Calculer le compteur à partir de la file OfflineStore (`store.pending()`), filtrée sur le compte et sur les types pointage, pointage_prevu et save_planning, toutes dates confondues. Rendre la pastille cliquable : elle ouvre une feuille listant ces opérations et leur état, ou lance MainActivity avec un paramètre qui ouvre showSyncCenter(). Utiliser la même fonction pour pointageShortcut().

### POINTAGE-09 — Trois points d'entrée, trois discours : l'accueil ne dit jamais « à pointer maintenant »

- **Sévérité** : Majeur
- **Écran** : Accueil (Terrain), carte « Pointage du jour » de la page Planning, barre du bas
- **Catégorie** : coherence · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** L'écran le plus consulté ne signale ni le créneau ouvert ni un pointage en retard. La page Planning rassure en vert à tort. Juste au-dessus de « 8 RDV », la mention « Aucun planning » mélange « mes plannings » et « l'agenda du périmètre ».

**Impact pour l'agent.** Créneaux oubliés faute de signal au bon endroit, lecture contradictoire entre deux écrans.

**Preuve (version 2.11.0).** MainActivity.kt:776-783 : la carte de l'accueil affiche toujours « Pointer ma position » suivi de PointageRules.libelleFenetres() (la liste fixe des trois créneaux), avec un ton INFO figé (l.763) – capture 01. MainActivity.kt:3901-3902 : dans la carte Planning, un planning sans créneau prévu donne « — aucun créneau prévu » en ton SUCCESS (vert), même pendant un créneau ouvert. l.3907 « Aucun planning aujourd'hui… » apparaît alors que l'agenda affiche « 8 RDV » le même jour (capture 04 : plannings du périmètre, pas ceux de l'agent). L'onglet Pointage n'a aucun indicateur d'état (l.474 et 740).

**Vérification sur 2.12.0.** app/MainActivity.kt:920-948 pointageShortcut : `accentedCard(this, Tone.INFO)`, titre fixe « Pointer ma position », sous-titre `PointageRules.libelleFenetres()` (ou « N pointage(s) en attente ») ; :4518-4567 planningPointageCard : `lines += "$name — ${states.ifBlank { "aucun créneau prévu" }}" to (… else Tone.SUCCESS)`, `"Aucun planning aujourd'hui : ajoutez-le pour pouvoir pointer."` ; :4404 badge « N RDV » — Toujours vrai. L'accueil ne signale ni créneau ouvert ni retard. La carte de la page Planning rassure en vert sur « aucun créneau prévu », y compris pendant un créneau ouvert. Elle titre « POINTAGE DU JOUR » sans préciser qu'elle porte sur les plannings de l'agent, à côté du badge « RDV » qui compte ceux du périmètre. Nuance : la carte Planning affiche bien « Créneau en cours : … » en gris, et affiche « Pointer ma position » en bouton principal pendant un créneau, ce qui atténue un peu le défaut ; l'accueil n'a rien de tel. L'onglet de la barre n'a aucun indicateur d'état.

**Recommandation.** Créer un résumé unique, par exemple PointageRules.resume(today, attente, maintenant) qui renvoie {titre, sous-titre, ton, action} : « À pointer maintenant · après-midi jusqu'à 18h » (WARNING), « Pointé à 10:12 ✓ » (SUCCESS), « Prochain : 15h–18h » (NEUTRAL), « Pas de planning : ajoutez-le pour pointer » (WARNING), « 1 pointage refusé » (ERROR). L'utiliser dans pointageShortcut() et planningPointageCard(), et comme pastille d'état sur l'icône Pointage de la barre. Dans la page Planning, titrer « Mon pointage (mes plannings) » pour le distinguer de l'agenda de l'équipe.

### POINTAGE-10 — « Mon équipe » : cartes « 0/0 » répétées, ratio sans libellé, symboles sans légende

- **Sévérité** : Majeur
- **Écran** : Pointage – section superviseur « Mon équipe »
- **Catégorie** : rendu donnees · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0

**Constat.** La liste traite de la même façon les employés sans planning et ceux qui doivent pointer. Le ratio n'a pas de sens (POINTAGE-02), les abréviations et symboles ne sont pas expliqués, et rien ne s'affiche hors ligne.

**Impact pour l'agent.** Le superviseur fait défiler des dizaines de cartes identiques sans voir qui doit pointer maintenant ni qui a manqué.

**Preuve (version 2.11.0).** PointageActivity.kt:838-840 `"${employee.optInt("nb_ok")}/${employee.optInt("nb_prevus")}"` sans libellé. l.843-844 : chaque employé sans planning a sa propre carte « Aucun planning aujourd'hui ». l.849 `"${creneau.label.take(3)}. $text"` produit « Mat. ✓ 10:12 », « Apr. ● », « Nui. ○ » sans légende (symboles définis l.865-869). l.820 « actualisé à 14:44:45 ». l.816 tri par manques, toujours nuls (POINTAGE-02). Capture 05 : cinq cartes « 0/0 » d'environ 107 px remplissent l'écran.

**Vérification sur 2.12.0.** app/pointage/PointageActivity.kt:844-846 `"${employee.optInt("nb_ok")}/${employee.optInt("nb_prevus")}"` sans libellé ; :849-850 carte « Aucun planning aujourd'hui » par employé ; :855 `"${creneau.label.take(3)}. $text"` ; :826 `actualisé à ${t.optString("actualise_a")}` (le serveur renvoie HH:MM:SS) ; :812 loadTeam `if (!isOnline()) return` ; :822 tri par nb_manques — Inchangé : une carte par employé, sans regroupement ni repli des employés sans planning, ratio sans mots, symboles ✓ ● ○ ✗ sans légende, secondes affichées, et rien d'affiché hors ligne (teamBox vidé dans stopTeamRefresh puis loadTeam abandonne). La section n'est pas repliable. Le tri par manqués place bien les problèmes en premier, mais `nb_manques` reste à 0 tant que POINTAGE-02 n'est pas traité.

**Recommandation.** Dans renderTeam(), regrouper en trois parties : (1) « À surveiller » (manqué, ou créneau en cours non pointé) en premier ; (2) « Pointés » ; (3) une seule ligne repliée « Sans planning aujourd'hui (7) : ADORE, ALAIN… ». Remplacer x/y par des mots (« 1 pointé · 1 à pointer · 0 manqué »). Afficher les créneaux avec HydriaUi.badge en toutes lettres (« Matin ✓ 10:12 », « Après-midi à pointer », « Nuit — »). Afficher « actualisé à 14:44 » sans les secondes. Hors ligne, afficher « Équipe indisponible hors ligne ». Rendre la section repliable pour ne pas repousser le contenu personnel.

### POINTAGE-11 — Pointage entièrement en français codé en dur, notification et motifs de refus compris

- **Sévérité** : Majeur
- **Écran** : Pointage, notification de rappel
- **Catégorie** : i18n · **Effort** : M
- **Statut** : Vérifié en 2.12.0

**Constat.** Cet écran quotidien, lié à la paie, ne suit pas la langue de l'application. La notification sur l'écran verrouillé et les motifs de refus sont uniquement en français. Les heures apparaissent sous deux formats différents.

**Impact pour l'agent.** Les agents à l'aise surtout en malgache comprennent mal les motifs de blocage et les rappels, ce qui entraîne des erreurs et des appels au superviseur.

**Preuve (version 2.11.0).** Aucune référence R.string dans pointage/*.kt (grep : 0). PointageActivity.kt:240 `DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.FRANCE)`. l.228 « Pointer ma position », l.636 « Position simulée détectée… ». PointageReminders.kt:126-127 `setContentTitle("Pointage …")` et `setContentText("Pointez votre position entre %02dh et %02dh.")`. res/values-mg/strings.xml contient 160 chaînes, mais aucune pour le pointage. Les formats se mélangent : « 15h00-18h00 » vient du serveur (services_pointage.py:320, affiché l.310) et « 15h-18h » du calcul local (PointageRules.kt:25).

**Vérification sur 2.12.0.** grep R.string dans app/pointage/*.kt : 0 occurrence ; PointageActivity.kt:246 `DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.FRANCE)` ; PointageReminders.kt:119,126-127 « Rappels de pointage », `setContentTitle("Pointage …")`, `setContentText("Pointez votre position entre %02dh et %02dh.")` ; PointageRules.kt:25 fenetre `"%02dh-%02dh"` vs serveur `15h00-18h00` affiché en PointageActivity.kt:316 — Inchangé. res/values-mg/strings.xml (160 chaînes) ne contient rien pour le pointage, et MainActivity ne compte que 2 occurrences de R.string : le défaut est transverse. Il n'y a pas de sélecteur de langue dans l'application ; la langue suit celle du système. Les deux formats d'horaires coexistent toujours (« 15h00-18h00 » du serveur et « 15h-18h » local).

**Recommandation.** Déplacer environ 50 chaînes vers strings.xml et values-mg, en commençant par les états du bouton, le statut GPS, les refus et la notification. Utiliser des ressources plurielles pour « pointage(s) ». Formater les dates selon la langue de l'application. Toujours formater la fenêtre localement depuis PointageRules en ignorant `fenetre` du serveur, avec un format unique « 15h–18h ». C'est une dette transverse : MainActivity n'a que deux références R.string.

### POINTAGE-12 — Carte claire dans l'application sombre, vide hors ligne, et 240 dp même sans village géolocalisé

- **Sévérité** : Mineur
- **Écran** : Pointage – carte MapLibre
- **Catégorie** : esthetique · **Effort** : S
- **Statut** : Vérifié en 2.12.0

**Constat.** En ligne, fond OSM clair quel que soit le thème. Hors ligne, fond noir sans aucun repère. Quand aucun village du planning n'a de coordonnées, la carte occupe environ un quart de l'écran pour montrer un seul point. La zone cyan des 3 km n'est expliquée nulle part. Nuance : un fond clair reste plus lisible en plein soleil et se défend en journée, mais la nuitée (19h–21h) se pointe de nuit.

**Impact pour l'agent.** Éblouissement le soir, carte inutile hors ligne, espace perdu au-dessus du contenu utile, sens de la zone et des points incompris.

**Preuve (version 2.11.0).** PointageActivity.kt:76 `ONLINE_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty"`, et l.199-201 le style est choisi selon la connexion, jamais selon le thème. assets/navigation_neutral_style.json : `"background-color": "#07151D"` et `"sources": {}` (hors ligne : fond noir sans aucune route). l.534-541 couleurs en dur `Color.rgb(155, 138, 251)` et `Color.rgb(37, 99, 235)` au lieu de R.color.hydria_map_village. l.196 hauteur fixe `dp(240)`. l.567-579 cadrage unique, sans bouton de recentrage ni légende. Capture 05 : un seul point bleu, aucune zone, un rectangle très clair entre deux blocs bleu nuit.

**Vérification sur 2.12.0.** app/pointage/PointageActivity.kt:76 `ONLINE_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty"` ; :205 `val uri = if (isOnline()) ONLINE_STYLE_URL else "asset://navigation_neutral_style.json"` ; :543,546 `Color.rgb(155, 138, 251)` / `Color.rgb(37, 99, 235)` ; :201 `LinearLayout.LayoutParams(-1, dp(240))` ; assets/navigation_neutral_style.json `"sources": {}`, fond #07191D — Inchangé : le style est choisi selon la connexion et jamais selon le thème, les couleurs sont en dur alors que R.color.hydria_map_village existe, la hauteur est fixe, et il n'y a ni légende ni bouton de recentrage. Nuance : hors ligne, le fond est noir sans route, mais la zone des 3 km, les villages et la position restent dessinés par-dessus, donc la carte n'est pas totalement vide. Les 2.11.1 à 2.12.0 n'ont ajouté que le garde-fou anti-plantage (mapSupported, isLowRamDevice), sans lien avec ce constat.

**Recommandation.** En mode nuit (resources.configuration.uiMode et UI_MODE_NIGHT_MASK), ajouter après chargement du style une couche de remplissage couvrant le monde, couleur ink à 35 %, sous `pointage-zones-fill` (ou utiliser un style vectoriel sombre). Prendre les couleurs dans R.color.hydria_map_village et HydriaColors.cyan. Si villagesDuJour est vide, réduire la carte à 120 dp ou la remplacer par la note « Aucun village géolocalisé : le serveur vérifiera la distance ». Ajouter sous la carte une légende d'une ligne (« Zone = 3 km autour du village · point bleu = vous ») et un bouton de recentrage.

### POINTAGE-13 — Statut GPS : une position ancienne présentée comme actuelle, des messages hors sujet

- **Sévérité** : Mineur
- **Écran** : Pointage – ligne de statut GPS au-dessus du bouton
- **Catégorie** : feedback etats · **Effort** : S
- **Statut** : Vérifié en 2.12.0

**Constat.** Le statut et l'état du bouton peuvent dire « vous pouvez pointer » ou « trop loin » en s'appuyant sur une ancienne position, puis le clic contredit l'écran. Le message affiché sans planning est faux.

**Impact pour l'agent.** Le statut et le clic se contredisent, l'agent perd confiance et s'interroge pour rien sur le GPS ou sur son planning.

**Preuve (version 2.11.0).** TerrainLocationController.kt:29 `manager.getLastKnownLocation(provider)?.let(onLocation)` : cette position peut dater de plusieurs heures. PointageActivity.kt:594-625 updateGpsStatus n'affiche ni n'écarte une position ancienne, et peut afficher en vert « vous pouvez pointer ». l.502-506 tooFar() ne vérifie pas l'âge, d'où un bouton « Trop loin pour pointer » calculé sur la position de la veille. l.646-648 au clic, refus « position trop ancienne » au-delà de 60 s. l.612-614 « Aucun village avec coordonnées pour votre planning » s'affiche alors qu'il n'y a aucun planning (capture 05). l.585-587 : les positions réseau (±1 km) et GPS peuvent alterner toutes les 20 s et faire clignoter le statut (déduction).

**Vérification sur 2.12.0.** navigation/location/TerrainLocationController.kt:29 `manager.getLastKnownLocation(provider)?.let(onLocation)` ; PointageActivity.kt:600-630 updateGpsStatus sans contrôle d'âge ; :508-512 tooFar() sans contrôle d'âge ; :652 contrôle de 60 s seulement au clic, après le test tooFar (:648) ; :619 « Aucun village avec coordonnées pour votre planning » — Inchangé : une position ancienne alimente le statut vert ou « trop loin » et l'état du bouton, puis le clic la refuse. Le message « aucun village avec coordonnées » est affiché même sans aucun planning. Le point sur le clignotement entre positions réseau et GPS n'est pas démontré : onLocation ne remplace une position récente que si la nouvelle est au moins aussi précise.

**Recommandation.** Pour le statut et tooFar(), ignorer toute position de plus de 60 s : afficher « Recherche du signal GPS… (dernière position il y a 12 min) » au ton neutre. Indiquer l'âge à côté de la précision. Distinguer les messages « aucun planning » et « aucun village géolocalisé ». Ignorer les positions réseau dont la précision dépasse PRECISION_MAX_M dès qu'une position GPS récente existe.

### POINTAGE-14 — Rappels : un seul avis à l'ouverture du créneau, aucune relance, aucun réglage dans l'application

- **Sévérité** : Mineur
- **Écran** : Notification « Pointage après-midi »
- **Catégorie** : workflow · **Effort** : S
- **Statut** : Vérifié en 2.12.0

**Constat.** Le rappel arrive 10 minutes avant l'ouverture du créneau, puis plus rien jusqu'à la fin de la fenêtre (2 à 3 h). On ne peut ni le régler ni le couper depuis l'application.

**Impact pour l'agent.** Un agent occupé à 15h n'a pas de seconde chance avant 18h. Pour couper les rappels, il doit passer par les réglages Android.

**Preuve (version 2.11.0).** PointageReminders.kt:28 `LEAD_MINUTES = 10L`, et l.36-49 un seul déclencheur par créneau. l.114-116 aucun rappel si la fenêtre est passée. l.119 canal « Rappels de pointage » en IMPORTANCE_HIGH, sans réglage dans l'application. l.126-127 texte générique, sans planning ni village. l.120-123 aucune action « Pointer » et pas de pile de retour vers l'application.

**Vérification sur 2.12.0.** app/pointage/PointageReminders.kt:28 `LEAD_MINUTES = 10L` ; :42-43 un seul déclencheur par créneau ; :114 aucun rappel si la fenêtre est passée ; :119 canal IMPORTANCE_HIGH ; :121 `addFlags(FLAG_ACTIVITY_NEW_TASK)` sans addAction ni pile de retour ; :126-127 texte générique — Inchangé : un seul rappel, 10 minutes avant l'ouverture, aucune relance en fin de fenêtre, aucun planning ni village dans le texte, aucune action « Pointer ». Aucun réglage ni interrupteur dans l'application (grep « rappel » dans le code hors pointage : rien). Les rappels dépendent aussi de POINTAGE-02, car `triggers` ne programme que les créneaux déclarés prévus.

**Recommandation.** Ajouter un second déclencheur à fin − 30 min si dejaFait est faux (« Il reste 30 min pour pointer l'après-midi »). Ajouter le planning et le village, lus dans cachedToday. Ajouter une action « Pointer » via addAction. Prévoir un interrupteur « Rappels de pointage » dans le menu ⋮, avec un lien vers Settings.ACTION_CHANNEL_NOTIFICATION_SETTINGS. Utiliser un TaskStackBuilder pour que « retour » mène à l'accueil.

### POINTAGE-15 — Écarts au système de design : cibles de 40 dp, case native, dialogue non thématisé, coins colorés parasites

- **Sévérité** : Mineur
- **Écran** : Pointage, dialogue de planning, cartes Pointage de l'accueil et de la page Planning
- **Catégorie** : coherence · **Effort** : S
- **Statut** : Vérifié en 2.12.0

**Constat.** Le pointage recrée ses propres petits composants au lieu d'utiliser HydriaUi : cibles tactiles sous 48 dp, case et dialogue au style Android par défaut, cartes sans couleur d'état, date au format ISO. Les coins parasites ont une cause unique dans accentedCard.

**Impact pour l'agent.** Ratés de toucher en marchant et d'une main. L'écran paraît d'une autre application. Les dates sont saisies dans un format étranger à l'agent.

**Preuve (version 2.11.0).** PointageActivity.kt:898-904 secondary() force `minHeight = 0; minimumHeight = 0`, d'où « Modifier ce planning » à 40 dp (l.294-295, 324-325), « + Ajouter » à 46 dp (l.264-265) et le retour « ← » en texte à 44 dp (l.159), au lieu des 52 dp de HydriaUi.secondaryButton (HydriaVisuals.kt:287-300). l.309 CheckBox native. l.281 HydriaUi.card simple, alors que l'application code l'état avec accentedCard(ton). l.401 androidx.appcompat AlertDialog.Builder ignore materialAlertDialogTheme (themes.xml:25). l.369-371 date en saisie libre « AAAA-MM-JJ » (même défaut que l'obs. 7). Coins colorés (obs. 2) sur les cartes de l'accueil et de la page Planning : dans HydriaVisuals.kt:262-266, `cornerRadii = floatArrayOf(radius, radius, 0f, 0f, 0f, 0f, radius, radius)` donne au filet des coins droits carrés, que le corps arrondi (décalé de 3 dp à gauche seulement) ne recouvre pas. Nuance sur l'obs. 12 : textSecondary #9FBAC4 sur surface #0E2029 donne environ 8:1 ; le manque de lisibilité vient de 13 sp × 0,85 ≈ 11 sp, pas de la couleur.

**Vérification sur 2.12.0.** app/pointage/PointageActivity.kt:904-910 secondary() `minHeight = 0; minimumHeight = 0` ; :301,331 `dp(40)` « Modifier ce planning » ; :270 `dp(46)` « + Ajouter » ; :163 retour « ← » en `dp(48), dp(44)` ; :315 CheckBox native ; :287 HydriaUi.card ; :407 `androidx.appcompat.app.AlertDialog.Builder` ; :375-376 « Date (AAAA-MM-JJ) » ; HydriaVisuals.kt:262-266 `cornerRadii = floatArrayOf(radius, radius, 0f, 0f, 0f, 0f, radius, radius)` — Tous les points sont toujours présents, y compris le défaut des coins de accentedCard (HydriaVisuals.kt inchangé depuis le 17/09, filet aux coins droits carrés non couverts par le corps arrondi). Une nuance : le dialogue n'est pas entièrement hors thème, car l'app définit colorSurface et colorOnSurface sur les couleurs Hydria ; seul le ThemeOverlay.Hydria.Dialog (surface relevée) est ignoré, puisque `materialAlertDialogTheme` ne concerne que MaterialAlertDialogBuilder.

**Recommandation.** Supprimer la surcharge de minHeight dans secondary() (48 dp minimum). Remplacer la flèche texte par un ImageButton avec icône de retour, en 48 dp. Utiliser accentedCard avec le ton du créneau pour les cartes de planning, et MaterialAlertDialogBuilder pour le dialogue. Saisir la date avec un DatePickerDialog et l'afficher en « 12/10/2026 ». Corriger accentedCard en donnant les quatre arrondis au filet (`cornerRadii = FloatArray(8) { radius }`) : le corps le recouvre alors à droite, et la correction vaut pour toute l'application. Passer le texte des boutons secondaires à 14–15 sp.


## Recherche, fiches et carte

_Audit initial sur la version 2.12.0._

**Synthèse du domaine.** Audit du domaine Recherche / fiches / carte, établi sur le code (aucune capture de la carte ni des fiches n'existait dans le dossier ; l'appareil de test est en thème sombre, ce qui masque des défauts propres au thème clair). 12 constats vérifiés à la ligne : 2 critiques, 9 majeurs, 1 mineur.

La Recherche reprend bien le système de design (champ 56 dp, onglets, jetons de type, cache avec horodatage) mais trois choses la desservent : les fiches affichent un dump brut du modèle Django, la recherche hors ligne ne couvre que les ouvrages, et la fiche est un cul-de-sac (ni appeler, ni « Y aller »). La carte a un socle technique sain (R-tree, repli de fond, file hors ligne, itinéraire 2.11.0), mais l'interaction casse sur le terrain : villages non touchables, HUD illisible en thème clair, état perdu à la rotation, pose de position sans garde-fou.

Non retenus faute de place (à traiter ensuite) : (1) Interventions récentes embarque toutes les pièces jointes en base64 dans chaque page de liste (backend/apps/core/views_mobile_search.py:339 ; RecentInterventionsActivity.kt:171-175 ; mises en cache par clé de page) et affiche Terminer/Reporter/Modifier/Supprimer hors ligne pour les refuser au toucher (:225, :260, :312) ; statuts bruts « termine / annule / reporte » sans accent (:164). (2) Aucune chaîne de search/ ni navigation/ ne passe par R.string : values-mg (160 entrées) est ignoré, et plusieurs dialogues manquent d'accents (« enregistree », « deplacee », « Selectionnez », « marque hors ligne »). (3) Textes de 10,5 à 12 sp (jetons, libellés, boutons de la carte) qui tombent vers 9-10 sp à l'échelle de police 0,85 de l'appareil réel ; puces de couches à 32 dp.

**À préserver :**

- Recherche fidèle au système de design : champ 56 dp à filet cyan avec croix d'effacement, onglets Tout/Personnes/Ouvrages, jetons de type PE/V/EQ, cartes à liseré, en-tête d'état EN LIGNE / HORS LIGNE.
- Robustesse réseau de la Recherche : anti-rebond 400-500 ms, jeton de génération contre les réponses périmées, cache par clé (requête + filtres + page) avec date affichée en en-tête, état (requête, filtres, scroll) sauvé et restauré à la rotation.
- Fiche détail pensée offline-first : cascade cache, puis aperçu issu du résultat, puis message clair ; UUID techniques masqués (isTechnicalUuid) ; champs manquants en ton avertissement ; « En attente d'envoi : GPS, Photo » ; mise en file immédiate puis envoi opportuniste ; validations de saisie ; photo retrouvée après destruction du processus.
- Fiches village/commune bien structurées : cartes de synthèse chiffrées (fonctionnels / total, « branchés, non coupés »), bloc d'alerte « sans date de branchement » séparé du décompte, navigation croisée commune - village - ouvrage, filtre dans les listes longues, entrées non cliquables atténuées avec le motif.
- Honnêteté du guidage : distances toujours libellées « direct » / « à vol d'oiseau », message « itinéraire routier indisponible - cap direct » hors ligne, réponses d'itinéraire périmées ignorées (routeRequestId), recalcul seulement après 300 m et 20 s, profil de déplacement mémorisé.
- Rendu cartographique soigné : tracé orange à liseré sombre sous les repères, libellés blancs à halo, noms d'entités seulement dès le zoom 13, entités à moins de 3 km toujours chargées avant la limite de 600, repli automatique vers un fond local.
- Chaîne de marquage hors ligne solide : candidats filtrés par proximité des villages (25 km), distance de déplacement annoncée, ancienne position gardée en historique, proposition de photographier si la photo manque, conflits modélisés côté synchro.
- Cibles tactiles généreuses sur les actions principales (boutons 48-58 dp, rayon de capture de 54 dp pour les indicateurs de bord) et contentDescription sur le retour et les puces de couches.

### RECH_NAV-02 — HUD de navigation illisible en thème clair : texte sombre sur panneau sombre codé en dur

- **Sévérité** : Critique
- **Écran** : Navigation terrain - bandeau haut et HUD de guidage
- **Catégorie** : accessibilite · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (contre-épreuve : réfutation échouée)

**Constat.** En thème clair (le mode « lisible au soleil »), le titre « NAVIGATION TERRAIN », le nom de la destination et la distance (22 sp) sont du #07151D sur du #07151D : invisibles. Mode, statut, cap/ETA et ligne d'itinéraire (textSecondary) sont à environ 3:1. Seuls les boutons, qui ont un fond clair, restent lisibles. En thème sombre (appareil de test) tout semble correct, ce qui cache le défaut.

**Impact pour l'agent.** De jour, avec un téléphone en thème clair, l'agent voit des boutons mais ni la distance restante ni le nom de la cible : le guidage devient inutilisable précisément dans la condition visée.

**Preuve (version 2.12.0).** NavigationTerrainActivity.kt:181 et :218 : fonds Color.argb(238|245, 7, 21, 29) fixes quel que soit le thème ; textes en HydriaColors.text par défaut (label() :1085, hudDistance :249, titre :185). res/values/colors.xml : hydria_text = #07151D en thème clair, identique au fond du panneau ; hydria_text_secondary #4A6570 sur #07151D donne environ 3:1. HydriaApp.kt:23 : MODE_NIGHT_FOLLOW_SYSTEM, donc le clair est actif de jour. Mêmes fonds sombres fixes : puces de couches :1070 et EdgeIndicatorsView.kt:49.

**Vérification sur 2.12.0.** app/src/main/java/mg/hydria/app/navigation/NavigationTerrainActivity.kt:181 (bandeau haut `Color.argb(238, 7, 21, 29)`) et :218 (HUD `Color.argb(245, 7, 21, 29)`) ; textes : label() l.1085-1087 par défaut `HydriaColors.text` (titre l.185, hudName l.~244, hudDistance l.249 `setTextColor(HydriaColors.text)`), `textSecondary` pour statut/hudMeta/hudRoute/« EN ROUTE ». res/values/colors.xml : hydria_text = #07151D, hydria_text_secondary = #4A6570 ; values-night : #FFFFFF. HydriaApp.kt:23 MODE_NIGHT_FOLLOW_SYSTEM ; AndroidManifest.xml:32 thème Theme.HydriaApp (DayNight), aucun thème sombre forcé pour NavigationTerrainActivity. — Réfutation tentée, échec : la couleur du HUD ne dépend PAS du thème (fonds en dur) alors que les textes viennent de HydriaColors, résolu par HydriaColors.bind(this) en onCreate (l.154) selon la configuration. En thème clair : titre « NAVIGATION TERRAIN », nom de destination et distance (22 sp) en #07151D sur #07151D (≈ 1,2:1 une fois mélangé à la carte claire, invisible) ; textSecondary #4A6570 sur ce fond ≈ 2,5-3:1 (statut, cap/ETA, itinéraire). Lisibles : boutons (fond surfaceRaised clair), flèche de cap (vase), mode (cyan ≈ 3,3:1). Même défaut en tablette : le HUD (l.215-218) garde son fond sombre dans un panneau clair. Correction de périmètre : EdgeIndicatorsView.kt:49 n'est PAS fautif (texte `Color.WHITE` en dur sur pastille sombre, cohérent) ; seule la puce de couche désactivée (l.1070, texte textMuted #7A929B sur fond sombre ≈ 4:1) est limite. Les occurrences à corriger sont donc l.181, l.218 et éventuellement l.1070. Sévérité : « critique » au niveau de l'écran (informations principales du guidage illisibles dans le mode système le plus courant de jour) ; au niveau de l'app, secondaire (fonction accessible via le menu session).

**Recommandation.** Remplacer les panneaux par HydriaColors.surface avec alpha 238 (ou ajouter hydria_map_overlay / hydria_on_map_overlay dans values et values-night) pour le bandeau haut, le HUD et les puces désactivées : les textes HydriaColors.text / textSecondary redeviennent cohérents dans les deux thèmes. Corriger les 4 occurrences de Color.argb(..., 7, 21, 29) (:181, :218, :1070, EdgeIndicatorsView:49). Ajouter une capture clair + sombre de cet écran à la checklist de recette.

### RECH_NAV-01 — Carte : les villages ne se touchent pas, les grappes sont muettes et inertes

- **Sévérité** : Majeur (initialement Critique)
- **Écran** : Navigation terrain - carte (repères)
- **Catégorie** : ergonomie · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (contre-épreuve : réfutation échouée)

**Constat.** Toucher un village sur la carte ne fait rien : seuls points d'eau, équipements et repères ouvrent la feuille (Y aller / Voir la fiche), alors que detailTypeOf() prévoit bien la fiche village. Un village n'est atteignable que par le détour d'un indicateur de bord, quand il est hors écran. Aux zooms inférieurs ou égaux à 14, points d'eau/équipements/repères fusionnent en disques cyan sans nombre (le cyan d'un point d'eau) qu'un toucher ne fait pas zoomer. Le hit-test ponctuel exige de viser un picto de 20 dp au doigt.

**Impact pour l'agent.** L'agent ne peut pas lancer « Y aller » vers un village (la destination la plus courante) en le touchant ; sur le terrain, en plein soleil et à une main, même les points d'eau demandent plusieurs essais ; les grappes ne disent ni combien ni quoi.

**Preuve (version 2.12.0).** navigation/NavigationTerrainActivity.kt:428 : selectAt() n'interroge que MarkerLayerManager.ENTITY_LAYER. navigation/map/MarkerLayerManager.kt:101-105 : les villages sont dessinés par VILLAGE_MARKER_LAYER (source distincte) ; ce layer n'est interrogé nulle part (grep : un seul queryRenderedFeatures dans l'app). MarkerLayerManager.kt:91-95 : CLUSTER_LAYER est un simple cercle cyan de 20 sans texte point_count, et aucun clic de grappe n'est géré. Le test de toucher est un PointF exact pour un picto d'environ 20 dp (bitmap 72 px, iconSize 0,72).

**Vérification sur 2.12.0.** app/src/main/java/mg/hydria/app/navigation/NavigationTerrainActivity.kt:315 (seul addOnMapClickListener) et :425-433 `selectAt` : `queryRenderedFeatures(screenPoint, MarkerLayerManager.ENTITY_LAYER)` uniquement, avec un PointF exact. navigation/map/MarkerLayerManager.kt:97-105 : ENTITY_LAYER filtre `not(has("point_count"))` sur SOURCE_ID ; les villages vont dans VILLAGE_SOURCE_ID / VILLAGE_MARKER_LAYER (submit(), séparation `villages` / `otherEntities`) ; l.92-95 CLUSTER_LAYER = simple CircleLayer cyan rayon 20 sans SymbolLayer de point_count. Aucune requête sur VILLAGE_MARKER_LAYER ni CLUSTER_LAYER nulle part. — Réfutation tentée, échec : pas de listener sur les villages ni sur les grappes, et aucun autre queryRenderedFeatures dans l'app. Un village visible à l'écran n'est pas sélectionnable ; il l'est seulement via un indicateur de bord, or IndicatorSelection.select (shared/.../IndicatorSelection.kt:22) exclut les entités déjà à l'écran (détour : faire sortir le village de l'écran). Atténuation tablette uniquement : le panneau « Autour de moi · 500 m » (NavigationTerrainActivity.kt:285, 380-424) liste villages compris et lance startNavigation au toucher. Aucun autre point d'entrée de navigation (grep « Y aller » / from_navigation : seule la fiche Recherche propose un retour à la carte). Les grappes sont inertes et sans nombre. Nuance sur le seuil : le code ne fixe pas clusterMaxZoom (`GeoJsonOptions().withCluster(true).withClusterRadius(46)`), et la vue initiale est à zoom 13 (l.321-324) ; l'audit dit « zoom <= 14 », le défaut natif de MapLibre est vraisemblablement 17 (non vérifié, sources absentes) : la fusion persiste alors plus haut que dit, ce qui aggrave plutôt qu'atténue. Sévérité : lacune d'interaction avec contournements (indicateurs de bord, zoom manuel, liste tablette), sans perte de données ni crash, donc « majeur » plutôt que « critique ».

**Recommandation.** Dans selectAt(), requêter un RectF de ±24 dp autour du toucher sur arrayOf(ENTITY_LAYER, VILLAGE_MARKER_LAYER, CLUSTER_LAYER) et retenir le plus proche du doigt. Si grappe : animateCamera(newLatLngZoom(point, zoom + 2)). Dans MarkerLayerManager, ajouter une SymbolLayer sur la source des grappes avec textField(get("point_count_abbreviated")) et une couleur de grappe neutre (surfaceRaised + liseré) distincte du cyan point d'eau. Extraire le choix de la feature la plus proche en fonction pure testable.

### RECH_NAV-03 — Marquer une position : pas de réticule et aucun garde-fou sur la qualité du fix

- **Sévérité** : Majeur
- **Écran** : Navigation terrain - Marquer ma position / Placer sur la carte
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** « Placer sur la carte » enregistre un point que l'utilisateur ne voit pas (quatre panneaux recouvrent la carte, aucune croix). « Marquer ma position » peut enregistrer un fix réseau à plusieurs centaines de mètres (qui a écrasé un bon fix GPS) ou une position vieille de 2 minutes, sans alerte dans 2 des 3 parcours. La pose enchaîne 4 à 5 dialogues sans jamais afficher les coordonnées ni la précision ; seul « Modifier la position GPS » avertit.

**Impact pour l'agent.** Des coordonnées fausses sont enregistrées dans le référentiel (l'ancienne reste en historique) : les agents suivants naviguent vers un mauvais endroit, et l'erreur est invisible au moment de la saisie.

**Preuve (version 2.12.0).** NavigationTerrainActivity.kt:716-719 : markMapCenter() enregistre le centre caméra, mais buildUi (:169-297) ne pose aucune mire (la doc §7.2 la prévoyait). :684 est le seul avertissement de précision (captureEntityPosition), avec 30f codé en dur : NavigationConfig.accuracyWarningMeters (shared .../GeoModels.kt:60) n'est lu nulle part ; confirmExistingEntityPlacement (:862-895) et createLandmarkAt (:776-809) n'avertissent pas. location/TerrainLocationController.kt:21-31 écoute GPS et NETWORK, et onLocation (:529-531) écrase currentLocation sans comparer ; shared NavigationProgress.kt:27 accepte un fix de 120 s ; markCurrentPosition (:697) ne revérifie ni âge ni précision. Le libellé « GPS ± » (:574, :1006) s'applique aussi aux fixes réseau.

**Recommandation.** 1) Vue réticule centrée (croix 36 dp + bandeau « lat, lon ») tant que la pose est active, avec un bouton « Poser ici ». 2) shared/navigation : PositionQuality (ignorer NETWORK si un fix GPS a moins de 15 s ; n'écraser que si plus récent et précision au plus 1,5 fois l'actuelle ; âge maximal 15 s pour une pose), avec tests JVM. 3) Un garde-fou unique appelé par les 3 parcours : si accuracy dépasse navigationConfig.accuracyWarningMeters ou si l'âge dépasse 15 s, dialogue « Précision ± 85 m (seuil 30 m) » avec Réessayer / Enregistrer quand même ; afficher coordonnées et précision dans les confirmations. 4) Colorer la précision (vert ≤ 10 m, ambre ≤ 30 m, rouge au-delà) et libeller « Réseau » pour un fix NETWORK.

### RECH_NAV-04 — Rotation ou retour de l'appareil photo : la navigation active et la photo en cours sont perdues

- **Sévérité** : Majeur
- **Écran** : Navigation terrain
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Toute recréation de l'activité (rotation du téléphone, y compris au retour de l'appareil photo pris en paysage, ou mémoire basse sur téléphone d'entrée de gamme) efface la cible, l'itinéraire (aucun cache : requestRoute exige le réseau), le mode, le sens d'orientation et les filtres de couches, et abandonne sans aucun message la photo qui vient d'être prise (ni enfilée, ni signalée).

**Impact pour l'agent.** L'agent qui marche vers un village perd son guidage en tournant le téléphone ; la photo d'un point d'eau prise à des kilomètres de la base est perdue sans qu'il le sache, le point reste « photo manquante ».

**Preuve (version 2.12.0).** AndroidManifest.xml:68-70 : NavigationTerrainActivity en screenOrientation=fullSensor sans configChanges (MainActivity en déclare). NavigationTerrainActivity.kt:109, :114 (target, activeRoute, mode, directionUp, visibleCategories : simples champs d'instance) et :1106 (seul l'état de la carte est sauvé). :122-123 et :129-140 : pendingPhotoCandidate / pendingPhotoFile non sauvés, et le callback ignore sans message la photo si candidate est null. SearchDetailActivity.kt:93-102 sauve au contraire pending_photo parce que « l'appareil photo peut détruire le processus ».

**Recommandation.** Court terme (S) : verrouiller le portrait sur téléphone (screenOrientation portrait, ou configChanges comme MainActivity) et afficher un toast quand le résultat photo arrive sans candidat. Complet (M) : dans onSaveInstanceState sauver target (catégorie + id), mode, directionUp, visibleCategories, chemin de la photo en attente + candidat ; restaurer après importSnapshot() en rappelant startNavigation(entity) sans réafficher le dialogue d'arrivée ; mettre la dernière route en cache (SharedPreferences, clé cible + profil) pour la retrouver hors ligne. Reprendre le schéma de SearchDetailActivity pour la photo.

### RECH_NAV-05 — HUD : l'itinéraire routier de la 2.11.0 est relégué en 12 sp et la flèche l'ignore

- **Sévérité** : Majeur
- **Écran** : Navigation terrain - HUD de guidage
- **Catégorie** : rendu donnees · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Depuis l'ajout de l'itinéraire, l'écran affiche deux distances et deux durées qui se contredisent (grand : « 380 m (direct) · ~5 min » ; petit : « Par la route : 3,2 km · ~25 min (moto) ») et une flèche qui traverse la brousse alors que le tracé orange suit la piste. L'ETA direct saute à chaque fix. Rien n'indique l'état du bouton d'orientation, et l'action principale « Marquer ma position » a le même style que « Sync ».

**Impact pour l'agent.** L'agent lit le chiffre le plus gros, donc une durée fausse d'un facteur 5, et suit une flèche qui le fait quitter la route.

**Preuve (version 2.12.0).** NavigationTerrainActivity.kt:245-253 : distance à vol d'oiseau en 22 sp (suffixe « (direct) » de GeoMath.formatDistance + « à vol d'oiseau » :574, redondants) ; :260 et :643-648 : distance/durée par la route en 12 sp textSecondary, sur environ 3 lignes dans une colonne de 186 dp. :556-574 : la flèche (relativeDirectionDegrees) et l'ETA (shared NavigationProgress.kt:45-46 : distance directe divisée par la vitesse GPS instantanée) ignorent activeRoute ; un second ETA « Par la route » coexiste. :1088-1092 button() : tous les boutons ont le même style, 12 sp ; Profil et Tracé à 40 dp ; le bouton « N » (:210) n'est jamais mis à jour par toggleOrientation() (:986-990).

**Recommandation.** Si activeRoute n'est pas null : valeur principale = distance restante par la route + durée (22 sp, « 3,2 km · ~25 min »), sous-ligne « direct 380 m » ; sinon comportement actuel. Ajouter shared/navigation RouteGuidance.nextWaypoint(route, location, lookahead = 40 m) (projection sur la polyligne, test JVM) pour orienter la flèche, et supprimer l'ETA direct quand une route existe. Raccourcir hudMeta (« cap 237° · Réseau ± 12 m »). Boutons Profil/Tracé à 48 dp, « Marquer ma position » en stylePrimary comme sur la maquette 1a, bouton d'orientation libellé « Nord ↑ » / « Cap ↑ » selon directionUp.

### RECH_NAV-06 — Recherche hors ligne limitée aux ouvrages mais présentée comme une copie complète

- **Sévérité** : Majeur
- **Écran** : Recherche - onglets Tout / Ouvrages / Personnes
- **Catégorie** : feedback etats · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Hors ligne, chercher « PE-042 », un village ou un équipement renvoie 0 résultat alors que la donnée est sur le téléphone ; seul un ouvrage de même nom ressort. Le message ne signale pas que la recherche est partielle.

**Impact pour l'agent.** L'agent en zone sans réseau conclut que le point n'existe pas, ou ne retrouve pas la fiche dont il a besoin, là où la recherche hors ligne est justement indispensable.

**Preuve (version 2.12.0).** search/SearchActivity.kt:627-633 et :779-783 : hors ligne, le repli offlineSnapshotResults() ne sert que ALL/WORKS ; shared .../rules/search/SearchRules.kt:26-38 ne renvoie que des résultats de type « ouvrage » (nom, type, village, commune). :667-672 : l'en-tête annonce « N RÉSULTATS · COPIE HORS LIGNE » puis « Aucun résultat. » sans dire la portée. Or GeoRepository / OfflineStore (geoAllEntities, geoNearby) détiennent déjà villages, points d'eau (1 725) et équipements (616) du périmètre (capture 01_accueil). Onglet Personnes : aucun repli (message :631).

**Recommandation.** Créer OfflineGeoSearch dans shared/rules/search (normalisation sans accents comme OfflineWorkSearch) sur geo_entities (villages, points d'eau, équipements, repères) + ouvrages, avec jetons PE/V/EQ. Bandeau ton avertissement : « Recherche hors ligne : ouvrages, villages, points d'eau et équipements de votre périmètre. Les personnes nécessitent le réseau. » État vide : « Aucun résultat dans les données téléchargées - relancez avec le réseau pour une recherche complète. » Ouvrir via la fiche en cache ou renderFallback(). Afficher la date de dernière synchro.

### RECH_NAV-07 — Fiches : ni appeler, ni « Y aller », ni « Voir sur la carte », ni texte copiable

- **Sévérité** : Majeur
- **Écran** : Recherche - fiches détail (point d'eau, village, commune, ouvrage, personne)
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** La fiche d'un abonné, d'une représentante, d'une autorité ou d'un fournisseur affiche le numéro sans pouvoir ni l'appeler ni le copier ; celle d'un point d'eau ou d'un village affiche des coordonnées sans pouvoir s'y rendre. Le parcours Recherche, fiche, carte, guidage est rompu : il faut quitter, rouvrir la carte et retrouver le marqueur (non touchable pour un village, cf. RECH_NAV-01).

**Impact pour l'agent.** Ressaisie manuelle des numéros et absence de chemin court vers l'action n°1 de l'agent (aller sur place) : la fiche est un cul-de-sac.

**Preuve (version 2.12.0).** search/SearchDetailActivity.kt:246-251 et :443-454 : téléphone et coordonnées GPS rendus par text() (TextView non sélectionnable). Aucun ACTION_DIAL ni « tel: » dans l'app (grep ; seul calculator/AdvancedCalculatorActivity.kt:907 utilise geo:). Aucune référence à NavigationTerrainActivity depuis search/ (seul MainActivity la lance), alors que la carte ouvre la fiche avec « Retour à la carte » (:119-126) : le sens inverse n'existe pas. Aucun lien fiche ouvrage vers réparations/interventions (RecentInterventionsActivity.openWork va dans l'autre sens).

**Recommandation.** Barre d'actions épinglée sous le titre (48-56 dp), selon les données disponibles : « Appeler » (Intent.ACTION_DIAL, normalisation 0XX / +261), « Y aller » (extras target_category + target_id lus par NavigationTerrainActivity pour appeler startNavigation à l'ouverture), « Voir sur la carte » (centerOn), « Réparations » (RecentInterventionsActivity filtrée par ouvrage). setTextIsSelectable(true) sur valeurs et coordonnées (S, à faire tout de suite). Mettre aussi « Appeler » dans la feuille d'entité de la carte et en appui long sur les résultats.

### RECH_NAV-08 — Fiches : dump de tous les champs du modèle (un champ = une carte) et diagramme de flux aux étiquettes superposées

- **Sévérité** : Majeur
- **Écran** : Recherche - fiches point d'eau / ouvrage / commune (diagramme de flux)
- **Catégorie** : rendu donnees · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Une fiche point d'eau fait défiler une trentaine de cartes de champs techniques (DiameX, montants, createdat) aux libellés non traduits (« Numerodiamexpaiementdevis », « Createdat »), valeurs brutes (« False », ISO) et doublons, avant ce que l'agent cherche ; sur village/commune, ces cartes passent avant la synthèse « Desservi / habitants ». Dans le diagramme de flux, toute catégorie sous environ 6 % du total chevauche son voisin (centres écartés de moins de 28 dp) : les catégories rares, souvent les plus utiles (non desservi, hors service), sont illisibles ; il faut balayer environ 2 écrans sans repère de défilement ni toucher sur un nœud.

**Impact pour l'agent.** Fiche longue et illisible, information métier noyée sous des champs de facturation ; lecture fausse ou impossible des petites catégories du diagramme.

**Preuve (version 2.12.0).** backend/apps/core/views_mobile_search.py:887-903 : fields = tous les instance._meta.fields (sauf password, signature, photo(s)), en str()/isoformat, libellé = verbose_name ou nom de champ capitalisé. search/SearchDetailActivity.kt:183-194 : une carte d'environ 70 dp par champ non vide ; PointEau compte environ 40 champs (billing/models.py : numerodiamexpaiementdevis, basediamexdevis, montants...). :213-216 date ISO brute ; :518-525 tableaux aplatis « Clé : null » (JSONObject.NULL non filtré) ; booléens « True/False » ; doublon avec la carte FICHE TERRAIN (Abonné/Téléphone/GPS vs « Nom de l'abonné », « Latitude ») ; titre répété en 19 sp (:114) puis 25 sp (:179). Diagramme : FlowDiagramView.kt:43-49 hauteur fixe 380 dp et colonnes de 210 dp (environ 840 dp de large à 3 dimensions pour 368 dp visibles) ; FlowDiagramLayout.kt:135-143 hauteur de nœud = effectif × échelle, sans anti-chevauchement, alors que chaque étiquette occupe environ 28 dp (FlowDiagramView.kt:109-112).

**Recommandation.** Mise en page déclarative par type dans shared/rules/search (DetailLayout : groupe, clé, libellé fr/mg, formateur date / oui-non / Ar / téléphone, visible) ; un groupe = UNE carte à lignes clé/valeur sur deux colonnes (style statCard), champs inconnus masqués sous un « Tous les champs » replié, ou idéalement une liste blanche côté serveur (moins d'octets aussi). Un seul titre (l'en-tête devient le badge de type), ignorer JSONObject.NULL, afficher « il y a 3 j » pour updated_at, mettre la synthèse (badge desservi, cartes) avant les champs. Diagramme : pas vertical minimal de 30 dp entre étiquettes dans FlowDiagramLayout.build (relaxation, test JVM), regrouper les nœuds sous 3 % en « Autres », hauteur 280 dp, repère de défilement, nœud touchable ouvrant la liste des villages.

### RECH_NAV-09 — Carte hors ligne : fond uni jamais rétabli au retour du réseau, aucune zone téléchargeable, palette non adaptée au fond clair en ligne

- **Sévérité** : Majeur
- **Écran** : Navigation terrain - fond de carte
- **Catégorie** : workflow · **Effort** : L
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Si l'écran est ouvert hors réseau (cas normal sur le terrain), le fond reste un rectangle bleu nuit uni, sans route, sans grille, sans échelle, et ne revient jamais à la carte quand le réseau réapparaît ; l'itinéraire exige de toute façon le réseau. En ligne, le fond clair OpenFreeMap reçoit des repères conçus pour fond sombre : le cyan du point d'eau et du point de position ressort à environ 1,5:1. Aucun téléchargement de zone ni indicateur de progression n'existe.

**Impact pour l'agent.** Hors ligne, l'agent n'a que des points flottants sur fond uni, sans repère spatial pour s'orienter ; son point bleu est difficile à retrouver au soleil.

**Preuve (version 2.12.0).** NavigationTerrainActivity.kt:330-340 : loadNavigationStyle n'est appelée qu'au démarrage (:314) et pour le repli unique (:310, offlineFallbackStarted) ; aucun NetworkCallback (grep) ; style choisi par isOnline() et non par le thème, URL en dur (:74, OpenFreeMap liberty, clair). assets/navigation_neutral_style.json : sources vides, un seul calque de fond #07151D (la grille de la maquette 1a et de la conception §3.6 n'existe pas). backend/apps/navigation_terrain/views.py:126 : offline_download_enabled False. Palette fixe de repères pastel (MarkerLayerManager.kt:173-178, NavigationTerrainActivity.kt:1045-1050) alors que res/values/colors.xml:42-45 définit hydria_map_* jamais utilisés ; point de position = cercle cyan de 9 sans liseré (MarkerLayerManager.kt:119-121).

**Recommandation.** 1) registerDefaultNetworkCallback : au retour du réseau, relancer loadNavigationStyle() et remettre offlineFallbackStarted à false (S). 2) Fond neutre utile : graticule discret, échelle, cercles de 100 / 500 m autour de l'utilisateur, nord (S/M). 3) Utiliser hydria_map_* (clair/sombre) et un liseré blanc 2 dp sur repères et point de position ; choisir une variante sombre du style en thème sombre (M). 4) Phase 2 : OfflineManager MapLibre, bouton « Télécharger la zone visible » avec estimation de taille, ProgressBar alimentée par OfflineRegionObserver, Wi-Fi seulement, après décision sur le fournisseur de tuiles (L).

### RECH_NAV-10 — Arrivée et enregistrements : aucune suite proposée et confirmations qui disparaissent en une seconde

- **Sévérité** : Majeur
- **Écran** : Navigation terrain - arrivée, sauvegardes, ligne de statut
- **Catégorie** : feedback etats · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Arrivé à moins de 25 m, l'agent a une boîte « Terminer / Continuer » : rien ne mène à la saisie sur place (relevé du point, fiche, photo, correction GPS), ni son ni vibration. Après « Position enregistrée hors ligne », le message est remplacé par la ligne de statut au fix suivant, souvent en moins d'une seconde : l'agent ne sait pas si l'enregistrement a eu lieu. La feuille d'entité affiche « Synchronisation : synced » et un éventuel conflit apparaît comme le mot « conflict ».

**Impact pour l'agent.** Doute sur la sauvegarde (donc doublons ou captures refaites), parcours interrompu au moment où l'agent a besoin d'enchaîner sur la saisie sur place.

**Preuve (version 2.12.0).** NavigationTerrainActivity.kt:575-581 : à l'arrivée, un AlertDialog « Terminer / Continuer » seulement. :693, :712, :806, :891, :949 : confirmations via updateStatus("...") dans la ligne de statut, réécrite sans message à chaque fix (:542 updateStatus()) ; ligne de 5 informations en une phrase de 12 sp (:1003-1008). HydriaFeedback (son, pulse) utilisé dans MainActivity, Pointage et Calculatrice mais absent de search/ et navigation/. :445 affiche syncState brut (« synced », « pending », « error », « conflict », TerrainDatabase.kt:551) ; aucun repère de la carte ne montre l'état en attente ou en conflit. Textes sans accents (« enregistree », « deplacee », « marque hors ligne »).

**Recommandation.** Remplacer la boîte d'arrivée par une feuille « Vous êtes arrivé : PE-042 » avec actions primaires « Saisir le relevé » (Intent vers MainActivity singleTask avec un extra de point), « Ouvrir la fiche », « Photo », « Corriger le GPS », et « Terminer » ; HydriaFeedback.success() + vibration 200 ms. Pour chaque enregistrement : Snackbar persistant 4 s (« Position enregistrée · 3 en attente »), HydriaFeedback.success(), liseré sur le marqueur tant qu'il est en attente. Découper la ligne de statut en pastilles (précision colorée, réseau, en attente). Traduire syncState : Envoyé / En attente d'envoi / Échec, nouvel essai / Conflit : coordonnée serveur plus récente. Corriger les accents.

### RECH_NAV-11 — Indicateurs hors écran masqués sous les panneaux (haut, bas et droite)

- **Sévérité** : Majeur
- **Écran** : Navigation terrain - indicateurs de bord
- **Catégorie** : ergonomie · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Un indicateur placé à 54 dp du bord haut tombe sous le bandeau, un indicateur du bas tombe sous « Marquer ma position », et un indicateur de l'est tombe sous la colonne ◎ / N / + / −. Seul le bord gauche est libre. Le principe « destination toujours visible » de la doc §3.5 est donc faux sur téléphone ; le toucher est de plus capté par les panneaux.

**Impact pour l'agent.** Les flèches vers les points proches ou la cible sont invisibles dans la plupart des directions : la fonction « où est le prochain point » ne sert pas.

**Preuve (version 2.12.0).** NavigationTerrainActivity.kt:178 (EdgeIndicatorsView ajouté juste après la carte, donc sous top :204, tools :214, hud :292, actions :295). EdgeIndicatorsView.kt:30 : marge uniforme de 54 dp ; shared GeoMath.projectBearingToEdge (GeoMath.kt:46-68) réduit le rectangle de façon uniforme. Panneau haut d'environ 135 dp (:180-206), barre d'actions de 70 dp + 8 dp de marge (:295), colonne d'outils de 54 dp à droite et centrée (:214).

**Recommandation.** Calculer un rectangle de sécurité à partir des vues superposées (top.bottom, actions.top, tools.left, hud.top, mesurés après layout) et le passer à projectBearingToEdge sous forme d'insets par bord (au lieu du padding uniforme) ; ajuster les tests de GeoMath. En complément, placer EdgeIndicatorsView au-dessus de la carte mais sous les seuls panneaux non couverts.

### RECH_NAV-12 — Résultats : jeton « OU » pour 8 types sur 14, 13 puces de filtre par défaut, pagination sans retour

- **Sévérité** : Mineur
- **Écran** : Recherche - liste de résultats
- **Catégorie** : ergonomie · **Effort** : S
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Le jeton de type, ce que la refonte voulait pour lire une liste mixte d'un coup d'œil, est ambigu pour plus de la moitié des types. L'écran ouvre sur 13 puces défilables dont chacune retire une catégorie au toucher. Après « Page suivante », la liste reste positionnée en bas et il n'y a aucun retour ; l'état vide ne propose ni élargissement des filtres ni réseau. Le clavier ne s'ouvre pas et l'autocorrection du clavier peut modifier des noms propres malgaches.

**Impact pour l'agent.** Lecture plus lente de la liste, filtres retirés par erreur, perte du contexte en pagination.

**Preuve (version 2.12.0).** search/SearchActivity.kt:745-759 searchTypeToken : seuls point_eau, village, equipement, commune, intervention et personnes ont un jeton ; representant, autorite, tiers, fournisseur, designation, modalite, carte_sociale et planning tombent sur « OU » (type renvoyé par views_mobile_search.py:40-44) ; PE, CO, OU et initiales sont tous cyan. :67 et :580-584 : 13 types sélectionnés par défaut donc 13 puces « Libellé ✕ » (maquette 5b : une seule puce « 5 catégories »). :677-681 : « Page suivante » seulement, sans précédent, sans remise en haut du ScrollView. :672 : « Aucun résultat. » sans piste. :166-184 : aucun inputType ni imeOptions, pas de focus automatique.

**Recommandation.** Table TYPE_META complète (14 types : sigle, teinte distincte, libellé) partagée avec la fiche ; remplacer les 13 puces par une puce unique « 13 catégories » qui ouvre le filtre (en n'affichant des puces retirables que pour les écarts par rapport au défaut) ; afficher « page 2 / 5 », ajouter « Page précédente » et remonter le scroll à chaque changement de page ; état vide avec « Retirer les filtres » ; inputType TEXT_FLAG_NO_SUGGESTIONS | TEXT_VARIATION_FILTER, imeOptions IME_ACTION_SEARCH, requestFocus + clavier à l'ouverture.


## Calculatrice et volumétrique

_Audit initial sur la version 2.12.0._

**Synthèse du domaine.** Domaine audité : la calculatrice avancée (6 onglets) et le workflow volumétrique (facturation, encaissement, pointage DiameX, impression). Le métier est solide : calcul d'argent en BigDecimal avec serveur autoritaire, file persistante idempotente, récapitulatif figé, protection contre le double encaissement. En revanche les deux écrans n'ont pas bénéficié de la même refonte. L'onglet Calculs est abouti dans sa typographie et son pavé, mais sa liste est inutilisable sur téléphone et deux actions détruisent des données sans filet (AC, suppression de ligne). Les autres onglets restent des formulaires à libellés éphémères. L'écran Volumétrique est du texte brut en français sans charte : montants non formatés, statuts sans couleur, total et bouton de validation qui défilent avec la liste, saisie de date libre, synchronisation qui s'arrête au premier refus. La facture A4 imprimée est très en retrait du gabarit web. Les calculatrices et le workflow volumétrique sont enfouis dans le menu « Outils et session » (MainActivity.kt:5112-5115), à côté de « Se déconnecter ». Le coût de lecture SQLite par case cochée (VolumeActivity.updateSummary, rows() puis entries()) n'a pas été mesuré : à vérifier sur un appareil d'entrée de gamme avec un lot de 300 à 500 factures.

**À préserver :**

- Onglet Calculs refondu avec soin : ligne active cadrée cyan 2 dp, chiffres en Roboto Mono, retour haptique et sonore sur les touches, hauteur des touches adaptée à l'écran (CalculatorDeviceRules.keyHeightDp), jetons « L1 · 210 » pour référencer une ligne, 12 messages d'erreur précis, parseur fermé qui accepte virgule et point.
- Calculatrice entièrement locale et persistante par compte, entièrement traduite en malgache (159 chaînes values-mg), avec confirmation avant chaque effacement d'onglet et un carnet de caisse nommé réutilisable.
- Onglet GPS bien pensé pour le terrain : captage de la meilleure position (fraîcheur inférieure à 2 min, objectif 20 m, 30 s maximum, bouton « Utiliser cette position »), copie lat/long/paire, carte avec style neutre hors ligne en repli.
- Workflow volumétrique aligné sur le site (trois étapes, mois de facturation = mois suivant le relevé) avec ouvrage et mois choisis une seule fois.
- Sécurité de l'argent bien conçue : factures encaissées ou pointées non sélectionnables, version de devis vérifiée (« Conflit : le relevé ou le tarif a changé »), journaux autorisés côté serveur, opérations rejouables sans doublon (UUID idempotent).
- Hors ligne rigoureux : file persistante, récapitulatif d'encaissement figé enregistré dans la même écriture locale, historique local des 200 dernières opérations, clôture manuelle d'un refus exigeant une note d'au moins 10 caractères.
- Récapitulatif A4 utile au contrôle : grille IDXLS (noir pour le lot, gris pour les déjà pointés, lignes vides omises), pagination automatique, état affiché (local, synchronisé, refusé, clôturé) ; QR sur chaque facture avec saisie manuelle en repli.

### CALC_VOL-01 — Date d'encaissement en texte libre, sans garde-fou, et journal sans valeur par défaut

- **Sévérité** : Majeur
- **Écran** : Volumétrique › Encaissement › dialogue « Date et journal d'encaissement »
- **Catégorie** : workflow · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** La date qui part dans la ligne DiameX temporaire (recette 707401) se saisit dans un champ texte brut. Un format « 19/10/2026 » ou « 2026-1-5 » lève une exception dont le message anglais brut (« Text '…' could not be parsed… ») s'affiche dans un toast. Une année mal tapée (2025-10-19) passe tous les contrôles locaux ; une date future n'est refusée par le serveur qu'à la synchronisation, donc après l'impression du récapitulatif. Le journal est un Spinner brut dont la première valeur (« 00PERS · Caisse personnelle ») est choisie par défaut, sans mémoire du journal habituel de la base.

**Impact pour l'agent.** Une recette peut être datée dans la mauvaise période comptable, ou refusée (409) après coup alors que l'argent est encaissé et le récapitulatif remis, ce qui force la procédure de vérification manuelle. Un tap distrait sur le Spinner suffit à poster dans le mauvais journal.

**Preuve (version 2.12.0).** VolumeActivity.kt:359-371 (collect : EditText hint « Date d'encaissement AAAA-MM-JJ », LocalDate.parse(date.text) sans contrôle, Spinner de journaux non stylé, première entrée retenue d'office) ; VolumeActivity.kt:127 (safely affiche e.message) ; backend/apps/billing/views_mobile_volume.py (sync_operation, action collect : « Date future interdite » vérifiée seulement à la synchronisation).

**Recommandation.** Dans collect() : remplacer l'EditText par un DatePickerDialog (défaut = aujourd'hui, maximum = aujourd'hui), ajouter un contrôle explicite avant enqueue (date ≤ aujourd'hui, avertissement si l'écart avec aujourd'hui dépasse 31 jours), mémoriser le dernier journal dans OfflineStore et le présélectionner. Styler le Spinner avec HydriaUi.styleSpinner et afficher « code · nom » du journal dans la boîte de confirmation confirmBatch. Intercepter DateTimeParseException pour un message français (« Date invalide »).

### CALC_VOL-02 — Synchronisation de l'écran : le premier refus bloque les suivants et supprime l'affichage du récapitulatif

- **Sévérité** : Majeur
- **Écran** : Volumétrique › Outils › Synchroniser, et validation d'un encaissement en ligne
- **Catégorie** : feedback etats · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Une opération refusée reste dans la file en statut error et passe en tête à chaque synchronisation. Dans l'écran Volumétrique, la boucle s'arrête sur ce premier échec : les opérations plus récentes ne partent pas, et après « Valider l'encaissement » le récapitulatif n'apparaît pas ; le toast affiche l'erreur de l'ancienne opération. Seule la synchronisation globale de l'écran principal contourne ce blocage. La seule issue pour évacuer l'opération fautive est Historique › Vérification manuelle, et seulement pour un 409 (une erreur 400 ou 500 persistante n'a aucune issue dans l'écran).

**Impact pour l'agent.** L'agent vient d'encaisser, ne voit pas son récapitulatif et lit un message d'erreur d'une autre opération : il peut croire que son encaissement a échoué, le refaire, ou remettre un reçu sans récapitulatif. Les autres opérations restent coincées derrière l'opération refusée.

**Preuve (version 2.12.0).** VolumeActivity.kt:384-386 (boucle for sur repository.pending() ; check(result.successful) lève à la première erreur et after() n'est jamais appelé) ; VolumeActivity.kt:355 (showRecap uniquement dans after) ; SyncQueue.sq selectPendingOrError (statuts pending ET error, ORDER BY createdAt ASC) ; VolumeRepository.syncOne + VolumeResultGateway.recordFailure (un 409 garde l'opération dans la file, statut error) ; à comparer avec QueueSyncEngine.run (shared) qui poursuit après un échec.

**Recommandation.** Dans synchronize() : traiter chaque élément dans un try/catch, retenir le premier message d'erreur, poursuivre la file (comme QueueSyncEngine.run) puis appeler after() dans tous les cas pour que showRecap s'affiche même si la synchronisation a échoué. Préfixer l'erreur par l'ouvrage, le mois et le total de l'opération concernée. Séparer dans le statut de l'écran (VolumeActivity.render, ligne status) le compteur « en attente » du compteur « bloquées ».

### CALC_VOL-03 — Encaissement et Pointage : total, compteur et bouton de validation défilent avec la liste ; comparaison sur deux colonnes de 300 dp

- **Sévérité** : Majeur
- **Écran** : Volumétrique › Encaissement et Pointage DiameX
- **Catégorie** : ergonomie · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Le texte « N facture(s) sélectionnée(s) · total Ar » et l'écart DiameX sont un TextView du corps défilant, et le bouton « Valider l'encaissement » ou « Pointer… » est avant la liste : contrairement à la documentation, rien n'est visible en permanence. Aucun « tout cocher » ni recherche par IDXLS ou abonné, alors que le Pointage demande de retrouver à la main le sous-ensemble de relevés dont la somme égale une ligne DiameX. Sur 424 dp, les deux colonnes de 300 dp ne tiennent pas côte à côte : on coche à gauche, on glisse à droite pour choisir la ligne, on remonte pour lire l'écart. Le bouton Pointer est désactivé tant que les montants diffèrent mais garde exactement l'apparence d'un bouton actif : un tap ne fait rien, et le message « Le total des relevés doit correspondre » ne peut jamais s'afficher.

**Impact pour l'agent.** Sur un lot de dizaines ou centaines de factures, l'agent coche en bas puis remonte pour vérifier le total et valider ; au Pointage il perd le fil entre les trois zones et croit le bouton cassé. Risque de valider sans avoir relu le total.

**Preuve (version 2.12.0).** VolumeActivity.kt:86 (body dans un ScrollView), 266 (summary ajouté à body), 276 et 289 (boutons principaux placés avant la liste) ; docs/WORKFLOW_VOLUMETRIQUE_2.9.1.md:26 (« visibles en permanence ») ; VolumeActivity.kt:294-297 et 312 (colonnes de max(300 dp, écran/2−20 dp) dans un HorizontalScrollView) ; VolumeActivity.kt:233 (pointButton.isEnabled) avec HydriaVisuals.kt:287-304 (secondaryButton sans état désactivé) ; VolumeActivity.kt:216-234 (chaque case recalcule rows() puis entries(), donc N lectures SQLite par tap).

**Recommandation.** Sortir summary et le bouton principal du ScrollView vers une barre basse fixe (sous le ScrollView dans root) : « 12 factures · 125 000 Ar » + bouton ; au Pointage y ajouter « Écart 0 Ar » coloré (HydriaUi.toneColor SUCCESS ou ERROR). Ajouter « Tout cocher / Tout décocher » et un champ de recherche IDXLS ou abonné au-dessus de la liste. Sur téléphone, remplacer les deux colonnes par deux sous-onglets « Relevés » et « Ligne DiameX » partageant la barre fixe (HydriaWindow.of(this).isTablet garde le côte à côte). Gérer l'état désactivé dans HydriaUi.primaryButton/secondaryButton (texte textMuted, filet atténué). Mettre en cache rows() et pending() pendant la sélection.

### CALC_VOL-04 — « AC » de l'en-tête efface aussi les cahiers de caisse enregistrés et porte le même nom que « AC » du pavé

- **Sévérité** : Majeur
- **Écran** : Calculatrice › en-tête et pavé numérique
- **Catégorie** : ergonomie · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Deux commandes « AC » aux effets opposés : celle du pavé vide la ligne active, celle de l'en-tête supprime toute la ligne calculator_state, donc les lignes de tous les onglets mais aussi les « cahiers enregistrés » (jusqu'à 200 cahiers nommés par l'utilisateur). La boîte de dialogue ne parle que de « brouillons » et ne cite pas les cahiers. La touche AC du pavé est un ajout hors maquette.

**Impact pour l'agent.** Perte irréversible (aucune sauvegarde serveur) de carnets que l'agent a explicitement nommés et enregistrés, déclenchée par une confusion probable entre les deux AC.

**Preuve (version 2.12.0).** AdvancedCalculatorActivity.kt:116 (bouton AC d'en-tête → confirmClearMemory, ligne 1270) ; ligne 1179 et 1188-1200 (touche AC du pavé = vider l'expression active) ; res/values/strings.xml:21 (« Effacer les brouillons de la calculatrice… ») ; shared CalculatorModels.kt:50-75 (namedCashBooks fait partie de l'état sérialisé) ; TerrainDatabase.kt:253-255 (delete de la ligne calculator_state) ; maquette 5c (AC seulement en haut à droite, pas de touche AC dans le pavé).

**Recommandation.** Renommer le bouton d'en-tête « Tout effacer » et épargner les cahiers : clearMemory() = CalculatorState().copy(namedCashBooks = ancien état), ou lister dans la boîte « N cahiers enregistrés seront supprimés ». Libeller la touche du pavé « C » (ou la retirer pour coller à la maquette). Éventuellement déplacer l'action globale dans un menu ⋮.

### CALC_VOL-05 — Supprimer une ligne de calcul décale tous les Ln du dessous sans réécrire les références, sans confirmation ni annulation

- **Sévérité** : Majeur
- **Écran** : Calculatrice › Calculs
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Les références sont positionnelles. Si L1 est supprimée, « L2 » dans une expression pointe maintenant sur l'ancienne L3 : le résultat change en silence, ou devient « La ligne référencée n'existe pas » plus bas. Le bouton « × » fait 44 × 40 dp (sous les 48 dp) dans le coin de la carte tapable, sans confirmation ni annulation.

**Impact pour l'agent.** Un nettoyage anodin d'une ligne intermédiaire fausse tous les résultats en aval d'un calcul d'argent (ex. coût total = L1 × L2) sans signal visible.

**Preuve (version 2.12.0).** AdvancedCalculatorActivity.kt:1262-1266 (deleteLine : removeAt(index) puis repository.save, expressions inchangées) ; ligne 508 (bouton « × » fixed(44, 40) dans l'en-tête de chaque carte, supprime sans confirmation) ; shared ExpressionCore.kt parseReference (référence = numéro de position, referencedIndex = lineNumber - 1).

**Recommandation.** Dans deleteLine : réécrire les expressions suivantes (regex L(\d+) : décrémenter les numéros supérieurs à l'index supprimé, marquer en erreur celles qui visent la ligne supprimée), ou refuser la suppression si une ligne postérieure y fait référence. Passer le bouton à 48 × 48 dp et proposer un Snackbar « Ligne supprimée · Annuler ». Ajouter un test dans CalculatorWorkbookCoreTest.

### CALC_VOL-06 — Le « % » divise par 100 : « 5000 + 7% » donne 5 000,07 sans aucun avertissement

- **Sévérité** : Majeur
- **Écran** : Calculatrice › Calculs (touche % du pavé)
- **Catégorie** : rendu donnees · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Le pourcentage est un postfixe qui divise par 100. Pour l'utilisateur de calculette, « A + B% » vaut A × (1 + B/100). Ici « 18500 + 7% » donne 18 500,07 et « 120000 − 10% » donne 119 999,9 ; aucune erreur n'est signalée. La taxe communale de 7 %, la remise ou la majoration sont pourtant le cas d'usage le plus courant d'une calculatrice métier.

**Impact pour l'agent.** Résultat faux silencieux sur des calculs d'argent, lu comme juste puisqu'aucune erreur n'apparaît.

**Preuve (version 2.12.0).** shared ExpressionCore.kt parsePostfix (value / hundred) ; ExpressionCoreTest.kt:22 (« (2+3)*200% » = 10) ; AdvancedCalculatorActivity.kt:1177 (touche % en première rangée) ; aucune aide ni exemple dans strings.xml.

**Recommandation.** Dans ExpressionCore.parseExpression : lorsque l'opérande droit d'un + ou d'un − est un pourcentage pur, l'interpréter comme part de l'opérande gauche (A + B% = A + A×B/100) ; conserver la division par 100 ailleurs (« 200 × 15% », « 50% » seul). Ajouter les cas aux tests ExpressionCoreTest (le module est partagé avec le Desktop). À défaut, afficher sous la ligne l'expression interprétée (« 18 500 + 0,07 ») ou retirer la touche.

### CALC_VOL-07 — Montants bruts « 125000.00 Ar » à l'écran et sur la facture, et « null Ar » pour les relevés en erreur

- **Sévérité** : Majeur
- **Écran** : Volumétrique (toutes étapes), facture A4, récapitulatif d'encaissement
- **Catégorie** : rendu donnees · **Effort** : S · quick win
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Tous les montants du workflow sont affichés tels que le serveur les sérialise : « 1250000.00 Ar », sans séparateur de milliers ni alignement, en police proportionnelle. Les relevés dont le calcul échoue (montant null) affichent « null Ar » à côté du message d'erreur. La facture remise à l'abonné imprime « À PAYER : 12500.00 Ar », alors que le site imprime « 12 500 Ar ». Les écarts du pointage s'affichent sans signe lisible (« -1500.00 »).

**Impact pour l'agent.** Un montant à 7 chiffres sans séparateur se lit mal en plein soleil (erreur d'un zéro) ; l'abonné voit des centimes d'ariary inexistants ; « null Ar » ressemble à un bug.

**Preuve (version 2.12.0).** VolumeActivity.kt:230, 249, 258, 320, 345, 380 (interpolations de BigDecimal et de optString) ; VolumePrinter.kt:71 (« À PAYER : ${invoice.getString("montant")} Ar ») ; VolumeRecapPrinter.kt:80 et 89 ; backend/apps/billing/views_mobile_volume.py:76 (format(amount.quantize(0.01), 'f') et None si montant absent) ; VolumeActivity.kt:258 (optString("montant", "—") : org.json d'Android renvoie la chaîne « null » pour un JSON null) ; backend/static/js/print_factures_a4.js:17 (le site formate en entier avec séparateur fr-FR).

**Recommandation.** Créer un helper unique (Ariary.format(String ou BigDecimal) : arrondi à l'unité, séparateur fine insécable, suffixe « Ar ») dans HydriaVisuals ou shared et l'appliquer aux ~12 sites de VolumeActivity, VolumePrinter et VolumeRecapPrinter. Remplacer optString("montant", "—") par row.isNull("montant"). Afficher les montants avec HydriaType.numeral, alignés à droite, et aligner MONEY_FORMAT de la calculatrice (0 décimale quand le montant est entier).

### CALC_VOL-08 — Facture A4 mobile très en retrait du gabarit web : pas d'en-tête organisation, ni responsable, ni consignes de paiement, « N° Sans numéro » et mention interne imprimée

- **Sévérité** : Majeur
- **Écran** : Volumétrique › Facturation › Imprimer · A4/PDF
- **Catégorie** : coherence · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Le document remis à l'abonné ne reprend ni l'identité de l'organisation, ni le contact du responsable, ni le détail des volumes et des compteurs, ni les consignes de paiement bilingues du site ; il est entièrement en français. Il porte « N° Sans numéro » quand la base n'a pas de numéro, et la bannière « VALIDATION HORS LIGNE · EN ATTENTE DE SYNCHRONISATION » dans le cas normal d'une impression hors ligne. Le QR n'est accompagné d'aucun identifiant lisible (l'IDXLS n'est pas imprimé), ce qui rend la saisie manuelle de repli inopérante pour les factures sans numéro. Une facture occupe toute une page A4 (environ 60 % de vide).

**Impact pour l'agent.** Document peu crédible et peu informatif pour l'abonné, qui ne sait ni qui contacter ni comment payer ; deux gabarits différents (site et mobile) pour la même facture ; 100 abonnés = 100 feuilles dans un contexte rural où le papier est coûteux.

**Preuve (version 2.12.0).** VolumePrinter.kt:55-73 (HYDRIA, N°, ouvrage, abonné, index, À PAYER, taxe ; une page A4 par facture, setPageCount(frozen.size) ligne 27) ; VolumePrinter.kt:57 (« VALIDATION HORS LIGNE · EN ATTENTE DE SYNCHRONISATION » imprimé sur la facture) ; backend/apps/billing/views_mobile_volume.py:68 (numero = « Sans numéro » si numero_facture vide) et print_fields + pack.impression.organisation (fournis mais jamais lus dans volume/*.kt, utilisés par le client Desktop) ; backend/static/js/print_factures_a4.js:46-47, 149-177, 186-193 (logo/nom organisation, NIF/STAT, responsable et téléphone, volumes consommé / carte sociale / non facturé, consignes de paiement MVola en malgache).

**Recommandation.** Réutiliser le payload serveur déjà fourni (pack.impression.organisation et facture.impression : responsable, segments de compteur) pour reproduire print_factures_a4.js : en-tête organisation, responsable et téléphone, volumes détaillés, mentions de paiement bilingues MG/FR (chaînes dans values-mg). Retirer l'état de synchronisation du papier (le garder à l'écran) ; imprimer l'IDXLS à côté du N° (« Réf. abonné ») ; proposer 2 factures par feuille ou un format ticket 80 mm.

### CALC_VOL-09 — « Confirmer l'impression réalisée » : bouton verrouillant, indépendant de l'impression réelle, et réimpression possible seulement par lot entier

- **Sévérité** : Majeur
- **Écran** : Volumétrique › Facturation
- **Catégorie** : workflow · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Le bouton « Confirmer l'impression réalisée du lot » est actif dès l'affichage du lot, que l'impression ait été lancée, terminée ou annulée. Un tap suffit à passer tout le lot en « imprimé », ce qui interdit tout recalcul ultérieur (refus serveur « Facture verrouillée »). Le dialogue de confirmation ne mentionne pas ce caractère irréversible, contrairement au site. Pour réimprimer une seule facture perdue, il faut imprimer à nouveau tout le lot et choisir la page dans le dialogue système, sans mention « Duplicata ».

**Impact pour l'agent.** Impression annulée ou imprimante injoignable, puis confirmation : les factures sont verrouillées alors qu'aucun papier n'est parti, et une erreur de tarif découverte ensuite n'est plus corrigeable sans intervention serveur.

**Preuve (version 2.12.0).** VolumeActivity.kt:255-256 (Imprimer et Confirmer ajoutés l'un sous l'autre, sans dépendance) ; VolumeActivity.kt:333-338 (printInvoices(valid) : tout le lot, déjà imprimées incluses) et 339-358 (dialogue : « N factures · total » et « Conservation locale… », aucun avertissement de verrouillage) ; VolumePrinter.kt:12-30 (print() ne renvoie rien : ni PrintJob ni état de fin) ; backend/apps/billing/views_mobile_volume.py (action printed : facture_imprimee = True ; validate refusé avec « Facture verrouillée ») ; CLAUDE.md, section Facturation volumétrique (le site prévient « ne pourront plus être recalculées »).

**Recommandation.** Mémoriser le lancement d'une impression (PrintManager.getPrintJobs / PrintJob.isCompleted) et n'activer « Confirmer » qu'ensuite, ou proposer la confirmation automatiquement à la fin du job. Reprendre dans la boîte le texte d'avertissement du site (« irréversible : plus de recalcul ») avec le nombre de factures. Exclure par défaut les déjà imprimées du lot et ajouter une action « Réimprimer cette facture » depuis sa ligne, avec filigrane « DUPLICATA ».

### CALC_VOL-10 — Onglet Calculs sur téléphone : les lignes passées ne sont pas compactes, la liste n'a de place que pour moins d'une carte

- **Sévérité** : Majeur
- **Écran** : Calculatrice › Calculs
- **Catégorie** : ergonomie · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Estimation d'après les constantes du code (aucune capture de la calculatrice dans le lot) : sur 424 × 948 dp, environ 690 dp sont occupés par des éléments fixes, il reste 190 à 250 dp pour la liste, soit moins que la carte de la ligne active (≈ 222 dp). On ne voit donc ni les lignes précédentes ni leurs résultats, contrairement à la maquette qui montre deux lignes passées compactes au-dessus de la ligne active. Les boutons « Ajouter » (doublon de « = Ligne suivante »), « Recalculer » (sans effet visible) et « Vider » consomment 62 dp. L'alpha 0,65 réduit encore le contraste des résultats passés au soleil. Chaque touche reconstruit toutes les cartes.

**Impact pour l'agent.** Les calculs enchaînés (L1 × L2) se font à l'aveugle : résultat intermédiaire invisible, défilement permanent, jetons de référence sans contexte.

**Preuve (version 2.12.0).** AdvancedCalculatorActivity.kt:491-548 (calculationCard identique pour toutes les lignes : badge + ×, champ Libellé 50 dp, champ Expression 52 dp, résultat ; seuls alpha 0,65 et la taille du résultat changent) ; 351-389 (renderCalculations : en-tête 72 dp, onglets 58, boutons 62, bande de références 56, pavé ≈ 6×56+32) ; CalculatorDeviceRules.kt:keyHeightDp (56 dp pour un écran de 948 dp) ; ligne 1268 (« Recalculer » = save, déjà fait à chaque touche) ; ligne 1240-1247 (chaque touche : save complet puis renderContent) ; maquette 5c-telephone-calculatrice.png (deux lignes passées sur une seule rangée chacune).

**Recommandation.** Pour les lignes passées, construire une rangée compacte de 52 dp (« L1 · libellé · expression tronquée · résultat mono à droite ») en réutilisant la structure de calculationTableRow sans EditText, tap = activateLine ; réserver les champs Libellé et Expression à la ligne active. Déplacer Ajouter/Recalculer/Vider dans un menu ⋮ (ou supprimer Recalculer et Ajouter). Ne reconstruire que la ligne active à chaque touche. Supprimer l'alpha sur le texte des résultats.

### CALC_VOL-11 — Onglets Salaire, Devis, Total, Caisse : libellés qui disparaissent à la saisie, nouvelle ligne invisible après « Ajouter », typographie hors charte

- **Sévérité** : Majeur
- **Écran** : Calculatrice › Salaire / Devis / Total / Caisse
- **Catégorie** : coherence · **Effort** : M
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Contrairement à l'onglet Calculs (cartes à filet, Roboto Mono, résultat vert à droite), ces onglets sont restés des formulaires génériques en police par défaut. Les libellés sont de simples hints qui s'effacent dès qu'on tape : « Entrée » et « Sortie » côte à côte deviennent deux nombres sans nom ; « Personnes à charge » (valeur « 0 ») et « Heures de nuit » (valeur « 56 ») sont préremplis donc affichés sans libellé. Après « Ajouter » (Devis, Total, Caisse), la liste est recréée en haut : la nouvelle carte (≈ 218 dp, trois par écran) est sous la ligne de flottaison, rien ne semble s'être passé et on retape le bouton. Une suppression remet aussi le défilement en haut. Les résultats du Salaire sont 16 lignes de poids égal : « Net obtenu » est la troisième, les cinq majorations à 0 sont affichées.

**Impact pour l'agent.** Mauvaise lecture de ce qu'on a saisi (risque d'inverser entrée et sortie en caisse), création de lignes vides en rafale, et résultat clé du simulateur noyé.

**Preuve (version 2.12.0).** HydriaVisuals.kt:453-462 (styleInput : hint seul, pas de libellé flottant) ; AdvancedCalculatorActivity.kt:590-600 (Quantité / Prix unitaire), 653-659 (Date, Désignation, Montant), 723-735 (Entrée / Sortie), 212-218 ; SalaryInputRules.kt (SalaryDraft : dependents = "0", nightHours = "56") ; AdvancedCalculatorActivity.kt:559-562, 619-622, 686-689 (Ajouter → renderContent, nouveau ScrollView sans scrollTo ni requestFocus) ; ligne 1278 (label() sans HydriaType) et 552, 617, 684 (montants en police par défaut) ; lignes 289-318 (16 lignes de résultat salarial identiques).

**Recommandation.** Ajouter un libellé persistant au-dessus de chaque champ (HydriaUi.overline : « QUANTITÉ », « ENTRÉE (Ar) », « SORTIE (Ar) »). Après Ajouter : scrollView.post { fullScroll(FOCUS_DOWN) } puis requestFocus sur le premier champ de la nouvelle carte ; mémoriser scrollY avant une suppression. Utiliser HydriaType.display pour label() et HydriaType.numeral pour tous les montants, avec le net et le brut en carte accentuée (HydriaUi.card(emphasized)) et masquage des majorations nulles.

### CALC_VOL-12 — Écran Volumétrique construit hors refonte : statuts en texte brut, chaînes en dur sans malgache, erreurs d'exception affichées

- **Sévérité** : Mineur
- **Écran** : Volumétrique (toutes étapes)
- **Catégorie** : coherence · **Effort** : L
- **Statut** : Vérifié en 2.12.0 (relecture de l'auditeur)

**Constat.** Une erreur de calcul, une facture déjà encaissée, « Validée · non pointée » et « À facturer » se distinguent seulement par une ligne de texte de même couleur : la refonte posait pourtant que « la couleur porte l'urgence ». Les lignes non sélectionnables ne sont pas atténuées (seule la case est grisée). Tous les textes (étapes, boutons, dialogues, impression, jargon « Conservation locale, puis validation serveur ») sont en français en dur, non traduisibles en malgache. Le champ ouvrage invite à laisser « vide = tous » pour les trois étapes ; en Encaissement en ligne cela produit une erreur d'exception brute (« No value for factures »). L'historique liste « collect · error · 12 facture(s) » sans date, ouvrage ni total, avec des codes techniques.

**Impact pour l'agent.** Lecture lente d'une liste de dizaines de lignes uniformes, anglais technique dans les erreurs, historique inexploitable pour retrouver l'encaissement refusé, et écran inaccessible aux agents qui travaillent en malgache.

**Preuve (version 2.12.0).** VolumeActivity.kt:257-262 et 316-326 (trois lignes de texte dans HydriaUi.card, pas de Tone, chip, accentedCard ni taskRow) ; VolumeWorkflowGateway.statusLabel (texte seul) ; 0 occurrence de R.string dans volume/*.kt alors que calculator/ dispose de 159 chaînes malgaches ; VolumeActivity.kt:120-125 (boutons WRAP_CONTENT alignés à gauche) ; VolumeActivity.kt:70 et 193-198 (« vide = tous » accepté en Encaissement) avec backend/apps/billing/views_mobile_volume.py:168-171 (sans ouvrage, le serveur ne renvoie que la liste d'ouvrages, donc savePack lève « No value for factures ») ; VolumeActivity.kt:394 (historique : codes d'action bruts « collect », « point »).

**Recommandation.** Remplacer les lignes par un composant de la charte (HydriaUi.taskRow ou accentedCard avec Tone SUCCESS, WARNING, ERROR, NEUTRAL, montant en mono à droite) et atténuer les lignes non sélectionnables. Extraire les chaînes dans strings.xml et values-mg. Dans l'historique, afficher « Encaissement · Ouvrage · 10/2026 · 125 000 Ar · Refusé ». Retirer « vide = tous » ou aligner le serveur ; boutons pleine largeur. Enrichir safely() pour traduire les exceptions courantes.
