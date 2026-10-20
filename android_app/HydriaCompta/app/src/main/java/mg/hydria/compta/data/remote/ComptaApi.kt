package mg.hydria.compta.data.remote

import android.util.Log
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Client HTTP léger pour l'API mobile comptabilité. Même approche que l'objet
 * `HydriaApi` de l'app terrain : `HttpURLConnection` + `org.json`, en-tête
 * `Authorization: Token <clé>`, pas de gestion gzip manuelle (décompression
 * transparente de `HttpURLConnection`).
 *
 * Login : `/mobile/api/login/` (jeton `scope='mobile'` longue durée).
 * Sync   : `/api/mobile/v1/compta/` (tous les endpoints).
 */
class ComptaApi(
    private val baseUrl: String,
    private val tokenProvider: () -> String?,
) {

    data class Response(val status: Int, val body: JSONObject) {
        val successful: Boolean get() = status in 200..299
        val isAuthError: Boolean get() = status == 401 || status == 403
        val error: String get() = body.optString("message", body.optString("error", "Erreur HTTP $status"))
    }

    private val root get() = "$baseUrl/api/mobile/v1/compta"

    // ---- Auth ----

    fun login(username: String, password: String, deviceId: String, deviceLabel: String): Response =
        request(
            path = "$baseUrl/mobile/api/login/",
            method = "POST",
            form = mapOf(
                "username" to username,
                "password" to password,
                "device_label" to deviceLabel,
            ),
            authenticated = false,
        )

    /** Pas de refresh sur le jeton mobile actuel : renvoie le jeton inchangé. */
    fun refresh(refreshToken: String): Response =
        Response(200, JSONObject().put("access_token", refreshToken).put("refresh_token", refreshToken))

    // ---- Synchronisation ----

    fun bootstrap(): Response = request("$root/bootstrap", "GET")

    fun soldes(): Response = request("$root/soldes", "GET")

    fun verificationScansRecap(): Response = request("$root/verification-scans", "GET")

    fun verificationScansDetail(mois: String, fichier: String, statut: String, page: Int): Response {
        val query = listOf(
            "mois" to mois,
            "fichier" to fichier,
            "statut" to statut,
            "page" to page.toString(),
        ).joinToString("&") { (k, v) -> "${URLEncoder.encode(k, "UTF-8")}=${URLEncoder.encode(v, "UTF-8")}" }
        return request("$root/verification-scans/detail?$query", "GET")
    }

    fun changes(since: String): Response =
        request("$root/changes?since=${URLEncoder.encode(since, "UTF-8")}", "GET")

    fun pushMutations(mutations: JSONObject): Response =
        request("$root/mutations", "POST", json = mutations)

    fun mutationStatus(localUuid: String): Response =
        request("$root/mutations/$localUuid", "GET")

    fun allocateInvoiceRange(deviceId: String): Response =
        request("$root/devices/$deviceId/invoice-range", "POST", json = JSONObject())

    // ---- Transport ----

    private fun request(
        path: String,
        method: String,
        json: JSONObject? = null,
        form: Map<String, String>? = null,
        authenticated: Boolean = true,
    ): Response {
        val token = if (authenticated) tokenProvider()?.takeIf { it.isNotBlank() } else null
        Log.d(TAG, "$method $path (auth=${if (token != null) "token[${token.length}]" else "AUCUN"})")

        val connection = URL(path).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = method
            connection.connectTimeout = 15_000
            connection.readTimeout = 120_000 // bootstrap = payload volumineux
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("User-Agent", "HydriaComptaAndroid/0.1")
            if (token != null) connection.setRequestProperty("Authorization", "Token $token")

            when {
                json != null -> {
                    val bytes = json.toString().toByteArray(Charsets.UTF_8)
                    connection.doOutput = true
                    connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                    connection.setFixedLengthStreamingMode(bytes.size)
                    connection.outputStream.use { it.write(bytes) }
                }
                form != null -> {
                    val bytes = form.entries.joinToString("&") { (k, v) ->
                        "${URLEncoder.encode(k, "UTF-8")}=${URLEncoder.encode(v, "UTF-8")}"
                    }.toByteArray(Charsets.UTF_8)
                    connection.doOutput = true
                    connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                    connection.setFixedLengthStreamingMode(bytes.size)
                    connection.outputStream.use { it.write(bytes) }
                }
            }

            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            Log.d(TAG, "  -> HTTP $status, ${text.length} caractères")

            val body = runCatching { JSONObject(text) }.getOrElse {
                val apercu = text.take(180).replace('\n', ' ')
                JSONObject().put("error", "Réponse non-JSON (HTTP $status) : $apercu")
            }
            Response(status, body)
        } catch (e: Exception) {
            Log.w(TAG, "  -> échec réseau : ${e.message}")
            Response(-1, JSONObject().put("error", e.message ?: "Erreur réseau"))
        } finally {
            connection.disconnect()
        }
    }

    private companion object {
        const val TAG = "ComptaApi"
    }
}
