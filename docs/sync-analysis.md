# Analyse préalable : synchronisation de fichiers type Dropbox

Branche : `feature/sync-fichiers`. Phase 1 (lecture seule, aucun code modifié).
Date : 2026-10-25.

## 0. Écart avec le cahier des charges initial

Le cahier des charges décrit un backend **Express + supabase-js** (`server.js`,
`backend/routes/api/sync.js`, `backend/utils/stockage.js`, `express.static`, clé de session
`soakoja-secret-2024`). **Rien de tout cela n'existe dans ce dépôt** :

| Hypothèse du cahier | Réalité constatée |
|---|---|
| Express, `server.js` | Django 5.x / DRF (`backend/manage.py`, `backend/hydria/`) |
| supabase-js / `pg` | ORM Django, `DATABASES` via `DATABASE_URL` (PostgreSQL). Le SDK Python `supabase` n'est utilisé que par `apps/filemanager/services.py` (stockage de fichiers) |
| `backend/migrations/` SQL | Migrations Django par application |
| Clé en dur `soakoja-secret-2024` | Introuvable (grep sur tout le dépôt). `SECRET_KEY` vient de l'environnement mais **retombe sur une valeur `django-insecure-...` en dur** si absente (`settings.py:26`) |
| `express.static` | Fichiers médias servis via `MEDIA_URL=/media/`, `MEDIA_ROOT=backend/media` |

Décision de l'utilisateur : **adapter toute la tâche à Django/DRF** (modèles + migrations Django,
app `backend/apps/sync/`, routes `/api/sync/...`, tests Django, même contrat d'API).

Fichiers signalés (non ouverts) : `backend/hydria` et `backend/cookies.txt` sont présents.
`cookies.txt` ressemble à un export de cookies de session ; à vérifier qu'il n'est pas suivi par git.

## 1. Accès à la base

- ORM Django exclusivement ; connexion par `dj_database_url` (`backend/hydria/settings.py:284`).
- Pas de client supabase-js ni de `pg` direct. Fichiers concernés pour le stockage : 
  `apps/filemanager/services.py` (SDK Python Supabase, bucket `HydriaStock`, repli « stockage local »).
