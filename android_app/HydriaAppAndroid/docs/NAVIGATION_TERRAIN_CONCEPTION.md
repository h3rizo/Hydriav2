# Navigation terrain Hydria — conception préalable

Statut : proposition à valider avant implémentation de la phase 1  
Projet Android de référence : `C:\Users\Dir Soakoja\Desktop\HydriaAppAndroid`  
Date : 28 août 2026

## 1. Résumé des décisions proposées

Le module sera une activité Android native séparée, ouverte depuis l’écran Terrain actuel. Toute sa logique vivra sous `mg.hydria.app.navigation`; `MainActivity` ne contiendra que le point d’entrée.

La navigation utilisera MapLibre Native Android, les API Android de localisation au premier plan et `SensorManager` pour l’orientation. Elle continuera à fonctionner sans fond cartographique grâce à un style neutre local.

Les données géographiques métier ne seront pas conservées uniquement dans le snapshot JSON. Une migration de `TerrainDatabase` créera des tables structurées, un index SQLite R-Tree et un historique local des positions.

Le backend recevra une application Django dédiée `apps.navigation_terrain`, avec `TypeRepere`, `Repere`, `ReperePhoto` et `GeoPositionAudit`. Les écritures réutiliseront le token mobile, le périmètre serveur et la file `sync_queue` existante.

La phase 1 proposée couvre le socle cartographique, la navigation directe, les indicateurs hors écran, le stockage structuré hors ligne, la mise à jour des coordonnées des entités existantes et la création de repères hors ligne. Le téléchargement administrable de régions cartographiques est réservé à la phase 2 car il exige d’abord le choix d’un fournisseur de tuiles autorisé.

## 2. Audit de l’architecture existante

### 2.1 Android

- Kotlin, Android Views, `minSdk 26`, `targetSdk 34`, Java/Kotlin 17.
- Une seule activité principale : `MainActivity.kt`, environ 158 kB. Elle gère actuellement authentification, navigation, relevés, réparations, plannings, capture GPS, photos et synchronisation.
- Navigation actuelle à quatre onglets : Terrain, Relevés, Réparations et Planning.
- `TerrainDatabase`, version 2, contient uniquement :
  - `snapshot_chunks`, stockage fragmenté du snapshot JSON ;
  - `sync_queue`, file transactionnelle avec états `pending`, `syncing` et `error`.
- `OfflineStore` expose le token, le snapshot et la file, mais ne fournit aucun dépôt géographique structuré.
- `HydriaApi` utilise `HttpURLConnection` et le token `Authorization: Token …`.
- La synchronisation est séquentielle, reprend les opérations interrompues et conserve les conflits retournés en HTTP 409.
- La capture GPS actuelle utilise `LocationManager.getCurrentLocation` ou `requestSingleUpdate`, uniquement au premier plan. C’est un bon comportement à conserver.
- La compression photo existe déjà : maximum 1280 px, JPEG 80 %, limite serveur 5 Mo.
- Les seuls tests JVM actuels concernent `TerrainMeasurementEngine`. Il n’existe pas de tests instrumentés Android.
- MapLibre n’est pas encore une dépendance du projet.

### 2.2 Backend Django

- L’authentification mobile est déjà isolée par un token de scope `mobile` via `mobile_auth_required`.
- Le périmètre d’ouvrages est calculé côté serveur et ne doit jamais être remplacé par un filtrage seulement côté téléphone.
- `geography.Village` possède un UUID, latitude, longitude et altitude.
- `billing.PointEau` possède un UUID, latitude et longitude. Il est déjà sérialisé dans le snapshot Terrain.
- `infrastructure.EquipementConstitutif` possède latitude et longitude en décimal. Il est déjà sérialisé dans le snapshot Terrain.
- L’API `api_sync_terrain_item` gère déjà :
  - la mise à jour GPS d’un point d’eau ;
  - l’idempotence d’une répétition ;
  - le contrôle `base_updated_at` et les conflits 409 ;
  - les photos des points d’eau et équipements.
