# Audit du domaine Recherche Web Hydria

Date de l'audit : 30 août 2026  
Portée : code local Django, routes `core`, vues, templates, scripts intégrés, modèles et règles de périmètre. Les données de production et les UUID observés ne sont jamais codés en dur.

## Synthèse

Le domaine Recherche est réparti entre quatre vues principales et une fiche générique très volumineuse :

- recherche globale : `apps/core/views_search_evolved.py::search_api_evolved`, `templates/core/search.html` ;
- annuaire : `apps/core/views_personnes.py`, `templates/core/personnes_annuaire.html` ;
- ouvrages : `apps/core/views_ouvrage_interventions.py::recherche_ouvrages_rapide`, `templates/core/recherche_ouvrages_rapide.html` ;
- dernières interventions : `apps/core/views_ouvrage_interventions.py::interventions_recentes`, `templates/core/interventions_recentes.html` ;
- fiches : `apps/core/views.py::search_detail`, `templates/core/search_detail.html`.

Trois implémentations de recherche coexistent : `views_search_evolved.search_api_evolved` est la route active et prend en charge les 14 types avec filtrage préalable et pagination ; l'ancienne fonction `views.search_api` prend aussi en charge 14 types mais n'est plus routée ; `views_search.api_search_global` n'en couvre que huit. Le code de modale encore présent dans `search.html` n'est plus le parcours actif : les cartes ouvrent une page complète.

Risque découvert et corrigé : l'endpoint actif `/api/search/` n'était pas protégé, utilisait plusieurs champs ORM inexistants et ne filtrait pas uniformément les résultats selon l'organisation. Il exige maintenant une session, valide les 14 querysets et applique le périmètre avant pagination. La façade Android exige en plus un token de portée `mobile`.

## Inventaire fonctionnel

| ID | Route Web | Fonction réelle | Fichiers source | API/actions | Modèles principaux | Permission actuelle | Android | Hors ligne | Statut |
|---|---|---|---|---|---|---|---|---|---|
| R-01 | `/recherche/` | Recherche multitype, 2 caractères, délai 500 ms, Entrée/bouton, catégories | `views.py`, `search.html` | `GET /api/search/` | 14 modèles listés ci-dessous | page authentifiée ; API historique insuffisamment protégée | `SearchActivity/Tout` | cache des requêtes + ouvrages du snapshot | Implémenté, dette API documentée |
| R-02 | `/recherche/personnes/` | Annuaire, recherche 400 ms, type, statut, compteurs, pagination | `views_personnes.py`, `personnes_annuaire.html` | liste, détail enrichi, modification | PointEau, Employe, RepresentantUsager, Autorite, TiersParticipant, Fournisseur | session, employé limité à l'organisation | `SearchActivity/Personnes` | résultats consultés seulement | Implémenté pour liste/fiche commune ; édition enrichie à poursuivre |
| R-03 | `/recherche/ouvrages/` | Recherche opérationnelle et regroupement géographique | `views_ouvrage_interventions.py`, `recherche_ouvrages_rapide.html` | options, ajout, historique, modification, suppression, photo | Ouvrage, PointEau, EquipementConstitutif, Planning, EmployeOuvrages | `_accessible_intervention_ouvrages` | `SearchActivity/Ouvrages` + fiche avec indicateurs, points, équipements et historique | ouvrages du snapshot et fiches consultées | Implémenté |
| R-04 | `/recherche/ouvrages/interventions/recentes/` | Fil chronologique, filtres, médias et actions | `views_ouvrage_interventions.py`, `interventions_recentes.html` | modification/suppression/options/photo | Planning, PlanningDetail, FichePoste | périmètre historique + option autres bases | `RecentInterventionsActivity` : consultation, édition, galerie image/vidéo, clôture/report/suppression conditionnés par le serveur | pages consultées ; actions en ligne | Implémenté |
| R-05 | `/recherche/ouvrages/activites-equipements/` | Configuration des activités autorisées par cible | `repair_activity_equipment_permissions`, template associé | formulaire Web | FichePoste et politique de cible | staff uniquement | administration future | non | Hors périmètre terrain justifié |
| R-06 | `/recherche/details/{type}/{uuid}/` | Fiche complète et actions contextuelles | `search_detail`, `search_detail.html` | nombreuses routes liées | selon type | `login_required`, contrôles hétérogènes par action | `SearchDetailActivity` commune | cache fiche | Socle implémenté, enrichissement type par type en cours |
| R-07 | options intervention ouvrage | Catalogue serveur des cibles/activités | `options_intervention_ouvrage` | GET options | FichePoste, PointEau, Equipement | ouvrage accessible | réutilisé par formulaires terrain existants | snapshot partiel | Identifié |
| R-08 | ajout intervention | Création, cible, description, six médias | `ajouter_intervention_ouvrage` | POST JSON | Planning, PlanningDetail | serveur | formulaire réparation existant, fusion à poursuivre | file idempotente existante | En cours |
| R-09 | historique intervention | Pagination, pièces jointes, actions | `_historique_interventions`, endpoint historique | GET | Planning | serveur | vingt dernières entrées dans la fiche ouvrage + fil paginé dédié | fiche consultée | Implémenté |
| R-10 | modification/suppression | Mise à jour, clôture, report et suppression confirmée | vues modifier/supprimer | POST JSON | Planning | contrôles serveur | édition et actions dans `RecentInterventionsActivity` | actions en ligne | Implémenté |
| R-11 | signalement point d'eau | Réparation au niveau ouvrage et conversation | `signaler_reparation_point_eau` | POST | PointEau, Planning, Conversation | serveur | réparation existante partielle | file existante | En cours |

