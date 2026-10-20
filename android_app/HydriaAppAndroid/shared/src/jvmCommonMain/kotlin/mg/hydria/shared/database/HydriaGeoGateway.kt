package mg.hydria.shared.database

import org.json.JSONObject
import java.util.UUID
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Facade Android pour les tables navigation/GPS (geoEntities,
 * geoLandmarkTypes, geoPositionHistory, geoPlacementCandidates, cf. Geo.sq).
 * Miroir de GeoRepository.kt (app/) : les entites (points d'eau, equipements,
 * villages, reperes) affichees sur la carte terrain, leurs positions
 * capturees, et les candidats a placer (points/equipements sans GPS encore).
 *
 * N'expose que des types simples (String/Double/Long/Boolean/JSONObject) -
 * pas de dependance aux classes app/ (GeoEntity, GeoCategory...) : GeoRepository
 * (app/) fait la conversion JSON <-> GeoEntity/PlacementCandidate a la frontiere,
 * comme le reste de shared/network le fait deja pour les reponses serveur.
 *
 * BRANCHEE SUR L'APP : GeoRepository.kt route toutes ses operations
 * (y compris l'import serveur - importNavigationPage/importSnapshot, qui
 * reste orchestre cote app car couple aux formes JSON du reseau, mais dont
 * chaque ecriture passe desormais par les primitives ci-dessous) via
 * OfflineStore, avec le meme filet de secours que HydriaSyncQueueGateway.
 */
object HydriaGeoGateway {
    private const val EARTH_RADIUS_M = 6_371_008.8
    private const val DEFAULT_VILLAGE_RADIUS_M = 25_000.0


    private fun db() = HydriaSharedDatabaseHolder.database

    /** Enveloppe plusieurs appels dans une seule transaction SQLDelight -
     * utilise par l'import serveur (plusieurs entites/candidats/reperes a la
     * fois) pour conserver l'atomicite obtenue auparavant via une transaction
     * SQLite brute. */
    fun <T> runImportTransaction(block: () -> T): T = db().transactionWithResult { block() }

    private fun distanceMeters(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val phi1 = Math.toRadians(lat1)
        val phi2 = Math.toRadians(lat2)
        val dPhi = Math.toRadians(lat2 - lat1)
        val dLambda = Math.toRadians(lon2 - lon1)
        val a = sin(dPhi / 2).pow(2) + cos(phi1) * cos(phi2) * sin(dLambda / 2).pow(2)
        return EARTH_RADIUS_M * 2 * atan2(sqrt(a), sqrt(1 - a))
    }

    private fun entityJson(
        entityId: String, category: String, name: String, typeLabel: String?, code: String?,
        ouvrageId: String?, latitude: Double?, longitude: Double?, altitude: Double?,
        accuracyM: Double?, syncState: String, serverUpdatedAt: String?, isFieldMarker: Long,
    ): JSONObject = JSONObject()
        .put("entity_id", entityId).put("category", category).put("name", name)
        .put("type_label", typeLabel ?: "").put("code", code ?: "").put("ouvrage_id", ouvrageId ?: "")
        .put("latitude", latitude).put("longitude", longitude)
        .put("altitude", altitude).put("accuracy_m", accuracyM)
        .put("sync_state", syncState).put("server_updated_at", serverUpdatedAt ?: "")
        .put("is_field_marker", isFieldMarker == 1L)

    /** Insere ou remplace une entite venant du serveur, sauf si l'etat local
     * est en attente/erreur/conflit (une modification locale non synchronisee
     * ne doit jamais etre ecrasee par un import serveur). */
    fun upsertServerEntity(
        entityId: String, category: String, name: String, typeLabel: String?, code: String?,
        ouvrageId: String?, latitude: Double, longitude: Double, altitude: Double?,
        accuracyM: Double?, serverUpdatedAt: String?, isFieldMarker: Boolean,
        now: Long = System.currentTimeMillis(),
    ) {
        val database = db()
        val existing = database.geoQueries.selectForUpsertCheck(category, entityId).executeAsOneOrNull()
        if (existing != null && existing.syncState in setOf("pending", "error", "conflict")) return
        val isFieldMarkerValue = if (isFieldMarker) 1L else 0L
        if (existing == null) {
            database.geoQueries.insertEntity(
                entityId = entityId, category = category, name = name, typeLabel = typeLabel, code = code,
                ouvrageId = ouvrageId, latitude = latitude, longitude = longitude, altitude = altitude,
                accuracyM = accuracyM, captureMethod = null, capturedAt = null, serverUpdatedAt = serverUpdatedAt,
                localUpdatedAt = now, syncState = "synced", isFieldMarker = isFieldMarkerValue,
            )
        } else {
            database.geoQueries.updateEntityBySpatialId(
                name = name, typeLabel = typeLabel, code = code, ouvrageId = ouvrageId,
                latitude = latitude, longitude = longitude, altitude = altitude, accuracyM = accuracyM,
                captureMethod = null, capturedAt = null, serverUpdatedAt = serverUpdatedAt,
                localUpdatedAt = now, syncState = "synced", spatialId = existing.spatialId,
            )
        }
    }