- Manques actuels :
  - villages absents du snapshot mobile ;
  - aucune mise à jour GPS d’un équipement ;
  - aucune API cartographique paginée ou différentielle ;
  - aucun modèle de repère ;
  - aucun audit unifié des anciennes et nouvelles coordonnées ;
  - aucune configuration serveur du style ou du fournisseur de tuiles.

### 2.3 Contraintes d’intégration

- Préserver intégralement les parcours actuels et la structure du snapshot pour éviter toute régression.
- Ne pas charger un gros catalogue géographique dans un seul champ JSON SQLite.
- Ne pas autoriser une écriture simplement parce que l’entité est présente localement : le serveur valide toujours organisation, périmètre et permission.
- Les métadonnées sont synchronisées avant les photos, conformément à l’ordre déjà utilisé par `sync_queue`.

## 3. Architecture Android proposée

```text
mg.hydria.app.navigation
├── NavigationTerrainActivity.kt
├── model/
│   ├── GeoEntity.kt
│   ├── GeoCategory.kt
│   ├── NavigationState.kt
│   ├── CapturedPosition.kt
│   └── OfflineRegion.kt
├── geo/
│   ├── GeoMath.kt
│   ├── EdgeIndicatorEngine.kt
│   └── ArrivalDetector.kt
├── location/
│   ├── TerrainLocationController.kt
│   └── HeadingController.kt
├── data/
│   ├── NavigationDatabaseSchema.kt
│   ├── GeoRepository.kt
│   ├── SQLiteGeoRepository.kt
│   └── NavigationApi.kt
├── map/
│   ├── MapLibreController.kt
│   ├── MarkerLayerManager.kt
│   ├── MapStyleProvider.kt
│   └── OfflineMapManager.kt
├── sync/
│   ├── NavigationSyncAdapter.kt
│   └── NavigationConflictResolver.kt
└── ui/
    ├── EntityBottomSheet.kt
    ├── NavigationHudView.kt
    ├── EdgeIndicatorsView.kt
    ├── LayerFilterSheet.kt
    └── PositionCaptureSheet.kt
```

`NavigationTerrainActivity` orchestre les composants, mais ne contient ni calcul géodésique, ni SQL, ni logique de synchronisation.

### 3.1 États de navigation

```text
FOLLOW_GPS  → caméra recentrée, cap selon le réglage nord/direction
EXPLORE     → l’utilisateur déplace ou tourne librement la carte
NAVIGATE    → destination active, HUD directionnel et arrivée surveillée
```

Un déplacement manuel de la carte fait passer `FOLLOW_GPS` à `EXPLORE`. Le bouton de recentrage revient à `FOLLOW_GPS`. L’action « Y aller » active `NAVIGATE`.

### 3.2 Localisation et orientation

- Localisation au premier plan seulement.
- Priorité au fournisseur GPS ; réseau accepté comme repli avec précision visible.
- Rejet des coordonnées invalides et des positions trop anciennes.
- Seuil d’avertissement proposé : précision supérieure à 30 m.
- Orientation via cap GPS lorsque la vitesse rend le cap fiable, sinon capteur de rotation du téléphone.
- Filtrage léger du cap pour éviter une flèche instable.
- Aucun droit `ACCESS_BACKGROUND_LOCATION` en phase 1.

### 3.3 Calculs géographiques

- Distance directe : formule de Haversine.
- Cap initial : azimut géodésique normalisé sur `[0, 360)`.
- Direction relative : `capDestination - capRéférence`, normalisée sur `[-180, 180)`.
- Projection bord d’écran : intersection du rayon centre→cible avec un rectangle réduit par les marges système.
- Tous ces calculs seront en Kotlin pur et testables sans Android.

### 3.4 Marqueurs et regroupement

