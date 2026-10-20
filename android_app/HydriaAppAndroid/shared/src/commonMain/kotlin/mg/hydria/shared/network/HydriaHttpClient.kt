package mg.hydria.shared.network

import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngineFactory
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.request.forms.FormDataContent
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.HttpHeaders
import io.ktor.http.Parameters
import io.ktor.http.URLProtocol
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

/**
 * Client Ktor partage, destine a remplacer HydriaApi.kt (HttpURLConnection
 * manuel dans app/) endpoint par endpoint (Phase 1 du plan de migration
 * KMP). Reprend a l'identique le contrat reseau actuel du backend Django :
 *  - base URL https://www.hydria.mg
 *  - authentification par en-tete "Authorization: Token <token>"
 *  - POST en x-www-form-urlencoded (PAS de JSON REST) pour les endpoints
 *    d'ecriture existants - rien ne change cote serveur.
 *
 * Branche sur l'app via HydriaOperationsGateway et HydriaNetwork : chaque
 * domaine possede un repli HydriaApi partage pour toute la session.
 * Le login conserve HydriaAuthGateway et son repli deja en place.
 *
 * Le plafond HttpTimeout ci-dessous s'applique donc a TOUS les appels
 * partages ; il est cale sur le plus lent (le prechargement Terrain) et
 * reste large pour les autres.
 */
object HydriaHttpClient {
    const val BASE_URL = "https://www.hydria.mg"

    val json: Json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        encodeDefaults = true
    }

    fun create(engineFactory: HttpClientEngineFactory<*> = hydriaEngine): HttpClient = HttpClient(engineFactory) {
        install(ContentNegotiation) { json(json) }
        install(HttpTimeout) {
            // Aligne sur HydriaApi.request() (app/) : connexion 15 s, lecture
            // 120 s. Le premier prechargement /plannings/api/preparer-tournee/
            // d'un compte de coordination pese plusieurs centaines d'ouvrages
            // et points d'eau ; les autres appels n'approchent jamais ce plafond.
            connectTimeoutMillis = 15_000L
            requestTimeoutMillis = 120_000L
            socketTimeoutMillis = 120_000L
        }
        defaultRequest {
            url {
                protocol = URLProtocol.HTTPS
                host = "www.hydria.mg"
            }
            header(HttpHeaders.UserAgent, "HydriaTerrainKMP/1.0")
            header(HttpHeaders.Accept, "application/json")
        }
    }

    suspend fun get(client: HttpClient, path: String, token: String?): HttpResponse = client.get(path) {
        applyAuth(token)
    }

    /** POST x-www-form-urlencoded, identique au contrat HydriaApi.request(form = ...) actuel. */
    suspend fun postForm(client: HttpClient, path: String, token: String?, form: Map<String, String>): HttpResponse =
        client.post(path) {
            applyAuth(token)
            setBody(FormDataContent(Parameters.build {
                form.forEach { (key, value) -> append(key, value) }
            }))
        }

    private fun io.ktor.client.request.HttpRequestBuilder.applyAuth(token: String?) {
        token?.takeIf { it.isNotBlank() }?.let { header(HttpHeaders.Authorization, "Token $it") }
    }
}