    fun allEntities(categories: Set<String>): List<JSONObject> {
        if (categories.isEmpty()) return emptyList()
        return db().geoQueries.selectEntitiesByCategories(categories.toList()).executeAsList().map {
            entityJson(
                it.entityId, it.category, it.name, it.typeLabel, it.code, it.ouvrageId,
                it.latitude, it.longitude, it.altitude, it.accuracyM, it.syncState,
                it.serverUpdatedAt, it.isFieldMarker,
            )
        }
    }

    fun nearby(latitude: Double, longitude: Double, radiusMeters: Double, limit: Int = 300): List<JSONObject> {
        val latDelta = radiusMeters / 111_320.0
        val lonDelta = radiusMeters / (111_320.0 * cos(Math.toRadians(latitude)).coerceAtLeast(0.1))
        val candidates = db().geoQueries.selectEntitiesInBoundingBox(
            latitude - latDelta, latitude + latDelta, longitude - lonDelta, longitude + lonDelta,
        ).executeAsList()
        return candidates
            .filter { it.latitude != null && it.longitude != null }
            .filter { distanceMeters(latitude, longitude, it.latitude!!, it.longitude!!) <= radiusMeters }
            .sortedBy { distanceMeters(latitude, longitude, it.latitude!!, it.longitude!!) }
            .take(limit)
            .map {
                entityJson(
                    it.entityId, it.category, it.name, it.typeLabel, it.code, it.ouvrageId,
                    it.latitude, it.longitude, it.altitude, it.accuracyM, it.syncState,
                    it.serverUpdatedAt, it.isFieldMarker,
                )
            }
    }

    fun withinBounds(
        north: Double, south: Double, east: Double, west: Double,
        centerLatitude: Double, centerLongitude: Double, limit: Int = 600,
    ): List<JSONObject> = db().geoQueries.selectEntitiesInBoundingBoxOrderedByDistance(
        south, north, west, east, centerLatitude, centerLatitude, centerLongitude, centerLongitude,
        limit.coerceAtLeast(1).toLong(),
    ).executeAsList().map {
        entityJson(
            it.entityId, it.category, it.name, it.typeLabel, it.code, it.ouvrageId,
            it.latitude, it.longitude, it.altitude, it.accuracyM, it.syncState,
            it.serverUpdatedAt, it.isFieldMarker,
        )
    }

    fun markEntitySynced(category: String, entityId: String) {
        db().geoQueries.markEntitySyncedByCategoryAndId(category, entityId)
    }

    fun markEntitySyncedAndArchived(category: String, entityId: String) {
        db().geoQueries.markEntitySyncedAndArchivedByCategoryAndId(category, entityId)
    }

    fun markEntityConflict(category: String, entityId: String) {
        db().geoQueries.markEntityConflictByCategoryAndId(category, entityId)
    }

    fun archiveEntityIfSynced(category: String, entityId: String) {
        db().geoQueries.archiveIfSyncedByCategoryAndId(category, entityId)
    }

    // ── Reperes (landmark types) ──

    private val DEFAULT_LANDMARK_TYPES = listOf(
        "pont" to "Pont", "sentier" to "Sentier", "intersection" to "Intersection",
        "rond_point" to "Rond-point", "batiment" to "Bâtiment", "ecole" to "École",
        "sante" to "Centre de santé", "riviere" to "Rivière",
        "passage_difficile" to "Passage difficile", "depart" to "Point de départ", "autre" to "Autre",
    )

    fun seedDefaultLandmarkTypes() {
        val database = db()
        DEFAULT_LANDMARK_TYPES.forEachIndexed { index, (id, name) ->
            database.geoQueries.seedLandmarkType(id, name, id, "#58D594", index.toLong())
        }
    }