- Une source GeoJSON MapLibre unique avec propriété `category`.
- Clustering MapLibre activé aux faibles zooms.
- Couches séparées par catégorie pour couleurs et icônes :
  - village : violet ;
  - point d’eau : cyan ;
  - équipement : orange ;
  - repère : vert, ou couleur du `TypeRepere`.
- Le dépôt ne charge que la zone visible avec une marge, depuis le R-Tree.
- Les filtres catégorie, distance, ouvrage et zone administrative sont appliqués au dépôt, puis aux couches.

### 3.5 Indicateurs hors écran

Priorité proposée :

1. destination active, toujours visible ;
2. entités sélectionnées ;
3. entités les plus proches ;
4. maximum six indicateurs simultanés.

Les directions séparées de moins de 12° peuvent être regroupées. Un groupe affiche la catégorie dominante, le nombre d’entités et la distance minimale. Le toucher sélectionne la cible prioritaire du groupe ; un second toucher centre la carte.

### 3.6 Fond neutre sans carte

Le projet embarquera un style JSON MapLibre local sans source de tuiles, avec un fond bleu nuit et une grille discrète facultative. Position, entités, destination et indicateurs restent alors utilisables hors réseau.

## 4. Schéma SQLite proposé

La base `hydria_terrain.db` passe de la version 2 à la version 3 avec migration non destructive.

### 4.1 Tables métier structurées

`geo_villages`

- `id TEXT PRIMARY KEY`
- `name TEXT NOT NULL`
- `fokontany_id`, `commune_id`, `district_id`, `region_id`
- `latitude REAL`, `longitude REAL`, `altitude REAL`
- `server_updated_at TEXT`, `local_updated_at INTEGER`
- `sync_state TEXT NOT NULL`, `is_deleted INTEGER NOT NULL DEFAULT 0`

`geo_water_points`

- `id TEXT PRIMARY KEY`
- `name`, `code`, `type_label`
- `village_id`, `ouvrage_id`, `organisation_id`
- coordonnées et colonnes de synchronisation identiques

`geo_equipments`

- `id TEXT PRIMARY KEY`
- `name`, `code`, `type_label`
- `ouvrage_id`, `organisation_id`
- coordonnées et colonnes de synchronisation identiques

`geo_landmark_types`

- `id TEXT PRIMARY KEY`, `name TEXT UNIQUE`
- `description`, `icon_key`, `color_hex`, `display_order`
- `is_active`, `server_updated_at`

`geo_landmarks`

- `id TEXT PRIMARY KEY` — UUID créé localement ou serveur
- `name`, `type_id`, coordonnées, altitude, précision
- `notes`, `capture_method`, `captured_at`
- `village_id`, `ouvrage_id`, `organisation_id`
- `creator_id`, `server_version`, dates locales/serveur
- `sync_state`, `is_archived`, `is_deleted`

`geo_position_history`

- `local_uuid TEXT PRIMARY KEY`
- `entity_kind`, `entity_id`
- anciennes et nouvelles coordonnées
- altitude, précision, méthode, date réelle de capture
- `user_id`, `sync_state`, `server_audit_id`

`geo_photos`

- `local_uuid TEXT PRIMARY KEY`
- `entity_kind`, `entity_id`, `local_path`
- dimensions, taille, type MIME, hash SHA-256
- `sync_state`, `server_photo_id`, dates

### 4.2 Index spatial

- Table de correspondance `geo_entity_refs(spatial_id INTEGER PRIMARY KEY, entity_kind, entity_id UNIQUE)`.
- R-Tree `geo_entity_rtree(spatial_id, min_lat, max_lat, min_lon, max_lon)`.
- Triggers d’insertion, mise à jour et suppression pour garder l’index cohérent.
- Recherche de proximité en deux temps : présélection R-Tree par bounding box, puis distance Haversine exacte en Kotlin.

### 4.3 Réutilisation de `sync_queue`

