package mg.hydria.shared.search

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.http.encodeURLParameter
import io.ktor.http.HttpHeaders
import mg.hydria.shared.network.toHydriaResult
import mg.hydria.shared.network.HydriaResult

/**
 * Clients Ktor pour le domaine Recherche (ouvrages/personnes), miroirs de
 * HydriaApi.search()/people()/works()/workFilters()/searchDetail()/
 * personDetail() : GET + token, parametres geres par Ktor `parameter(...)`
 * plutot que par concatenation manuelle. Branche via HydriaOperationsGateway
 * et le repli de session Recherche.
 */
object HydriaSearchClient {
    suspend fun workFilters(client: HttpClient, token: String): HydriaResult =
        get(client, token, "/recherche/api/mobile/ouvrages/filtres/")

    suspend fun search(client: HttpClient, token: String, query: String, types: Set<String>, page: Int = 1): HydriaResult =
        get(client, token, "/recherche/api/mobile/search/") {
            parameter("q", query)
            parameter("types", types.joinToString(","))
            parameter("page", page)
            parameter("page_size", 20)
        }

    suspend fun people(
        client: HttpClient,
        token: String,
        query: String,
        type: String,
        status: String,
        page: Int = 1,
    ): HydriaResult = get(client, token, "/recherche/api/mobile/personnes/") {
        parameter("search", query)
        parameter("type", type)
        parameter("statut", status)
        parameter("page", page)
    }

    suspend fun works(
        client: HttpClient,
        token: String,
        query: String,
        page: Int = 1,
        region: String = "",
        district: String = "",
        commune: String = "",
        employee: String = "",
    ): HydriaResult = get(client, token, "/recherche/api/mobile/ouvrages/") {
        parameter("q", query)
        parameter("page", page)
        parameter("page_size", 20)
        parameter("region", region)
        parameter("district", district)
        parameter("commune", commune)
        parameter("employee", employee)
    }

    suspend fun searchDetail(client: HttpClient, token: String, type: String, id: String): HydriaResult =
        get(client, token, "/recherche/api/mobile/details/${encoded(type)}/${encoded(id)}/")

    suspend fun personDetail(client: HttpClient, token: String, type: String, id: String): HydriaResult =
        get(client, token, "/recherche/api/mobile/personnes/${encoded(type)}/${encoded(id)}/")

    private suspend fun get(
        client: HttpClient,
        token: String,
        path: String,
        block: io.ktor.client.request.HttpRequestBuilder.() -> Unit = {},
    ): HydriaResult {
        val response = client.get(path) {
            header(HttpHeaders.Authorization, "Token $token")
            block()
        }
        return response.toHydriaResult()
    }
    private fun encoded(value: String): String = value.encodeURLParameter(spaceToPlus = true)
}
