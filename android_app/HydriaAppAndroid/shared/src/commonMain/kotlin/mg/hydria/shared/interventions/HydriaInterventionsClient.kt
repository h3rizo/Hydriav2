package mg.hydria.shared.interventions

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.ContentType
import io.ktor.http.encodeURLParameter
import io.ktor.http.HttpHeaders
import io.ktor.http.contentType
import kotlinx.serialization.json.JsonObject
import mg.hydria.shared.network.HydriaHttpClient
import mg.hydria.shared.network.HydriaResult
import mg.hydria.shared.network.toHydriaResult

/**
 * Clients Ktor pour le domaine Interventions, miroirs de
 * HydriaApi.interventions()/postponeIntervention()/deleteIntervention()/
 * interventionOptions()/updateIntervention(). Meme contrat : liste GET
 * paginee, report/suppression en POST formulaire (ou formulaire vide pour
 * la suppression), options en GET, mise a jour en POST JSON. Branche via
 * HydriaOperationsGateway et le repli de session Interventions.
 */
object HydriaInterventionsClient {
    suspend fun list(
        client: HttpClient,
        token: String,
        page: Int = 1,
        includeOtherBases: Boolean = false,
        status: String = "",
        sort: String = "created",
    ): HydriaResult = result(
        client.get("/recherche/api/mobile/interventions/") {
            header(HttpHeaders.Authorization, "Token $token")
            parameter("page", page)
            parameter("page_size", 20)
            parameter("all_bases", if (includeOtherBases) 1 else 0)
            parameter("status", status)
            parameter("sort", sort)
        }
    )

    suspend fun postpone(client: HttpClient, token: String, planningId: String, date: String): HydriaResult = result(
        HydriaHttpClient.postForm(
            client, "/recherche/api/mobile/interventions/${encoded(planningId)}/reporter/", token, mapOf("date" to date),
        )
    )

    suspend fun delete(client: HttpClient, token: String, planningId: String): HydriaResult = result(
        HydriaHttpClient.postForm(
            client, "/recherche/api/mobile/interventions/${encoded(planningId)}/supprimer/", token, emptyMap(),
        )
    )

    suspend fun options(client: HttpClient, token: String, workId: String): HydriaResult = result(
        client.get("/recherche/ouvrages/${encoded(workId)}/interventions/options/") {
            header(HttpHeaders.Authorization, "Token $token")
        }
    )

    suspend fun update(client: HttpClient, token: String, workId: String, planningId: String, payload: JsonObject): HydriaResult = result(
        client.post("/recherche/ouvrages/${encoded(workId)}/interventions/${encoded(planningId)}/modifier/") {
            header(HttpHeaders.Authorization, "Token $token")
            contentType(ContentType.Application.Json)
            setBody(payload)
        }
    )

    private suspend fun result(response: HttpResponse): HydriaResult {
        return response.toHydriaResult()
    }
    private fun encoded(value: String): String = value.encodeURLParameter(spaceToPlus = true)
}
