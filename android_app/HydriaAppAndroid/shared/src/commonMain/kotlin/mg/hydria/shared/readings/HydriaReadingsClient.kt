package mg.hydria.shared.readings

import io.ktor.client.HttpClient
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import mg.hydria.shared.network.HydriaHttpClient
import mg.hydria.shared.network.HydriaResult
import mg.hydria.shared.network.toHydriaResult

/**
 * Client Ktor pour /facturation/api/save-releve-terrain/, cette fois un
 * POST x-www-form-urlencoded via HydriaHttpClient.postForm (meme helper
 * que HydriaAuthClient). Miroir de HydriaApi.saveReading() : reprend les
 * memes champs obligatoires + la meme liste de champs optionnels transmis
 * uniquement s'ils sont presents et non nuls dans le payload.
 * Branche via HydriaOperationsGateway et le repli de session Releves.
 */
object HydriaReadingsClient {
    private val optionalKeys = listOf(
        "local_uuid", "point_latitude", "point_longitude", "point_photo_data", "point_photo_name", "point_photo_type",
        "terrain_latitude", "terrain_longitude", "terrain_gps_accuracy_m", "terrain_distance_point_m", "terrain_captured_at",
        "montant", "ticket_local"
    )

    suspend fun saveReading(client: HttpClient, token: String, payload: JsonObject): HydriaResult {
        val form = buildMap {
            put("point_eau_id", requireNotNull(payload.stringFieldOrNull("point_eau_id")) { "point_eau_id manquant" })
            put("date_releve", requireNotNull(payload.stringFieldOrNull("date_releve")) { "date_releve manquante" })
            put("nouvel_index", payload.doubleField("nouvel_index").toString())
            put("volume_non_facture", (payload.doubleFieldOrNull("volume_non_facture") ?: 0.0).toString())
            put("remarque", payload.stringField("remarque"))
            put("cartes_sociales", payload.stringFieldOrNull("cartes_sociales") ?: "[]")
            optionalKeys.forEach { key ->
                val value = payload.stringFieldOrNull(key)
                if (value != null) put(key, value)
            }
        }
        val response = HydriaHttpClient.postForm(client, "/facturation/api/save-releve-terrain/", token, form)
        return response.toHydriaResult()
    }

    private fun JsonObject.stringField(key: String): String = stringFieldOrNull(key) ?: ""
    private fun JsonObject.stringFieldOrNull(key: String): String? = when (val value = this[key]) {
        null, JsonNull -> null
        is JsonPrimitive -> value.contentOrNull
        else -> value.toString()
    }
    private fun JsonObject.doubleField(key: String): Double = requireNotNull(doubleFieldOrNull(key)) { "$key invalide" }
    private fun JsonObject.doubleFieldOrNull(key: String): Double? = (this[key] as? JsonPrimitive)?.doubleOrNull
}