Nouveaux `operation_type` :

- `geo_position_upsert`
- `landmark_upsert`
- `landmark_archive`
- `landmark_photo_upload`

Chaque payload transporte `local_uuid`, `base_updated_at` ou `base_version`. L’ordre existant place naturellement les photos après les métadonnées.

## 5. Modèles Django proposés

Nouvelle application : `apps.navigation_terrain`.

### 5.1 `TypeRepere`

- `id UUIDField(primary_key=True, default=uuid.uuid4)`
- `nom CharField(unique=True)`
- `description TextField(blank=True)`
- `icone CharField` contenant une clé contrôlée, pas une URL arbitraire
- `couleur CharField` validée au format hexadécimal
- `ordre_affichage PositiveIntegerField`
- `actif BooleanField`
- `created_at`, `updated_at`

Une migration de données crée : pont, sentier, intersection, rond-point, bâtiment, école, centre de santé, rivière, passage difficile, point de départ et autre.

### 5.2 `Repere`

- UUID primaire fourni par le téléphone accepté tel quel
- nom et FK `TypeRepere`
- latitude `DecimalField(10, 7)` et longitude `DecimalField(10, 7)`
- altitude et précision GPS facultatives
- remarques
- méthode `gps` ou `carte`
- `captured_at`, distinct de `created_at`
- créateur `settings.AUTH_USER_MODEL`
- FK facultatives Village, Ouvrage et Organisation
- `version PositiveIntegerField(default=1)` pour concurrence optimiste
- `archived_at`, `created_at`, `updated_at`

### 5.3 `ReperePhoto`

Une table séparée est créée dès la première version, même si l’interface limite initialement à une photo :

- UUID primaire et `local_uuid` unique
- FK `Repere`
- référence vers le stockage de fichier Hydria
- nom, type MIME, taille, hash
- ordre, légende, créateur et dates

Cela évite une migration cassante lorsque plusieurs photos seront activées.

### 5.4 `GeoPositionAudit`

Journal commun aux villages, points d’eau, équipements et repères :

- UUID primaire et `local_uuid` unique pour idempotence
- `entity_kind` et `entity_uuid`
- anciennes et nouvelles latitude/longitude/altitude
- précision, méthode et date réelle de capture
- utilisateur, date de réception, appareil facultatif
- motif de remplacement et données techniques JSON limitées

L’écriture de coordonnées et l’audit sont effectués dans une même transaction Django.

## 6. Contrats API proposés

Tous les endpoints exigent `mobile_auth_required` et recalculent le périmètre côté serveur.

### 6.1 Configuration

`GET /navigation-terrain/api/mobile/config/`

Retour : permissions de création/modification, rayon d’arrivée, seuil de précision, limites d’indicateurs et configuration cartographique publique. Aucun secret fournisseur permanent ne doit être embarqué dans l’APK.

### 6.2 Synchronisation initiale et différentielle

`GET /navigation-terrain/api/mobile/entities/?cursor=…&bbox=…&limit=500`

Retour paginé : villages, points d’eau, équipements, repères, types de repères, suppressions logiques et nouveau curseur. Le téléphone réalise un upsert transactionnel dans les tables structurées.

La première synchronisation peut utiliser le périmètre complet. Les suivantes utilisent un curseur serveur stable, pas seulement l’heure du téléphone.

### 6.3 Capture ou remplacement d’une position

`POST /navigation-terrain/api/mobile/positions/upsert/`

Payload :

```json
{
  "local_uuid": "uuid",
  "entity_kind": "water_point",
  "entity_id": "uuid",
  "latitude": -18.9,
  "longitude": 47.5,
  "altitude": 1280.2,
  "accuracy_m": 12.4,
  "captured_at": "2026-08-28T17:15:00+03:00",
  "capture_method": "gps",
  "base_updated_at": "2026-08-20T10:00:00Z",
  "replace_confirmed": true
}
```

