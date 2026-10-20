package mg.hydria.app.navigation.data

import mg.hydria.app.OfflineStore
import mg.hydria.app.navigation.model.CapturedPosition
import mg.hydria.app.navigation.model.GeoCategory
import mg.hydria.app.navigation.model.GeoEntity
import mg.hydria.app.navigation.model.PlacementCandidate
import org.json.JSONArray
import org.json.JSONObject

/**
 * Le décodage et l'ordre d'import sont partagés. Les transactions et les écritures
 * restent exécutées via [OfflineStore], avec ses protections des modifications locales.
 */
class GeoRepository(private val store: OfflineStore) {

    private fun JSONObject.toGeoEntity(): GeoEntity =
        mg.hydria.shared.navigation.GeoLocalGateway.entity(this)

    private fun JSONObject.toPlacementCandidate(category: GeoCategory): PlacementCandidate =
        mg.hydria.shared.navigation.GeoLocalGateway.placement(this, category)

    fun importNavigationPage(body: JSONObject): Int {
        var imported = 0
        store.geoRunImportTransaction {
            imported = mg.hydria.shared.navigation.GeoPageImportGateway.importPage(
                body, ::importItems, ::importLandmarkTypes, store::geoArchiveEntityIfSynced,
            )
        }
        return imported
    }

    fun markOperationSynced(type: String, payload: JSONObject) = applySyncResult(type, payload, false)

    fun markOperationConflict(type: String, payload: JSONObject) = applySyncResult(type, payload, true)

    private fun applySyncResult(type: String, payload: JSONObject, conflict: Boolean) {
        mg.hydria.shared.navigation.GeoSyncResultGateway.changes(type, payload, conflict).forEach { change ->
            when (change.kind) {
                mg.hydria.shared.navigation.GeoSyncChangeKind.ENTITY_SYNCED ->
                    store.geoMarkEntitySynced(change.category, change.id)
                mg.hydria.shared.navigation.GeoSyncChangeKind.HISTORY_SYNCED ->
                    store.geoMarkPositionHistorySynced(change.id)
                mg.hydria.shared.navigation.GeoSyncChangeKind.ENTITY_ARCHIVED ->
                    store.geoMarkEntitySyncedAndArchived(change.category, change.id)
                mg.hydria.shared.navigation.GeoSyncChangeKind.ENTITY_CONFLICT ->
                    store.geoMarkEntityConflict(change.category, change.id)
            }
        }
    }

    fun importSnapshot(snapshot: JSONObject?) {
        if (snapshot == null) return
        store.geoRunImportTransaction {
            mg.hydria.shared.navigation.GeoPageImportGateway.importSnapshot(
                snapshot, ::importItems, ::importLandmarkTypes,
            )
        }
    }

