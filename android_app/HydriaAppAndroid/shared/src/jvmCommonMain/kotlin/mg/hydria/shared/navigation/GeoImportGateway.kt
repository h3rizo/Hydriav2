package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.GeoCategory
import mg.hydria.shared.navigation.model.GeoEntity
import org.json.JSONObject

/** JSON decoding shared by the Android and desktop adapters; no storage side effects. */
object GeoImportGateway {
    fun entity(item: JSONObject, category: GeoCategory, ouvrageId: String): GeoEntity? {
            if (!item.has("latitude") || item.isNull("latitude") || !item.has("longitude") || item.isNull("longitude")) return null
            val latitude = item.optDouble("latitude", Double.NaN)
            val longitude = item.optDouble("longitude", Double.NaN)
            if (!GeoMath.isValid(latitude, longitude)) return null
            val entityCategory = if (category == GeoCategory.LANDMARK) {
                GeoCategory.fromStorage(item.optString("marker_category", category.storageKey))
            } else category
            return GeoEntity(
                id = item.optString("id"), category = entityCategory,
                name = item.optString("nom").ifBlank { item.optString("name", category.label) },
                typeLabel = item.optString("type").ifBlank { item.optString("type_label") },
                code = item.optString("code"), ouvrageId = item.optString("ouvrage_id").ifBlank { ouvrageId },
                latitude = latitude, longitude = longitude,
                altitude = item.optDoubleOrNull("altitude"),
                accuracyMeters = item.optDoubleOrNull("accuracy_m") ?: item.optDoubleOrNull("coordinates_accuracy"),
                serverUpdatedAt = item.optString("updated_at"),
                isFieldMarker = item.optBoolean("is_field_marker", category == GeoCategory.LANDMARK),
            )
    }

    fun placement(item: JSONObject, category: GeoCategory, fallbackOuvrageId: String): PlacementImport? {
        val id = item.optString("id")
        if (id.isBlank()) return null
        // Le serveur historique utilisait reference_* pour les coordonnées du
        // village. Elles ne signifient pas que l'entité elle-même possède un GPS.
        val referenceLatitude = item.optDoubleOrNull("latitude")
        val referenceLongitude = item.optDoubleOrNull("longitude")
        val servedVillageIds = if (item.has("village_ids") || item.has("village_id")) {
            buildList {
                val values = item.optJSONArray("village_ids")
                if (values != null) for (index in 0 until values.length()) {
                    values.optString(index).takeIf { it.isNotBlank() }?.let(::add)
                }
                item.optString("village_id").takeIf { it.isNotBlank() }?.let(::add)
            }.distinct().joinToString(",")
        } else null // null => le gateway conserve la valeur locale existante.
        return PlacementImport(
            entityId = id, category = category,
            name = item.optString("nom").ifBlank { item.optString("name", category.label) },
            code = item.optString("code"), villageName = item.optString("village"),
            referenceLatitude = referenceLatitude, referenceLongitude = referenceLongitude,
            hasPhoto = item.optBoolean("has_photo", false), servedVillageIds = servedVillageIds,
            ouvrageId = item.optString("ouvrage_id").ifBlank { fallbackOuvrageId }, serverUpdatedAt = item.optString("updated_at"),
        )
    }

    private fun JSONObject.optDoubleOrNull(key: String): Double? =
        if (!has(key) || isNull(key)) null else optDouble(key).takeIf { it.isFinite() }
}
