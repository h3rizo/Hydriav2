package mg.hydria.shared.network

import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Meme interpretation des reponses que HydriaApi, quel que soit le Content-Type.
 * La lecture du transport reste hors du try : une coupure doit declencher le repli.
 * Une erreur HTTP ou un corps invalide reste un resultat serveur, sans rejouer le POST.
 */
internal suspend fun HttpResponse.toHydriaResult(): HydriaResult =
    decodeHydriaResponse(status.value, bodyAsText())

internal fun decodeHydriaResponse(status: Int, text: String): HydriaResult {
    val body = try {
        if (text.isBlank()) buildJsonObject { put("success", status in 200..299) }
        else HydriaHttpClient.json.parseToJsonElement(text) as? JsonObject
            ?: error("Objet JSON attendu")
    } catch (_: Exception) {
        val message = if (text.trimStart().startsWith("<!doctype html", ignoreCase = true) ||
            text.trimStart().startsWith("<html", ignoreCase = true)) {
            "Service de synchronisation indisponible (HTTP $status). Mettez à jour l'application ou réessayez plus tard."
        } else text.ifBlank { "Réponse serveur invalide (HTTP $status)" }
        buildJsonObject { put("success", false); put("error", message) }
    }
    return HydriaResult(status, body)
}