- Versions : `requirements.txt` épingle Django 5.1.4 / DRF 3.16.1, l'environnement local a Django 5.2.6 /
  DRF 3.15.2. **Le VPS tourne en Django 5.1.4** (relevé le 2026-10-25 ; d'anciennes notes disaient 4.2).
  L'app `sync` reste volontairement compatible 4.2 → 5.2 (`CheckConstraint(check=...)`, pas de `db_default`).
- Authentification DRF globale : `SessionAuthentication` + `IsAuthenticated`, pagination page/25.
  Une session impose le jeton CSRF pour les écritures : peu adaptée à un client desktop.
  **Précédent à réutiliser** : `/api/mobile/v1/` (`apps/core/mobile_api_v1.py`) propose
  `auth/login`, `auth/refresh` (jeton rotatif `MobileRefreshToken`), décorateur `mobile_v1_required`,
  `bootstrap` et `changes` avec curseur (`cursor`/`server_time`). Le contrat de sync devrait s'aligner dessus.

## 2. Entités et tables

Chaîne territoriale réelle (apps `geography`, `organization`, `billing`, `infrastructure`) :

```
Region -> District -> Commune -> Fokontany -> Village -> Parcelle -> PointEau -> Ouvrage
                                                      Ouvrage -> EquipementConstitutif
```

Le cahier omet `Fokontany` (entre Commune et Village) : il est **obligatoire** dans le modèle
(`Village.fokontany`). L'arborescence locale devra soit l'inclure, soit l'aplatir (question ouverte Q3).

| Entité | Table | Clé primaire | Parent(s) FK | Organisation directe ? |
|---|---|---|---|---|
| Region | `regions` | UUID `id` | `ex_province` (nullable) | Non |
| District | `districts` | UUID | `region` | Non |
| Commune | `communes` | UUID | `district` | Non |
| Fokontany | `fokontanys` | UUID | `commune` | Non |
| Village | `villages` | UUID | `fokontany` (NOT NULL en base, `null=True` dans le modèle) | Non |
| Parcelle | `parcelles` | UUID | `village` | Non |
| PointEau | `pointseaus` | UUID | `ouvrage` (`ouvrageid`, nullable), `parcelle` (`parcelleid`, nullable), `type_point_eau`, `compteur_tete` | Non |
| Ouvrage | `ouvrages` | UUID | `type_ouvrage`, `ouvrage_source` (self) | **Non** (voir §4) |
| **Équipement** | **`equipements_constitutifs`** (`infrastructure.EquipementConstitutif`) | UUID | `ouvrage` (`organization.Ouvrage`, nullable, CASCADE), `type_equipement` (nullable), `responsable` (Employe), `photo_reference` (`filemanager.FileUpload`) | Non |
| Activité | `activites` (`planning.Activite`) | UUID | `type_activite` | Non (catalogue global) |
| Organisation | `organisations` | UUID | — | — |

Notes :
- Le nom exact de la table des équipements est **`equipements_constitutifs`** (pas « Equipements »).
  Elle est définie dans `apps/infrastructure/models.py` avec migrations Django normales ; aucune table manuelle.
- Il existe **deux jeux** de modèles géographiques : `apps.geography` (tables `regions`, `districts`,
  `communes`, `villages`...) et `apps.core` (`core_regions`, `core_districts`, `core_communes`, `core_villages`).
  Aucun import de `apps.core.models.Region/Village` n'a été trouvé hors migrations : jeu `core_*` apparemment
  mort ; **les triggers ne doivent viser que `apps.geography`** (à confirmer, Q9).
- Deux modèles `TypeOuvrage` coexistent (`organization` → `type_ouvrages`, `infrastructure` → `typesouvrages`).
  `Ouvrage` utilise celui d'`organization`.
- `Activite` est un catalogue (nom, type, active). Les « activités » exécutées par les agents sont des
  lignes `Planning` (+ `PlanningDetail`). Le cahier dit « plus Activités » : catalogue ou plannings ? (Q4)
- Routes existantes (à détailler en phase 2 si besoin) : préfixes `geography/`, `organisations/`,
  `ouvrages/`, `plannings/`, `facturation/`, `inspections/`, et `''` pour `apps.infrastructure.urls`
  (équipements) — mélange de vues HTML et d'API JSON, sans convention commune.
  Le préfixe `api/` est monté sur `api_root` et sur des chemins `api/dashboard/...`; **`/api/sync/` est libre**.

## 3. Rattachement à l'organisation (OrganisationID)

C'est le point bloquant pour le modèle `SyncChanges.OrganisationID` (non nul).

| Entité | Organisation dérivable ? | Chemin |
|---|---|---|
| Employe | Oui | `Employe.base -> Base.organisation` |
| Base, Compte | Oui, direct | `Base.organisation`, `Compte.organisation` |
| Magasin, Journal | Oui | `base -> organisation` |
| Ouvrage | **Indirect, multiple, temporel** | `ModaliteGestion.gestionnaire` (nullable), plusieurs modalités possibles par ouvrage, actives selon `statut` + `date_debut`/`date_fin` |
| EquipementConstitutif, PointEau | Indirect | via `ouvrage` (nullable → parfois aucun) |
| Region/District/Commune/Fokontany/Village/Parcelle | **Non** | référentiel national partagé |
| Activite / TypeActivite | **Non** | catalogue global |

Conséquences :
1. Les entités territoriales et les activités sont **globales** : elles n'ont pas d'`OrganisationID`.
   Un trigger ne peut pas en fabriquer un. Il faut un modèle de diffusion (Q1).
2. Un ouvrage peut changer de gestionnaire ou en avoir plusieurs ; un ouvrage **sans gestionnaire est visible
   par tous** (`filter_queryset_by_permissions` : `modalites_gestion__gestionnaire__isnull=True`).
3. Les organisations **partenaires** voient les ouvrages des gestionnaires qui leur sont affectés
   (`PartenaireGestionnaireAffectation`), donc « organisation de l'utilisateur » ≠ « organisations accessibles ».

## 4. Restriction d'accès aujourd'hui

- Résolution : `apps/organization/scoping.py` (`get_user_organisation`, `get_user_accessible_gestionnaire_ids`)
  et `apps/employees/permissions.py::filter_queryset_by_permissions` (Ouvrage, PointEau, Parcelle uniquement).
  Superuser = tout ; **visiteur = lecture globale sans restriction** ; utilisateur sans employé = rien ;
  employé sans base = **tout** (« pas de filtre possible »).
- Le filtrage est appliqué **vue par vue**, à la main. Il n'y a pas de couche centrale.
- `@csrf_exempt` apparaît **524 fois dans 111 fichiers** de `apps/`. Exemple vérifié :
  `apps/billing/views_facturation.py` (`api_calculer_factures`, `api_valider_factures`,
  `api_marquer_factures_imprimees`) : POST csrf-exempt ; le `login_required` n'est pas visible sur ces trois
  fonctions (une seule occurrence de `login_required` ailleurs dans le fichier) → écritures potentiellement
  accessibles sans session. À auditer hors périmètre de cette tâche.
- Rôles : `is_visiteur`, `is_directeur_poste`, postes « support » (caissière, RAF...). Aucun concept existant
  de droit par domaine (opérationnel / administratif / financier / logistique).

## 5. Colonne photos

- `Ouvrage.photo` (**`TextField`**, « Photos (JSON) », pas `Photos`) ; idem `Region/District/Commune/Fokontany/Village.photo`
  (TextField) ; `PointEau.photos` et `EquipementConstitutif.photos` (**JSONField**) ; `Planning.photo` (TextField JSON).
- Format : liste d'objets `{url|data, type|content_type, ...}` ou de chaînes. `data` peut contenir du
  **Base64 brut** (souvent JPEG `/9j/...`) : les photos sont donc en partie **stockées dans la base**
  (`apps/organization/views.py:671-722`).
- Conséquence : la sync ne doit pas lire/écrire ces colonnes ; les nouvelles photos entrent par `Fichiers`
  (catégories `photos_*`). Migration des photos existantes = hors périmètre, à décider (Q7).

## 6. Tables « organisation » existantes

| Table | Stocke | Référence utilisable pour `Fichiers` ? |
|---|---|---|
| `organisations` | identité, NIF/STAT/CNAPS, tarifs, type gestionnaire/partenaire, logo | Oui : `OrganisationID` |
| `bases` | bases opérationnelles (org, ouvrage, lieu de départ) | Possible (sous-périmètre) |
| `comptes` | comptes comptables, FK `organisation` directe | Pas nécessaire ; catégorie « justificatif » suffit |
| `journaux` | journaux comptables par base | Idem |
| `magasins` | magasins par base | Idem (logistique) |
| Gestionnaires | **pas de table** : `Organisation.type_organisation='gestionnaire'` + `ModaliteGestion.gestionnaire` | — |
| `employes` (apps.employees) | personnel, `user` OneToOne, `base` | Sert à résoudre l'organisation de l'utilisateur |

Les domaines du cahier ne correspondent à aucune table : ils seront de simples libellés dans `CategoriesFichiers`.

## 7. Notion de document / pièce jointe existante

Pas de gestionnaire de documents unifié. Mécanismes en parallèle :
- `apps.filemanager.FileUpload` : fichiers dans Supabase Storage, **sans organisation** (propriétaire = utilisateur,
  `is_public`), tags, utilisé par inspections et `EquipementConstitutif.photo_reference`.
- `OuvrageDossierTechnique` (`ouvrage_dossiers_techniques`, `FileField`) : **déjà** un « dossier technique »
  par ouvrage, stocké sous `MEDIA_ROOT/ouvrages/dossiers_techniques/{ouvrage}/`. Chevauche la catégorie
  « dossier technique » du cahier (Q6).
- `FileField`/`ImageField` éparpillés : contrat de gestion, scans comptables, justificatifs RH, pièces de réunions,
  chantiers (`ChantierDocument`), photos de relevés, etc.
- Les fichiers `MEDIA_ROOT` sont servis par Django/nginx sous `/media/` : le futur répertoire de sync devra
  rester **hors `MEDIA_ROOT`** et hors `staticfiles/`.

## 8. Incohérences relevées

1. Cahier = Express/supabase-js ; dépôt = Django (résolu : adaptation Django).
2. Clé `soakoja-secret-2024` introuvable ; vrai risque : `SECRET_KEY` avec repli `django-insecure-...` dans `settings.py:26`.
3. Doublon géographique `apps.geography` vs `apps.core` (`core_*`).
4. `Village.fokontany` : `null=True` dans le modèle mais NOT NULL en base.
5. Deux `TypeOuvrage`.
6. `Ouvrage` sans organisation directe ; ouvrages sans gestionnaire visibles de tous.
7. Entités globales (géographie, activités) sans organisation, incompatibles avec `SyncChanges.OrganisationID` NOT NULL.
8. Fokontany absent de l'arborescence demandée.
9. Versions Django divergentes (requirements 5.1.4 / local 5.2.6 / VPS 4.2).
10. Authentification session+CSRF inadaptée à un client desktop ; `@csrf_exempt` massif et `login_required` manquant à plusieurs endroits.
11. Visiteur : lecture globale ; employé sans base : accès à tout.
12. Photos : colonnes `photo`/`photos` de natures différentes (TextField vs JSONField), Base64 en base.
13. `models_remote_backup.py` (organization) duplique `Organisation/Ouvrage/Magasin/Journal/Compte` ; vérifier qu'il n'est pas importé.
14. L'arbre de travail contient de nombreuses modifications **non liées** (app Android, accounting, billing...) : elles ne doivent pas être mêlées aux commits de cette branche.

## 9. Questions ouvertes (à trancher avant la phase 2)

**Bloquantes pour le modèle de données**
- **Q1. Entités globales sans organisation** (régions, districts, communes, fokontany, villages, activités, et ouvrages sans gestionnaire).
  Option A : `SyncChanges.OrganisationID` **nullable** ; NULL = diffusé à tous les utilisateurs authentifiés (référentiel).
  Option B : dupliquer une ligne `SyncChanges` par organisation (explosion de volume, 1 changement géo = N lignes).
  Option C : restreindre la diffusion territoriale aux zones où l'organisation gère des ouvrages (calcul coûteux).
  *Recommandation : A pour le référentiel + filtrage serveur à la lecture selon le périmètre de l'utilisateur.*
- **Q2. Organisation d'un ouvrage** (donc d'un équipement, d'un point d'eau). Retenir : toutes les organisations
  ayant une modalité **active** (+ partenaires affectés) ? Que faire quand le gestionnaire change : le fichier
  reste-t-il rattaché à l'ouvrage (et suit le nouveau gestionnaire) ? *Recommandation : `Fichiers.OrganisationID` =
  organisation qui **dépose** le fichier ; lecture = toute organisation ayant accès à l'entité via `filter_queryset_by_permissions`.*