Réponses : `200/201` succès idempotent, `403` permission, `404` hors périmètre, `409` conflit avec valeur serveur, `422` coordonnées incohérentes.

### 6.4 Repères

- `POST /navigation-terrain/api/mobile/reperes/upsert/`
- `POST /navigation-terrain/api/mobile/reperes/{id}/archive/`
- `POST /navigation-terrain/api/mobile/reperes/{id}/photos/`

L’UUID mobile sert de clé primaire. Répéter la même opération retourne la même ressource sans duplication.

### 6.5 Résolution des conflits

- Par défaut, aucune écriture silencieuse si le serveur est plus récent.
- Le serveur retourne la valeur locale proposée et la valeur serveur.
- Le téléphone affiche : conserver serveur, remplacer si autorisé, ou abandonner.
- Toute résolution produit un `GeoPositionAudit`.

## 7. Écrans et parcours utilisateur

### 7.1 Entrée dans le module

Une action « Navigation terrain » est ajoutée dans l’écran Terrain, sans ajouter un cinquième petit onglet. Elle ouvre `NavigationTerrainActivity` en plein écran.

### 7.2 Carte principale

- HUD supérieur : état GPS, précision, réseau, fond hors ligne et actions en attente.
- Carte plein écran.
- Boutons : recentrer, nord/direction, zoom, couches.
- Bouton principal : marquer ma position.
- Appui long : placer un point sur la carte.
- Mire centrale disponible en mode placement.

### 7.3 Fiche inférieure d’une entité

Nom, catégorie/type, distance directe explicitement libellée, coordonnées, synchronisation, puis actions : Y aller, Centrer, Voir la fiche et Modifier selon permission.

### 7.4 Navigation active

- Grande flèche relative.
- Destination, distance directe restante et cap.
- Précision GPS.
- Temps estimé uniquement si la vitesse récente est suffisamment fiable.
- Bouton Annuler.
- Arrivée par défaut à 25 m, configurable.
- Aucun texte ne suggère une distance routière ou un guidage virage par virage.

### 7.5 Marquage

1. Choisir GPS courant ou position carte.
2. Choisir la catégorie.
3. Rechercher une entité existante ou créer un repère.
4. Afficher la position existante et demander confirmation du remplacement.
5. Avertir si précision > 30 m.
6. Enregistrer immédiatement localement puis mettre en file.

### 7.6 Cartes hors ligne

Écran dédié prévu en phase 2 : liste des zones, estimation, Wi-Fi uniquement, progression, pause/reprise, mise à jour et suppression.

## 8. Stratégie cartographique hors ligne

### Phase 1

- Style neutre local toujours disponible.
- Cache MapLibre standard pour l’usage récent.
- Entités Hydria et navigation entièrement locales.
- Le style en ligne provient d’une URL configurée par le backend.
- Bascule automatique vers le style neutre en cas d’échec.

### Phase 2

- Régions hors ligne MapLibre avec catalogue SQLite de métadonnées.
- Limites de taille, zoom et nombre de zones imposées.
- Téléchargement uniquement via un fournisseur autorisé ou un serveur Hydria.
- Interdiction explicite de téléchargement massif depuis `tile.openstreetmap.org`.

Le fournisseur de tuiles doit être choisi avant d’implémenter cette phase.

## 9. Découpage en phases

### Phase 0 — validation

- Valider les décisions listées en section 11.
- Choisir le fournisseur/style cartographique.
- Confirmer les rôles d’écriture et le périmètre des villages.

### Phase 1 — socle opérationnel

- Dépendance MapLibre et activité dédiée.
- États suivi, exploration et navigation.
- Localisation/orientation au premier plan.
- `GeoMath`, indicateurs hors écran et tests JVM.
- Migration SQLite v3, tables structurées et R-Tree.
- API config et synchronisation paginée des entités.
- Affichage, clustering, filtres essentiels et fiche inférieure.
- Navigation directe avec arrivée à 25 m.
- Fond neutre sans carte.
- Capture GPS/carte pour entités existantes autorisées.
- Création de repères hors ligne et synchronisation idempotente.
- Tests backend, tests dépôt SQLite et documentation de compilation.

