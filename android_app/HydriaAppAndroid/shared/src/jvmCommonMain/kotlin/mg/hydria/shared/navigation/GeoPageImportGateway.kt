package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.GeoCategory
import org.json.JSONArray
import org.json.JSONObject

/** Call inside the caller's import transaction. */
object GeoPageImportGateway {
    fun importPage(
        body: JSONObject,
        importItems: (JSONArray?, GeoCategory, String) -> Unit,
        importLandmarkTypes: (JSONArray?) -> Unit,
        archiveSynced: (String, String) -> Unit,
    ): Int {
        val page = body.optJSONObject("data") ?: body
        val entities = page.optJSONObject("entities") ?: page
        var imported = 0
            fun load(names: List<String>, category: GeoCategory) {
                val values = names.firstNotNullOfOrNull { entities.optJSONArray(it) } ?: return
                imported += values.length()
                importItems(values, category, "")
            }
            load(listOf("villages"), GeoCategory.VILLAGE)
            load(listOf("points_eau", "water_points"), GeoCategory.WATER_POINT)
            load(listOf("equipements", "equipments"), GeoCategory.EQUIPMENT)
            load(listOf("reperes", "landmarks"), GeoCategory.LANDMARK)
            importLandmarkTypes(entities.optJSONArray("types_reperes") ?: page.optJSONArray("types_reperes"))
            val deletions = page.optJSONArray("deletions") ?: page.optJSONArray("suppressions") ?: JSONArray()
            for (index in 0 until deletions.length()) {
                val item = deletions.optJSONObject(index) ?: continue
                val kind = item.optString("entity_kind").ifBlank { item.optString("category") }
                val id = item.optString("entity_id").ifBlank { item.optString("id") }
                if (kind.isNotBlank() && id.isNotBlank()) archiveSynced(kind, id)
            }
        return imported
    }

    fun importSnapshot(
        snapshot: JSONObject?,
        importItems: (JSONArray?, GeoCategory, String) -> Unit,
        importLandmarkTypes: (JSONArray?) -> Unit,
    ) {
        if (snapshot == null) return
            val terrainWorks = snapshot.optJSONObject("terrain")?.optJSONArray("ouvrages") ?: JSONArray()
            for (workIndex in 0 until terrainWorks.length()) {
                val work = terrainWorks.optJSONObject(workIndex) ?: continue
                val workId = work.optString("id")
                importItems(work.optJSONArray("points_eau"), GeoCategory.WATER_POINT, workId)
                importItems(work.optJSONArray("equipements"), GeoCategory.EQUIPMENT, workId)
            }
            val navigation = snapshot.optJSONObject("navigation")
            importItems(navigation?.optJSONArray("villages"), GeoCategory.VILLAGE, "")
            importItems(navigation?.optJSONArray("reperes"), GeoCategory.LANDMARK, "")
            importLandmarkTypes(navigation?.optJSONArray("types_reperes"))
    }

    fun importLandmarkTypes(values: JSONArray?, save: (LandmarkTypeImport) -> Unit) {
        if (values == null) return
        for (index in 0 until values.length()) {
            val item = values.optJSONObject(index) ?: continue
            val serverId = item.optString("id")
            if (serverId.isBlank()) continue
            save(LandmarkTypeImport(
                serverId = serverId, name = item.optString("nom"), description = item.optString("description"),
                iconKey = item.optString("icone", "autre"), colorHex = item.optString("couleur", "#58D594"),
                displayOrder = item.optInt("ordre_affichage").toLong(), isActive = item.optBoolean("actif", true),
                serverUpdatedAt = item.optString("updated_at"),
            ))
        }
    }

}