**Structure**
- Q3. Inclure `Fokontany` dans l'arborescence locale ? (recommandé : oui, sinon deux fokontany homonymes se mélangent.)
- Q4. « Activités » = catalogue `Activite` ou plannings exécutés (`Planning`) ? L'arbre de fichiers a-t-il besoin du catalogue ?
- Q5. Authentification du client desktop : réutiliser le mécanisme `mobile/v1` (jeton + refresh rotatif) ? (recommandé) 
  ou ajouter DRF SimpleJWT (déjà installé mais non configuré dans `settings.py`) ?
- Q6. `OuvrageDossierTechnique` : le laisser tel quel, ou le remplacer à terme par la catégorie « dossier technique » ?
- Q7. Photos Base64 existantes et `FileUpload` Supabase : migration ultérieure ou jamais ?
- Q8. Droits par domaine : opérationnel + logistique ouverts à tous les membres ; financier et administratif **laissés vides**
  (aucune règle codée), comme demandé. Qui doit lire/écrire ces deux domaines ? (RAF, directeur, caissière ?)
- Q9. Confirmer que les tables `core_*` (géographie) sont mortes avant d'exclure leurs triggers.
- Q10. Triggers PostgreSQL : le VPS autorise-t-il l'utilisateur de l'application à créer des fonctions/triggers ?
  Les migrations Django `RunSQL` seront écrites réversibles (le `reverse` supprime uniquement les triggers/fonctions créés par `sync`).