    fun landmarkTypes(): List<Pair<String, String>> =
        db().geoQueries.selectActiveLandmarkTypes().executeAsList().map { it.id to it.name }

    /** Remplace un type prechargé (id lisible) par l'UUID canonique du serveur. */
    fun upsertServerLandmarkType(
        serverId: String, name: String, description: String?, iconKey: String,
        colorHex: String, displayOrder: Long, isActive: Boolean, serverUpdatedAt: String?,
    ) {
        val database = db()
        database.geoQueries.deleteLandmarkTypeByIconExcept(iconKey, serverId)
        database.geoQueries.upsertLandmarkType(
            serverId, name, description, iconKey, colorHex, displayOrder,
            if (isActive) 1L else 0L, serverUpdatedAt,
        )
    }

    // ── Candidats de placement (points/equipements sans GPS) ──

    fun upsertPlacementCandidate(
        entityId: String, category: String, name: String, code: String?, villageName: String?,
        referenceLatitude: Double?, referenceLongitude: Double?, hasPhoto: Boolean,
        servedVillageIds: String?, ouvrageId: String?, serverUpdatedAt: String?,
    ) {
        val database = db()
        val existing = database.geoQueries.selectPlacementCandidateState(category, entityId).executeAsOneOrNull()
        val localHasPhoto = existing?.hasPhoto == 1L
        val resolvedServedVillageIds = servedVillageIds ?: existing?.servedVillageIds
        database.geoQueries.upsertPlacementCandidate(
            entityId = entityId, category = category, name = name, code = code, villageName = villageName,
            referenceLatitude = referenceLatitude, referenceLongitude = referenceLongitude,
            hasPhoto = if (hasPhoto || localHasPhoto) 1L else 0L,
            servedVillageIds = resolvedServedVillageIds, ouvrageId = ouvrageId, serverUpdatedAt = serverUpdatedAt,
        )
    }

    private fun candidateJson(
        entityId: String, name: String, code: String?, villageName: String?,
        referenceLatitude: Double?, referenceLongitude: Double?, hasPhoto: Long,
        servedVillageIds: String?, ouvrageId: String?, serverUpdatedAt: String?,
    ) = JSONObject()
        .put("entity_id", entityId).put("name", name).put("code", code ?: "")
        .put("village_name", villageName ?: "")
        .put("reference_latitude", referenceLatitude).put("reference_longitude", referenceLongitude)
        .put("has_photo", hasPhoto == 1L)
        .put("served_village_ids", servedVillageIds ?: "")
        .put("ouvrage_id", ouvrageId ?: "").put("server_updated_at", serverUpdatedAt ?: "")

    fun placementCandidates(category: String): List<JSONObject> =
        db().geoQueries.selectPlacementCandidatesByCategory(category).executeAsList().map {
            candidateJson(
                it.entityId, it.name, it.code, it.villageName, it.referenceLatitude,
                it.referenceLongitude, it.hasPhoto, it.servedVillageIds, it.ouvrageId, it.serverUpdatedAt,
            )
        }

    fun placementCandidate(category: String, entityId: String): JSONObject? =
        placementCandidates(category).firstOrNull { it.optString("entity_id") == entityId }

    fun markCandidatePhotoQueued(category: String, entityId: String) {
        db().geoQueries.markCandidatePhotoQueued(category, entityId)
    }

    fun nearbyVillageIds(latitude: Double, longitude: Double, radiusMeters: Double = DEFAULT_VILLAGE_RADIUS_M): Set<String> {
        val latDelta = radiusMeters / 111_320.0
        val lonScale = cos(Math.toRadians(latitude)).let { kotlin.math.abs(it).coerceAtLeast(0.1) }
        val lonDelta = radiusMeters / (111_320.0 * lonScale)
        return db().geoQueries.selectCategoryEntitiesInBoundingBox(
            "village", latitude - latDelta, latitude + latDelta, longitude - lonDelta, longitude + lonDelta,
        ).executeAsList()
            .filter { it.latitude != null && it.longitude != null }
            .filter { distanceMeters(latitude, longitude, it.latitude!!, it.longitude!!) <= radiusMeters }
            .mapTo(mutableSetOf()) { it.entityId }
    }

