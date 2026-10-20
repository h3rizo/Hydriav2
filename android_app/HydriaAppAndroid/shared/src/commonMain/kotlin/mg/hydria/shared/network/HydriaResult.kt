package mg.hydria.shared.network

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * Resultat generique d'un appel API Hydria via Ktor, meme contrat que
 * HydriaApi.Result (app/, HttpURLConnection) : success = code HTTP 2xx ET
 * le champ JSON "success" (absent = true), error = champ JSON "error" ou
 * message par defaut. Sert de base commune aux futurs clients partages
 * (auth, puis endpoint par endpoint - voir le plan de migration KMP).
 */
data class HydriaResult(val status: Int, val body: JsonObject) {
    val successful: Boolean
        get() = status in 200..299 && (body["success"] as? JsonPrimitive)?.booleanOrNull != false

    val error: String
        get() = (body["error"] as? JsonPrimitive)?.contentOrNull ?: "Erreur HTTP $status"
}