### Phase 2 — cartes et médias hors ligne

- Gestion complète des régions cartographiques.
- Une ou plusieurs photos de repères.
- Reprise de téléchargements et politiques Wi-Fi.
- Interface détaillée de résolution des conflits.

### Phase 3 — enrichissements

- Création hors ligne de villages/points/équipements pour rôles autorisés.
- Groupement directionnel avancé.
- Partage/export de repères.
- Éventuel suivi continu, seulement après justification métier et étude batterie/confidentialité.

## 10. Tests attendus

### JVM Kotlin

- Haversine avec cas connus et passage du méridien.
- Cap, normalisation angulaire et direction relative.
- Projection sur chaque bord et chaque rotation de carte.
- Priorisation, limite et regroupement des indicateurs.
- Détection d’arrivée.
- Rejet latitude/longitude invalides.

### Android/instrumentés

- Migration SQLite v2→v3 sans perte du snapshot ou de la file.
- R-Tree et recherche de proximité.
- Création hors ligne puis reprise de synchronisation.
- GPS refusé/indisponible et fond de carte absent.
- Restauration d’état après rotation ou recréation d’activité.

### Django

- Scope mobile par organisation/périmètre.
- UUID idempotent et répétition après perte de réponse.
- Conflit `base_updated_at`/version.
- Audit atomique des anciennes coordonnées.
- Permissions de création et remplacement.
- Pagination/cursor et suppressions logiques.
- Métadonnées avant photos.

## 11. Risques et décisions nécessitant validation

1. **Fournisseur de tuiles** : URL du style, licence, coût, quotas et droit de téléchargement hors ligne. Sans décision, seule la carte neutre peut être garantie.
2. **Périmètre des villages** : un village n’a pas de lien direct à l’ouvrage. Il faut confirmer le calcul d’accès via fokontany/points d’eau/organisation.
3. **Permissions d’écriture** : rôles autorisés à remplacer des coordonnées et à créer chaque catégorie.
4. **Conflits** : proposition recommandée = blocage 409 et choix utilisateur, jamais « dernier écrit gagne » silencieusement.
5. **Application Django dédiée** : recommandée pour isoler modèles, API, admin et migrations.
6. **Photos** : réutiliser le gestionnaire de fichiers Hydria ou stocker dans un backend objet ; la base64 ne doit pas devenir la solution durable pour de gros volumes.
7. **Volume initial** : nombre maximal d’entités par organisation et tailles de zones nécessaires pour calibrer pagination, R-Tree et cache.
8. **Création de nouvelles entités métier** : recommandée seulement en phase 3 ; la phase 1 modifie les coordonnées d’entités existantes et crée des repères.
9. **Rayon d’arrivée** : 25 m proposé, avec préférence locale encadrée par une valeur min/max serveur.
10. **Dépendance MapLibre** : épingler une version stable après un prototype de compatibilité avec AGP/Kotlin actuels, puis ne pas la mettre à jour automatiquement.

## 12. Critères de validation de la phase 1

- Les modules Relevés, Réparations, Planning et Terrain continuent de compiler et fonctionner.
- La carte montre les quatre catégories depuis SQLite.
- La navigation directe fonctionne avec ou sans réseau et sans fond de carte.
- Les calculs de distance/cap/indicateurs passent leurs tests.
- Une capture hors ligne survit à la fermeture de l’application et se synchronise une seule fois.
- Une coordonnée serveur plus récente produit un conflit visible, sans perte silencieuse.
- Aucun téléchargement massif n’utilise les serveurs publics OSM.
- Aucune permission de localisation arrière-plan n’est demandée.

