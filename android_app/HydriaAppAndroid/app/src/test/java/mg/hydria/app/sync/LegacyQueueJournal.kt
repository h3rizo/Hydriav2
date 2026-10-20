package mg.hydria.app.sync

import org.json.JSONArray
import org.json.JSONObject

object LegacyQueueJournal {
    fun payloadDetails(item: JSONObject): String {
        val payload = item.optJSONObject("payload") ?: JSONObject()
        val operation = payload.optString("operation_type")
        return when (item.optString("type")) {
            "reading" -> buildString {
                append("Point : ${payload.optString("point_eau_id")}\nDate : ${payload.optString("date_releve")}\nNouvel index : ${payload.optString("nouvel_index")}")
                val nbCartes = runCatching { JSONArray(payload.optString("cartes_sociales", "[]")).length() }.getOrDefault(0)
                if (nbCartes > 0) append("\nCartes sociales : $nbCartes")
            }
            "terrain_photo" -> {
                val target = payload.optString("point_id").ifBlank { payload.optString("equipment_id") }
                val estimatedKb = payload.optString("photo_data").length * 3 / 4 / 1024
                "${if (operation == "photo_equipment") "Équipement" else "Point d'eau"} : $target\nPhoto compressée : environ $estimatedKb Ko"
            }
            "terrain_data" -> when (operation) {
                "update_point" -> buildString {
                    append("Point : ${payload.optString("point_id")}")
                    if (payload.has("subscriber_name")) append("\nNom : ${payload.optString("subscriber_name")}")
                    if (payload.has("telephone")) append("\nTéléphone : ${payload.optString("telephone")}")
                    if (payload.has("latitude")) append("\nGPS : ${payload.optString("latitude")}, ${payload.optString("longitude")}")
                }
                "flow_measure" -> "Ouvrage : ${payload.optString("ouvrage_id")}\nDate : ${payload.optString("date")}\nDébit : ${payload.optString("debit_l_s")} L/s"
                "head_meter_reading" -> "Compteur : ${payload.optString("meter_id")}\nDate : ${payload.optString("date")}\nIndex : ${payload.optString("new_index")}"
                else -> "Opération Terrain : $operation"
            }
            "save_repair" -> "Réparation · ${payload.optString("date")}\nOuvrage : ${payload.optString("ouvrage_id")}"
            "save_planning" -> "Planning · ${payload.optString("date")}\nOuvrage : ${payload.optString("ouvrage_id")}"
            else -> "Identifiant local : ${item.optString("local_uuid")}"
        }
    }

    fun serverConflictDetails(conflict: JSONObject): String {
        val server = conflict.optJSONObject("server_value")
        return buildString {
            append("Version serveur")
            conflict.optString("server_updated_at").takeIf { it.isNotBlank() }?.let {
                append("\nModifiée le : $it")
            }
            if (server == null) {
                append("\nLe détail serveur sera chargé au prochain essai de synchronisation.")
                return@buildString
            }
            if (server.has("subscriber_name")) append("\nNom : ${server.optString("subscriber_name").ifBlank { "Non renseigné" }}")
            if (server.has("telephone")) append("\nTéléphone : ${server.optString("telephone").ifBlank { "Non renseigné" }}")
            if (server.optBoolean("has_coordinates", false)) {
                append("\nGPS : ${server.optString("latitude")}, ${server.optString("longitude")}")
            } else if (server.has("has_coordinates")) append("\nGPS : non renseigné")
            if (server.has("has_photo")) append("\nPhoto : ${if (server.optBoolean("has_photo")) "présente" else "absente"}")
        }
    }

    fun journal(items: List<JSONObject>): String = if (items.isEmpty()) "Aucune opération dans la file." else items.joinToString("\n\n") { item ->
            buildString {
                append(item.optString("type"))
                append(" · tentative ${item.optInt("retry_count")}")
                item.optString("last_error").takeIf { it.isNotBlank() }?.let { append("\n$it") }
                append("\n${payloadDetails(item)}")
            }
        }
}
