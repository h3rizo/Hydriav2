package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.GeoCategory
import mg.hydria.shared.navigation.model.PlacementCandidate
import org.json.JSONObject

object NavigationPhotoPayloads {
    fun create(candidate: PlacementCandidate, encoded: String, localUuid: String): JSONObject {
        val equipment = candidate.category == GeoCategory.EQUIPMENT
        return JSONObject()
            .put("local_uuid", localUuid)
            .put("operation_type", if (equipment) "photo_equipment" else "photo_point")
            .put(if (equipment) "equipment_id" else "point_id", candidate.id)
            .put("photo_data", encoded)
            .put("content_type", "image/jpeg")
            .put("filename", if (equipment) "equipement-terrain.jpg" else "point-eau-terrain.jpg")
            .put("base_updated_at", candidate.serverUpdatedAt)
    }
}
