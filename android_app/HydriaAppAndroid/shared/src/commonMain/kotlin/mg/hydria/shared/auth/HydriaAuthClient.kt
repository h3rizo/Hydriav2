package mg.hydria.shared.auth

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import kotlinx.serialization.json.JsonObject
import mg.hydria.shared.network.HydriaHttpClient
import mg.hydria.shared.network.HydriaResult

/**
 * Client d'authentification mobile, Phase 1 de la migration KMP ("modeles +
 * acces API generiques"). Reprend EXACTEMENT le contrat de
 * mg.hydria.app.HydriaApi.login() (meme endpoint, meme form-encoding) pour
 * valider la chaine Ktor + kotlinx.serialization de bout en bout sur un cas
 * reel.
 *
 * Pas encore branche sur l'app : HydriaApi reste la seule source de verite
 * pour la connexion tant que ce chemin n'a pas ete valide contre le serveur
 * de production (meme discipline que HydriaHttpClient en Phase 0 - les deux
 * implementations cohabitent jusqu'a validation, cf. le plan de migration).
 */
object HydriaAuthClient {
    suspend fun login(client: HttpClient, username: String, password: String, deviceLabel: String): HydriaResult {
        val response = HydriaHttpClient.postForm(
            client = client,
            path = "/mobile/api/login/",
            token = null,
            form = mapOf("username" to username, "password" to password, "device_label" to deviceLabel),
        )
        val body = runCatching { response.body<JsonObject>() }.getOrElse { JsonObject(emptyMap()) }
        return HydriaResult(response.status.value, body)
    }
}