    /** Candidats (typiquement points d'eau) dont l'ouvrage dessert au moins un
     * village proche - meme logique de recoupement nom/village que
     * GeoRepository.candidateIdsServingNearbyVillages(). */
    fun candidateIdsServingNearbyVillages(
        category: String, latitude: Double, longitude: Double,
        radiusMeters: Double = DEFAULT_VILLAGE_RADIUS_M, waterPointCategory: String = "water_point",
    ): Set<String> {
        val latDelta = radiusMeters / 111_320.0
        val lonScale = cos(Math.toRadians(latitude)).let { kotlin.math.abs(it).coerceAtLeast(0.1) }
        val lonDelta = radiusMeters / (111_320.0 * lonScale)
        val nearbyVillages = db().geoQueries.selectCategoryEntitiesInBoundingBox(
            "village", latitude - latDelta, latitude + latDelta, longitude - lonDelta, longitude + lonDelta,
        ).executeAsList().filter {
            it.latitude != null && it.longitude != null &&
                distanceMeters(latitude, longitude, it.latitude!!, it.longitude!!) <= radiusMeters
        }
        val nearbyIds = nearbyVillages.mapTo(mutableSetOf()) { it.entityId }
        val nearbyNames = nearbyVillages.mapTo(mutableSetOf()) { it.name.trim().lowercase() }
        if (nearbyIds.isEmpty() && nearbyNames.isEmpty()) return emptySet()

        val villageNamesByOuvrage = mutableMapOf<String, MutableSet<String>>()
        db().geoQueries.selectCandidateOuvrageVillageNames(waterPointCategory).executeAsList().forEach { row ->
            val ouvrageId = row.ouvrageId ?: return@forEach
            val names = villageNamesByOuvrage.getOrPut(ouvrageId) { mutableSetOf() }
            (row.villageName ?: "").split(',').map { it.trim().lowercase() }.filterTo(names) { it.isNotBlank() }
        }

        return placementCandidates(category).filterTo(mutableSetOf()) { candidate ->
            val servedIds = candidate.optString("served_village_ids").split(',').filter { it.isNotBlank() }.toSet()
            val ouvrageId = candidate.optString("ouvrage_id")
            servedIds.any { it in nearbyIds } || villageNamesByOuvrage[ouvrageId].orEmpty().any { it in nearbyNames }
        }.mapTo(mutableSetOf()) { it.optString("entity_id") }
    }

    // ── Capture terrain (placement, reperes, mise a jour de position) ──

    /** Place un candidat (point d'eau/equipement) au GPS : cree l'entite si
     * elle n'existe pas, sinon met a jour sa position. Retourne l'entite
     * resultante et l'uuid local de l'historique de position cree. */
    fun placeCandidate(
        entityId: String, category: String, name: String, code: String?,
        latitude: Double, longitude: Double, altitude: Double?, accuracyM: Double?,
        captureMethod: String, capturedAt: String, serverUpdatedAt: String? = null,
        now: Long = System.currentTimeMillis(),
    ): Pair<JSONObject, String> {
        val database = db()
        val existing = database.geoQueries.selectEntityByCategoryAndId(category, entityId).executeAsOneOrNull()
        if (existing != null) {
            val localUuid = updatePosition(category, entityId, latitude, longitude, altitude, accuracyM, captureMethod, capturedAt, now)
            val updated = entityJson(
                existing.entityId, existing.category, existing.name, existing.typeLabel, existing.code,
                existing.ouvrageId, latitude, longitude, altitude, accuracyM, "pending",
                existing.serverUpdatedAt, existing.isFieldMarker,
            )
            return updated to localUuid
        }
        val localUuid = UUID.randomUUID().toString()
        database.transaction {
            database.geoQueries.insertEntity(
                entityId = entityId, category = category, name = name, typeLabel = null, code = code,
                ouvrageId = null, latitude = latitude, longitude = longitude, altitude = altitude,
                accuracyM = accuracyM, captureMethod = captureMethod, capturedAt = capturedAt,
                serverUpdatedAt = serverUpdatedAt, localUpdatedAt = now, syncState = "pending", isFieldMarker = 0L,
            )
            database.geoQueries.insertPositionHistory(
                localUuid = localUuid, entityKind = category, entityId = entityId,
                oldLatitude = null, oldLongitude = null, newLatitude = latitude, newLongitude = longitude,
                altitude = altitude, accuracyM = accuracyM, captureMethod = captureMethod, capturedAt = capturedAt,
                createdAt = now,
            )
        }
        val entity = entityJson(entityId, category, name, null, code, null, latitude, longitude, altitude, accuracyM, "pending", serverUpdatedAt, 0L)
        return entity to localUuid
    }

