package mg.hydria.shared.terrain

import org.json.JSONObject

object TerrainConfirmationGateway {
    fun error(type: String, payload: JSONObject, body: JSONObject): String? =
        TerrainConfirmationRules.error(
            type, payload.optString("operation_type"),
            if (payload.has("subscriber_name")) payload.optString("subscriber_name") else null,
            payload.has("latitude") || payload.has("longitude"),
            body.optJSONObject("server_value")?.let {
                TerrainServerConfirmation(it.optBoolean("has_photo",false),
                    it.optString("subscriber_name"),it.optBoolean("has_coordinates",false))
            },
        )
}
