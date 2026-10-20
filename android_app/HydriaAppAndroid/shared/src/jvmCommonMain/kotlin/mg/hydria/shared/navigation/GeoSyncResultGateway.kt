package mg.hydria.shared.navigation

import org.json.JSONObject

object GeoSyncResultGateway {
    fun changes(type: String, payload: JSONObject, conflict: Boolean): List<GeoSyncChange> =
        GeoSyncResultRules.changes(
            GeoSyncOperation(
                type, payload.optString("local_category"), payload.optString("entity_kind"),
                payload.optString("entity_id"), payload.optString("local_uuid"),
                payload.optString("marker_category", "landmark"), payload.optString("id"),
            ),
            conflict,
        )
}