    fun createLandmark(
        name: String, typeId: String, latitude: Double, longitude: Double,
        altitude: Double?, accuracyM: Double?, captureMethod: String, capturedAt: String,
        category: String = "landmark",
        now: Long = System.currentTimeMillis(),
    ): JSONObject {
        val entityId = UUID.randomUUID().toString()
        val typeLabel = landmarkTypes().firstOrNull { it.first == typeId }?.second ?: "Repère"
        db().geoQueries.insertEntity(
            entityId = entityId, category = category, name = name, typeLabel = typeLabel, code = typeId,
            ouvrageId = null, latitude = latitude, longitude = longitude, altitude = altitude,
            accuracyM = accuracyM, captureMethod = captureMethod, capturedAt = capturedAt,
            serverUpdatedAt = null, localUpdatedAt = now, syncState = "pending", isFieldMarker = 1L,
        )
        return entityJson(entityId, category, name, typeLabel, typeId, null, latitude, longitude, altitude, accuracyM, "pending", null, 1L)
    }

    fun updatePosition(
        category: String, entityId: String, latitude: Double, longitude: Double,
        altitude: Double?, accuracyM: Double?, captureMethod: String, capturedAt: String,
        now: Long = System.currentTimeMillis(),
    ): String {
        val localUuid = UUID.randomUUID().toString()
        val database = db()
        val existing = database.geoQueries.selectEntityByCategoryAndId(category, entityId).executeAsOneOrNull()
        database.transaction {
            database.geoQueries.updatePositionFields(
                latitude = latitude, longitude = longitude, altitude = altitude, accuracyM = accuracyM,
                captureMethod = captureMethod, capturedAt = capturedAt, localUpdatedAt = now,
                category = category, entityId = entityId,
            )
            database.geoQueries.insertPositionHistory(
                localUuid = localUuid, entityKind = category, entityId = entityId,
                oldLatitude = existing?.latitude, oldLongitude = existing?.longitude,
                newLatitude = latitude, newLongitude = longitude, altitude = altitude, accuracyM = accuracyM,
                captureMethod = captureMethod, capturedAt = capturedAt, createdAt = now,
            )
        }
        return localUuid
    }

    fun archiveLandmark(category: String, entityId: String, now: Long = System.currentTimeMillis()): String {
        db().geoQueries.archiveByCategoryAndId(now, category, entityId)
        return UUID.randomUUID().toString()
    }

    fun markPositionHistorySynced(localUuid: String) {
        db().geoQueries.markPositionHistorySynced(localUuid)
    }

    // ── Migration (copie fidele depuis TerrainDatabase, cf. OfflineStore.migrateGeoIfNeeded) ──

    fun seedEntity(
        entityId: String, category: String, name: String, typeLabel: String?, code: String?,
        ouvrageId: String?, latitude: Double?, longitude: Double?, altitude: Double?, accuracyM: Double?,
        captureMethod: String?, capturedAt: String?, serverUpdatedAt: String?, localUpdatedAt: Long,
        syncState: String, isArchived: Boolean, isFieldMarker: Boolean,
    ) {
        db().geoQueries.seedEntity(
            entityId = entityId, category = category, name = name, typeLabel = typeLabel, code = code,
            ouvrageId = ouvrageId, latitude = latitude, longitude = longitude, altitude = altitude,
            accuracyM = accuracyM, captureMethod = captureMethod, capturedAt = capturedAt,
            serverUpdatedAt = serverUpdatedAt, localUpdatedAt = localUpdatedAt, syncState = syncState,
            isArchived = if (isArchived) 1L else 0L, isFieldMarker = if (isFieldMarker) 1L else 0L,
        )
    }

    fun seedPositionHistory(
        localUuid: String, entityKind: String, entityId: String, oldLatitude: Double?, oldLongitude: Double?,
        newLatitude: Double, newLongitude: Double, altitude: Double?, accuracyM: Double?,
        captureMethod: String, capturedAt: String, syncState: String, createdAt: Long,
    ) {
        db().geoQueries.seedPositionHistory(
            localUuid = localUuid, entityKind = entityKind, entityId = entityId,
            oldLatitude = oldLatitude, oldLongitude = oldLongitude, newLatitude = newLatitude, newLongitude = newLongitude,
            altitude = altitude, accuracyM = accuracyM, captureMethod = captureMethod, capturedAt = capturedAt,
            syncState = syncState, createdAt = createdAt,
        )
    }
}