**Technique**
- Q11. Emplacement du stockage : `/srv/hydria/storage` (défaut du cahier) ; l'utilisateur systemd gunicorn (`soakoja`)
  doit en avoir l'écriture. À créer par vous (aucune action serveur de ma part).
- Q12. Politique de **conflit** pour les fichiers poussés par le desktop : `If-Match` sur `Version` suffit-il, ou faut-il
  conserver l'ancienne version (historique) ?
- Q13. Les migrations existantes sont fragiles (graphe aligné sur le VPS, Django 4.2) : les dépendances de la migration
  `sync` seront prises sur les **dernières migrations réelles** de chaque app, relues avec vous avant application.

## 10. Décisions prises (avant la phase 2)

Tranchées par l'utilisateur le 2026-10-25 :
- **Q1** `sync_changes.organisation_id` nullable ; NULL = référentiel diffusé à tous les utilisateurs authentifiés.
- **Q2** `fichiers.organisation_id` = organisation qui dépose ; la lecture s'appuie sur `filter_queryset_by_permissions`.
- **Q3** `Fokontany` inclus dans l'arborescence. **Q4** « Activités » = catalogue `Activite`. **Q5** mécanisme de jetons de `mobile/v1`.

Appliquées par défaut (recommandations de ce document), **à confirmer** :
- **Q5 (précision)** : scope de jeton dédié `sync` (et refresh préfixé `sync:`) plutôt que le scope `mobile`, pour qu'un jeton de
  synchronisation n'ouvre pas les endpoints logistiques. Aucune migration dans `apps.core`.
- **Q6** `OuvrageDossierTechnique` inchangé ; la catégorie `dossier_technique` (ouvrage, équipement) coexiste. **Q7** photos Base64 existantes : non migrées.
- **Q8** domaines financier et administratif : aucune règle (superutilisateur seulement) ; opérationnel et logistique ouverts à tous les membres.
- **Q9** triggers uniquement sur `apps.geography` (pas `core_*`). **Q10** triggers créés par la migration `sync 0002`, réversibles.
- **Q11** `/srv/hydria/storage`, créé par vous. **Q12** conflit = `If-Match` sur `version` ; l'ancien contenu remplacé va dans `_corbeille/`.
- **Q13** dépendances de `sync 0002` = feuilles actuelles des migrations (organization 0039, geography 0019, infrastructure 0029, billing 0093, planning 0067).
- Rattachement d'un ouvrage au village : village de son premier point d'eau localisé ; sinon `ouvrages_sans_village`.
- Un point d'eau sans ouvrage est diffusé à tous (comme le référentiel).
