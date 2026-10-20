package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.*
import org.json.JSONObject

object GeoOperationPayloads {
    private fun position(
        entityKind: String, localCategory: String, entityId: String, localUuid: String,
        captured: CapturedPosition, baseUpdatedAt: String, replaceConfirmed: Boolean,
    ): JSONObject = JSONObject()
        .put("operation_type", "geo_position_upsert").put("local_uuid", localUuid)
        .put("entity_kind", entityKind).put("local_category", localCategory).put("entity_id", entityId)
        .put("latitude", captured.latitude).put("longitude", captured.longitude)
        .put("altitude", captured.altitude).put("accuracy_m", captured.accuracyMeters)
        .put("captured_at", captured.capturedAt).put("capture_method", captured.method)
        .put("base_updated_at", baseUpdatedAt).put("replace_confirmed", replaceConfirmed)

    fun updatePosition(entity: GeoEntity, localUuid: String, captured: CapturedPosition): JSONObject =
        position(if (entity.isFieldMarker) GeoCategory.LANDMARK.storageKey else entity.category.storageKey,
            entity.category.storageKey, entity.id, localUuid, captured, entity.serverUpdatedAt, true)

    fun placeCandidate(candidate: PlacementCandidate, entityId: String, localUuid: String,
        captured: CapturedPosition, replaceConfirmed: Boolean): JSONObject =
        position(candidate.category.storageKey, candidate.category.storageKey, entityId, localUuid,
            captured, candidate.serverUpdatedAt, replaceConfirmed)

    fun createLandmark(entity: GeoEntity, markerCategory: GeoCategory, typeId: String, captured: CapturedPosition): JSONObject =
        JSONObject().put("operation_type", "landmark_upsert").put("id", entity.id).put("local_uuid", entity.id)
            .put("marker_category", markerCategory.storageKey).put("nom", entity.name).put("type_repere_id", typeId)
            .put("latitude", captured.latitude).put("longitude", captured.longitude).put("altitude", captured.altitude)
            .put("accuracy_m", captured.accuracyMeters).put("captured_at", captured.capturedAt)
            .put("capture_method", captured.method)

    fun archiveLandmark(entity: GeoEntity, localUuid: String): JSONObject =
        JSONObject().put("operation_type", "landmark_archive").put("id", entity.id)
            .put("marker_category", entity.category.storageKey).put("local_uuid", localUuid)
}
