package mg.hydria.shared.plannings

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.statement.HttpResponse
import io.ktor.http.HttpHeaders
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import mg.hydria.shared.network.HydriaHttpClient
import mg.hydria.shared.network.HydriaResult
import mg.hydria.shared.network.toHydriaResult
import mg.hydria.shared.network.toSyncForm

/**
 * Clients Ktor pour le domaine Plannings : preparer-tournee, factures d'un
 * point d'eau (GET + token) et enregistrement planning/reparation (POST
 * formulaire, meme liste de champs que HydriaApi.savePlanningLike()).
 * Branche via HydriaOperationsGateway et un repli par domaine pour la session.
 */
object HydriaPlanningsClient {
    private val savableFields = listOf("id", "employe_id", "fiche_poste_id", "ouvrage_id", "date", "remarque", "statut", "priorite",
        "equipement_id", "point_eau_id", "composants_ids")

    suspend fun prepareTour(client: HttpClient, token: String, horizonJours: Int = 14, snapshotVersion: String? = null): HydriaResult =
        result(
            client.get("/plannings/api/preparer-tournee/") {
                header(HttpHeaders.Authorization, "Token $token")
                parameter("horizon_jours", horizonJours)
                snapshotVersion?.takeIf { it.isNotBlank() }?.let { parameter("snapshot_version", it) }
            }
        )

    suspend fun pointInvoices(client: HttpClient, token: String, pointId: String): HydriaResult = result(
        client.get("/plannings/api/mobile/point-eau/$pointId/factures/") {
            header(HttpHeaders.Authorization, "Token $token")
        }
    )

    suspend fun saveRepair(client: HttpClient, token: String, payload: JsonObject): HydriaResult =
        saveLike(client, token, payload, "/plannings/api/mobile/reparation/enregistrer/")

    suspend fun savePlanning(client: HttpClient, token: String, payload: JsonObject): HydriaResult =
        saveLike(client, token, payload, "/plannings/api/mobile/planning/enregistrer/")

    /** Photo preuve jointe a une reparation : s'accumule cote serveur (Planning.photo),
     * contrairement a une photo Terrain qui remplace. Meme route que HydriaApi.saveRepairPhoto
     * (Android), transport Ktor en plus pour la reutiliser depuis Desktop. */
    suspend fun saveRepairPhoto(client: HttpClient, token: String, payload: JsonObject): HydriaResult {
        val planningId = payload["planning_id"]?.jsonPrimitive?.contentOrNull.orEmpty()
        return result(HydriaHttpClient.postForm(
            client, "/plannings/api/mobile/reparation/$planningId/photo/", token, payload.toSyncForm(),
        ))
    }

    private suspend fun saveLike(client: HttpClient, token: String, payload: JsonObject, path: String): HydriaResult {
        val form = payload.toSyncForm().filterKeys { it in savableFields }
        return result(HydriaHttpClient.postForm(client, path, token, form))
    }

    private suspend fun result(response: HttpResponse): HydriaResult {
        return response.toHydriaResult()
    }
}