    private fun importItems(items: JSONArray?, category: GeoCategory, ouvrageId: String) {
        if (items == null) return
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            if (category == GeoCategory.WATER_POINT || category == GeoCategory.EQUIPMENT) {
                mg.hydria.shared.navigation.GeoImportGateway.placement(item, category, ouvrageId)?.let { value ->
                    store.geoUpsertPlacementCandidate(
                        entityId = value.entityId, category = value.category.storageKey,
                        name = value.name, code = value.code, villageName = value.villageName,
                        referenceLatitude = value.referenceLatitude, referenceLongitude = value.referenceLongitude,
                        hasPhoto = value.hasPhoto, servedVillageIds = value.servedVillageIds,
                        ouvrageId = value.ouvrageId, serverUpdatedAt = value.serverUpdatedAt,
                    )
                }
            }
            mg.hydria.shared.navigation.GeoImportGateway.entity(item, category, ouvrageId)?.let { value ->
                store.geoUpsertServerEntity(
                    entityId = value.id, category = value.category.storageKey,
                    name = value.name, typeLabel = value.typeLabel, code = value.code, ouvrageId = value.ouvrageId,
                    latitude = value.latitude, longitude = value.longitude,
                    altitude = value.altitude, accuracyM = value.accuracyMeters,
                    serverUpdatedAt = value.serverUpdatedAt, isFieldMarker = value.isFieldMarker,
                )
            }
        }
    }

    private fun importLandmarkTypes(values: JSONArray?) {
        mg.hydria.shared.navigation.GeoPageImportGateway.importLandmarkTypes(values) { value ->
            store.geoUpsertServerLandmarkType(
                serverId = value.serverId, name = value.name, description = value.description,
                iconKey = value.iconKey, colorHex = value.colorHex, displayOrder = value.displayOrder,
                isActive = value.isActive, serverUpdatedAt = value.serverUpdatedAt,
            )
        }
    }

    fun allEntities(categories: Set<GeoCategory> = GeoCategory.entries.toSet(), limit: Int? = null): List<GeoEntity> =
        store.geoAllEntities(categories.mapTo(mutableSetOf()) { it.storageKey }, limit).map { it.toGeoEntity() }

    fun nearby(latitude: Double, longitude: Double, radiusMeters: Double, limit: Int = 300): List<GeoEntity> =
        store.geoNearby(latitude, longitude, radiusMeters, limit).map { it.toGeoEntity() }

    fun withinBounds(
        north: Double, south: Double, east: Double, west: Double,
        centerLatitude: Double, centerLongitude: Double, limit: Int = 600,
    ): List<GeoEntity> = store.geoWithinBounds(north, south, east, west, centerLatitude, centerLongitude, limit).map { it.toGeoEntity() }

    fun landmarkTypes(): List<Pair<String, String>> = store.geoLandmarkTypes()

    fun placementCandidates(category: GeoCategory): List<PlacementCandidate> =
        store.geoPlacementCandidates(category.storageKey).map { it.toPlacementCandidate(category) }

    fun placementCandidate(category: GeoCategory, entityId: String): PlacementCandidate? =
        store.geoPlacementCandidate(category.storageKey, entityId)?.toPlacementCandidate(category)

    fun markCandidatePhotoQueued(category: GeoCategory, entityId: String) = store.geoMarkCandidatePhotoQueued(category.storageKey, entityId)

    fun nearbyVillageIds(latitude: Double, longitude: Double, radiusMeters: Double = 25_000.0): Set<String> =
        store.geoNearbyVillageIds(latitude, longitude, radiusMeters)

    fun candidateIdsServingNearbyVillages(
        category: GeoCategory, latitude: Double, longitude: Double, radiusMeters: Double = 25_000.0,
    ): Set<String> = store.geoCandidateIdsServingNearbyVillages(category.storageKey, latitude, longitude, radiusMeters)

    fun placeCandidate(candidate: PlacementCandidate, position: CapturedPosition): Pair<GeoEntity, String> {
        val (entityJson, localUuid) = store.geoPlaceCandidate(
            entityId = candidate.id, category = candidate.category.storageKey, name = candidate.name, code = candidate.code,
            latitude = position.latitude, longitude = position.longitude, altitude = position.altitude, accuracyM = position.accuracyMeters,
            captureMethod = position.method, capturedAt = position.capturedAt, serverUpdatedAt = candidate.serverUpdatedAt,
        )
        return entityJson.toGeoEntity() to localUuid
    }

    fun createLandmark(
        name: String, typeId: String, position: CapturedPosition, category: GeoCategory = GeoCategory.LANDMARK,
    ): GeoEntity = store.geoCreateLandmark(
        name, typeId, position.latitude, position.longitude, position.altitude, position.accuracyMeters, position.method, position.capturedAt,
        category.storageKey,
    ).toGeoEntity()

    fun updatePosition(entity: GeoEntity, position: CapturedPosition): String = store.geoUpdatePosition(
        entity.category.storageKey, entity.id, position.latitude, position.longitude, position.altitude, position.accuracyMeters,
        position.method, position.capturedAt,
    )

    fun archiveLandmark(entity: GeoEntity): String {
        require(entity.isFieldMarker)
        return store.geoArchiveLandmark(entity.category.storageKey, entity.id)
    }


}