## Les 14 types réellement renvoyés

| Type | Modèle/source | Fiche Web | État Android |
|---|---|---|---|
| `village` | `geography.Village` | fiche générique + données géographiques | fiche commune disponible |
| `ouvrage` | `organization.Ouvrage` | fiche très riche | fiche commune + périmètre sécurisé |
| `commune` | `geography.Commune` | fiche et cartes | fiche commune disponible |
| `planning` | `planning.Planning` | fiche | fiche commune ; désactivé par défaut |
| `employe` | `employees.Employe` | fiche personne | fiche commune disponible |
| `point_eau` | `billing.PointEau` | fiche, relevés, réparations | fiche commune + actions terrain existantes |
| `representant` | `usagers.RepresentantUsager` | fiche personne | fiche commune disponible |
| `autorite` | `usagers.Autorite` | fiche personne | fiche commune disponible |
| `tiers` | `usagers.TiersParticipant` | fiche personne | fiche commune disponible |
| `fournisseur` | `billing.Fournisseur` | fiche personne | fiche commune disponible |
| `equipement` | `infrastructure.EquipementConstitutif` | fiche | fiche commune + actions terrain existantes |
| `designation` | `planning.Designation` | fiche | fiche commune disponible |
| `modalite` | `billing.ModaliteGestion` | fiche | fiche commune disponible |
| `carte_sociale` | `infrastructure.CarteSociale` | fiche/historique | fiche commune disponible |

## Contrats et dépendances

### Authentification

- Web : session Django.
- Android : `WidgetAuthToken` de portée stricte `mobile`, produit par `/mobile/api/login/`.
- Décorateur : `apps/core/views_mobile_auth.py::mobile_auth_required`.
- Un token widget ne peut pas appeler une route mobile et réciproquement.

### Périmètre

- Filtre générique : `apps/employees/permissions.py::filter_queryset_by_permissions`.
- Ouvrages actifs : `_accessible_ouvrages`, avec modalité courante et périmètre responsable.
- Historique : `_accessible_intervention_ouvrages`, qui préserve les anciennes publications sans compter une modalité future comme affectation actuelle.
- Les points d'eau et équipements mobiles sont toujours dérivés d'ouvrages autorisés.

### Médias

- Les photos de points d'eau et équipements utilisent le gestionnaire de fichiers existant.
- Les interventions stockent aussi d'anciens formats JSON/data URL ; `_planning_attachments` les normalise.
- Le téléchargement automatique de tous les médias n'est pas souhaitable ; seules les métadonnées et les éléments de tournée doivent être préchargés.

## Routes atteignables depuis les interfaces

- Recherche globale → fiche complète de chacun des 14 types.
- Annuaire → aperçu enrichi, fiche complète, modification rapide.
- Ouvrages → fiche, ajout de réparation, historique, carte cible, modification/suppression.
- Dernières interventions → fiche ouvrage, aperçu média, modification/suppression.
- Fiche ouvrage → points d'eau, équipements, dossier technique, réparations, analyses et paiements.
- Fiche point d'eau → relevés/factures, réparation, GPS, photos.

## Code ancien ou non actif

- La modale `detailsModal` de `search.html` est conservée dans le template mais les handlers actifs naviguent vers `/recherche/details/.../`.
- `views_search.api_search_global` est une recherche partielle (huit types) et n'est pas la source de la page auditée.
- `views.search_api` est l'ancienne recherche 14 types ; la route active utilise désormais `views_search_evolved.search_api_evolved`, filtre avant requête et limite `page_size` à 50.

## Points restant à vérifier avant parité complète

- permissions fines par chacun des neuf profils métier demandés : le modèle actuel raisonne surtout par poste, base, organisation et responsabilités ; une matrice automatisée avec comptes-fixtures est nécessaire ;
- contenu riche de chaque fiche (analyses financières, dossier technique, graphiques, relations) ;
- édition rapide des personnes depuis Android avec une règle d'autorisation explicite plus fine que la seule visibilité ;
- filtres région/district/commune/employé et indicateurs de contribution complets dans la vue Android ;
- administration des activités par cible, volontairement absente de l'interface agent terrain.
