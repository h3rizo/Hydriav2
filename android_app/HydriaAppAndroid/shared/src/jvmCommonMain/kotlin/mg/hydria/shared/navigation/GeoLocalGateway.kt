package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.*
import org.json.JSONObject

/** Decodes the local storage schema, distinct from the server import schema. */
object GeoLocalGateway {
    fun entity(row: JSONObject): GeoEntity = with(row) { GeoEntity(
        id = getString("entity_id"), category = GeoCategory.fromStorage(getString("category")), name = getString("name"),
        typeLabel = optString("type_label"), code = optString("code"), ouvrageId = optString("ouvrage_id"),
        latitude = getDouble("latitude"), longitude = getDouble("longitude"),
        altitude = if (isNull("altitude") || !has("altitude")) null else optDouble("altitude").takeIf { it.isFinite() },
        accuracyMeters = if (isNull("accuracy_m") || !has("accuracy_m")) null else optDouble("accuracy_m").takeIf { it.isFinite() },
        syncState = optString("sync_state", "synced"), serverUpdatedAt = optString("server_updated_at"),
        isFieldMarker = optBoolean("is_field_marker", false),
    ) }

    fun placement(row: JSONObject, category: GeoCategory): PlacementCandidate = with(row) { PlacementCandidate(
        id = getString("entity_id"), category = category, name = getString("name"),
        code = optString("code"), villageName = optString("village_name"),
        referenceLatitude = if (isNull("reference_latitude") || !has("reference_latitude")) null else optDouble("reference_latitude").takeIf { it.isFinite() },
        referenceLongitude = if (isNull("reference_longitude") || !has("reference_longitude")) null else optDouble("reference_longitude").takeIf { it.isFinite() },
        hasPhoto = optBoolean("has_photo", false),
        servedVillageIds = optString("served_village_ids").split(',').filter { it.isNotBlank() }.toSet(),
        ouvrageId = optString("ouvrage_id"), serverUpdatedAt = optString("server_updated_at"),
    ) }

}
