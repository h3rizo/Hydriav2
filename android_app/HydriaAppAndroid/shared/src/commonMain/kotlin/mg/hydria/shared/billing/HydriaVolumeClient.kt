package mg.hydria.shared.billing

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.contentType
import kotlinx.serialization.json.JsonObject
import mg.hydria.shared.network.HydriaResult
import mg.hydria.shared.network.toHydriaResult

/**
 * Clients Ktor pour le Volumetrique (Facturation/Encaissement mobile) :
 * /facturation/api/mobile/volume/bootstrap/ (GET) et
 * /facturation/api/mobile/volume/sync/ (POST JSON). Miroirs de
 * HydriaApi.volumeBootstrap()/volumeOperation() : meme contrat, la
 * suppression des cles "_sync_*" (metadonnees de file d'attente locale,
 * jamais envoyees au serveur) est effectuee ici avant l'envoi JSON.
 * Branche via HydriaOperationsGateway et le repli de session Volume.
 */
object HydriaVolumeClient {
    suspend fun bootstrap(client: HttpClient, token: String, ouvrageId: String = "", month: String = ""): HydriaResult {
        val response = client.get("/facturation/api/mobile/volume/bootstrap/") {
            header(HttpHeaders.Authorization, "Token $token")
            parameter("ouvrage_id", ouvrageId)
            parameter("mois", month)
        }
        return response.toHydriaResult()
    }

    suspend fun syncOperation(client: HttpClient, token: String, payload: JsonObject): HydriaResult {
        val response = client.post("/facturation/api/mobile/volume/sync/") {
            header(HttpHeaders.Authorization, "Token $token")
            contentType(ContentType.Application.Json)
            setBody(JsonObject(payload.filterKeys { !it.startsWith("_sync_") }))
        }
        return response.toHydriaResult()
    }
}
