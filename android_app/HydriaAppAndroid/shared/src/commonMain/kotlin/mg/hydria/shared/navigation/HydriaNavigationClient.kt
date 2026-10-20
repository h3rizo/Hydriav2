package mg.hydria.shared.navigation

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.statement.HttpResponse
import io.ktor.http.HttpHeaders
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.contentOrNull
import mg.hydria.shared.network.HydriaHttpClient
import mg.hydria.shared.network.HydriaResult
import mg.hydria.shared.network.toHydriaResult
import mg.hydria.shared.network.toSyncForm

/**
 * Clients Ktor pour le domaine Navigation terrain : config/entities en
 * GET, positions/reperes/photos en POST formulaire. Miroirs de
 * HydriaApi.navigationConfig()/navigationEntities()/
 * saveNavigationPosition()/saveNavigationLandmark()/saveNavigationPhoto().
 * Branche via HydriaOperationsGateway et un repli par domaine pour la session.
 */
object HydriaNavigationClient {
    suspend fun config(client: HttpClient, token: String): HydriaResult = result(
        client.get("/navigation-terrain/api/mobile/config/") {
            header(HttpHeaders.Authorization, "Token $token")
        }
    )

    suspend fun entities(client: HttpClient, token: String, cursor: String?, bbox: String?, limit: Int = 500): HydriaResult = result(
        client.get("/navigation-terrain/api/mobile/entities/") {
            header(HttpHeaders.Authorization, "Token $token")
            parameter("limit", limit)
            cursor?.takeIf { it.isNotBlank() }?.let { parameter("cursor", it) }
            bbox?.takeIf { it.isNotBlank() }?.let { parameter("bbox", it) }
        }
    )

    /** Itinéraire routier position GPS -> entité (profil moto/voiture/pied), calculé par le serveur. */
    suspend fun route(
        client: HttpClient, token: String,
        fromLat: Double, fromLon: Double, toLat: Double, toLon: Double, profile: String,
    ): HydriaResult = result(
        client.get("/navigation-terrain/api/mobile/itineraire/") {
            header(HttpHeaders.Authorization, "Token $token")
            parameter("from_lat", fromLat); parameter("from_lon", fromLon)
            parameter("to_lat", toLat); parameter("to_lon", toLon)
            parameter("profil", profile)
        }
    )

    suspend fun savePosition(client: HttpClient, token: String, payload: JsonObject): HydriaResult = result(
        HydriaHttpClient.postForm(client, "/navigation-terrain/api/mobile/positions/upsert/", token, payload.toSyncForm())
    )

    suspend fun saveLandmark(client: HttpClient, token: String, payload: JsonObject): HydriaResult {
        val operationType = (payload["operation_type"])?.jsonPrimitive?.contentOrNull
        val id = (payload["id"])?.jsonPrimitive?.contentOrNull.orEmpty()
        val path = if (operationType == "landmark_archive") {
            "/navigation-terrain/api/mobile/reperes/$id/archive/"
        } else {
            "/navigation-terrain/api/mobile/reperes/upsert/"
        }
        return result(HydriaHttpClient.postForm(client, path, token, payload.toSyncForm()))
    }

    suspend fun savePhoto(client: HttpClient, token: String, payload: JsonObject): HydriaResult {
        val entityId = (payload["entity_id"])?.jsonPrimitive?.contentOrNull.orEmpty()
        return result(
            HydriaHttpClient.postForm(client, "/navigation-terrain/api/mobile/reperes/$entityId/photos/", token, payload.toSyncForm())
        )
    }

    private suspend fun result(response: HttpResponse): HydriaResult {
        return response.toHydriaResult()
    }
}
