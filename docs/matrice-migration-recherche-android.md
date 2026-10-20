# Matrice de migration Recherche Web → Hydria Android

Cette matrice ne présente pas le socle actuel comme une migration terminée. `Vérifié` signifie qu'un test automatisé ou une compilation a confirmé le comportement ; `Implémenté` signifie que le code existe mais que la parité complète demande encore des scénarios métier.

| ID | Fonction Web | API Android | Écran Android | Cache/hors ligne | Test attendu | Statut |
|---|---|---|---|---|---|---|
| M-01 | recherche ≥ 2 caractères | `/recherche/api/mobile/search/` | Tout | requête cachée | 0/1/2 caractères | Implémenté |
| M-02 | délai 500 ms, Entrée, bouton | idem | Tout | n/a | instrumentation UI | Implémenté |
| M-03 | 14 catégories | `types` CSV | dialogue multichoix | choix conservé à rotation | chaque type | Implémenté |
| M-04 | Planning désactivé par défaut | `default_types` | Tout | état local | démarrage frais | Implémenté |
| M-05 | tout sélectionner/désélectionner | contrat inchangé | filtre catégories | état local | boutons du dialogue | Partiel : désélection globale disponible |
| M-06 | pagination/total par type | `page`, `page_size`, `counts_by_type`, `has_next` | page suivante | page cachée | pages 1+n | Implémenté, page bornée à 50 |
| M-07 | carte résultat | champs Web + `actions`, `web_url` | carte native | JSON caché | photo/absence photo | Partiel : images distantes différées |
| M-08 | retour et état | activité dédiée + état sauvegardé | Tout | cache SQLite | rotation/retour | Implémenté |
| M-09 | annuaire six types | `/recherche/api/mobile/personnes/` | Personnes | requêtes consultées | six types | Implémenté |
| M-10 | statuts personnes | `statut` | filtre personnes | requête cachée | actif/inactif/tous | Implémenté |
| M-11 | compteurs/pagination annuaire | réponse Web existante | Personnes | page cachée | compteurs/pages | Implémenté côté contrat, affichage compteurs détaillé à poursuivre |
| M-12 | aperçu enrichi personne | `/personnes/{type}/{id}/` | fiche commune | fiche cachée | six aperçus | API ajoutée, UI riche à poursuivre |
| M-13 | modification nom/téléphone | `/personnes/{type}/{id}/modifier/` | fiche future | file future | autorisé/refusé/nom vide | API ajoutée, UI bloquée par matrice de droits |
| M-14 | recherche ouvrages | `/recherche/api/mobile/ouvrages/` | Ouvrages | snapshot + cache | nom/type/village | Implémenté |
| M-15 | périmètre ouvrages | serveur `_accessible_intervention_ouvrages` | badge périmètre | même snapshot | UUID forgé | Implémenté |
| M-16 | filtres géographiques | paramètres région/district/commune/employé + endpoint filtres | dialogue Ouvrages | cache par clé | filtres combinés | Implémenté |
| M-17 | regroupement géographique | champs région/district/commune | groupes repliables sur la page chargée | cache | repli/dépli | Implémenté |
| M-18 | indicateurs ouvrage | fiche mobile ouvrage : points/équipements, coordonnées manquantes, interventions et échéances | section Détails opérationnels | fiche consultée en cache | ouvrage avec relations directes et via PlanningDetail | Implémenté sur la fiche ouvrage |
| M-19 | dernières interventions | `/recherche/api/mobile/interventions/`, options/modification Web partagées avec authentification mobile, actions `marquer-terminee`, `reporter`, `supprimer` | édition date/statut/employé/cible/activité ; boutons selon autorisations ; confirmation renforcée pour suppression | pages consultées ; actions en ligne uniquement | tri/statuts/autres bases/combinaisons cible-activité/date future/directeur | Implémenté |
| M-20 | médias intervention | `attachments` normalisés | compteur cliquable, galerie d’images et ouverture vidéo via lecteur Android | métadonnées et données des pages consultées ; vidéo temporaire en cache | ancien/nouveau format, décodage réduit en mémoire, URI FileProvider | Implémenté |
| M-21 | fiche commune 14 types | `/recherche/api/mobile/details/{type}/{id}/` | `SearchDetailActivity` | `search_cache` | ouverture de chaque type | Implémenté, contenu riche partiel |
| M-22 | GPS points/équipements | APIs terrain existantes | Navigation/À compléter | file `sync_queue` | permission/refus/conflit | Existant, réutilisation indiquée |
| M-23 | photo points/équipements | APIs terrain existantes | Navigation/À compléter | file `sync_queue` | caméra/erreur/reprise | Existant |
| M-24 | intervention hors ligne | APIs réparation existantes | Réparations | file idempotente | doublon/reprise | Partiel |
| M-25 | état en/hors ligne | aucune | en-tête Recherche/fiche | date du cache | bascule réseau | Implémenté |
| M-26 | recherche dans tournée téléchargée | snapshot `terrain.ouvrages` | Tout/Ouvrages | `hydria_terrain.db` | mode avion | Implémenté pour ouvrages |
| M-27 | fichiers techniques sur demande | routes Web actuelles | fiche future | pas d'auto-download | téléchargement | À implémenter |
| M-28 | activités par cible | options serveur existantes | administration future | références tournée | rôle staff | Hors périmètre agent justifié |

## Nouvelles routes mobiles

Toutes exigent une session Django ou `Authorization: Token …` de portée `mobile` :

- `GET /recherche/api/mobile/search/`
- `GET /recherche/api/mobile/personnes/`
- `GET /recherche/api/mobile/personnes/{type}/{uuid}/`
- `POST /recherche/api/mobile/personnes/{type}/{uuid}/modifier/`
- `GET /recherche/api/mobile/ouvrages/`
- `GET /recherche/api/mobile/interventions/`
- `POST /recherche/api/mobile/interventions/{uuid}/reporter/`
- `POST /recherche/api/mobile/interventions/{uuid}/supprimer/`
- `GET /recherche/api/mobile/details/{type}/{id}/`
- `GET /recherche/ouvrages/{uuid}/interventions/options/` (session ou token mobile)
- `POST /recherche/ouvrages/{uuid}/interventions/{uuid}/modifier/` (session ou token mobile)

## Différences volontaires actuelles

- Android montre des cartes à toutes les tailles, pas une table sur grand écran.
- Les images ne sont pas téléchargées automatiquement par la recherche.
- La configuration des activités par cible reste en Administration Web tant qu'une interface réservée aux rôles staff n'est pas nécessaire sur le terrain.
- Le mode hors ligne ne copie pas tout l'annuaire : seulement les requêtes et fiches consultées ; les ouvrages de tournée viennent du snapshot existant.
- Les analyses et relations lourdes des fiches Web ne sont pas encore toutes sérialisées. La fiche Android affiche cependant toujours une identité et des champs réels ; elle n'est jamais vide.

## Critère de fermeture

La migration ne pourra passer à `Vérifié` globalement qu'après : enrichissement des autres fiches métier, matrice de permissions par fixtures et tests instrumentés GPS/photo/hors ligne.
