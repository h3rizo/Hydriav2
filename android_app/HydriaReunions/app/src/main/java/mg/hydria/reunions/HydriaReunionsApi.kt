package mg.hydria.reunions

import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/**
 * Client HTTP de l'app HydriaReunions. Meme approche que HydriaApi (app
 * terrain) et ComptaApi (HydriaCompta) : HttpURLConnection + org.json,
 * en-tete `Authorization: Token <cle>`, un objet singleton par app.
 *
 * Deux familles d'endpoints, meme backend (www.hydria.mg) :
 *  - /api/mobile/v1/reunions/...   (representantes, avis, reunions, notes)
 *  - /api/mobile/v1/messaging/...  (conversations, messages, jetons push)
 *
 * Login : /mobile/api/login/ (jeton scope='mobile', partage avec les autres
 * apps Hydria — meme WidgetAuthToken cote serveur).
 */
object HydriaReunionsApi {
    private const val BASE_URL = "https://www.hydria.mg"
    /** Meme serveur, schema ws(s) — Nginx redirige /ws/ vers Daphne en production. */
    const val WS_BASE_URL = "wss://www.hydria.mg"
    private const val ROOT_REUNIONS = "$BASE_URL/api/mobile/v1/reunions"
    private const val ROOT_MESSAGING = "$BASE_URL/api/mobile/v1/messaging"

    data class Result(val status: Int, val body: JSONObject) {
        val successful: Boolean get() = status in 200..299
        val error: String get() = body.optString("error", body.optString("message", "Erreur HTTP $status"))
    }

    // ---- Auth ----

    fun login(username: String, password: String, deviceLabel: String): Result = request(
        path = "$BASE_URL/mobile/api/login/",
        method = "POST",
        form = mapOf("username" to username, "password" to password, "device_label" to deviceLabel),
    )

    // ---- Reunions / representantes / avis / notes ----

    fun bootstrap(token: String): Result = request(path = "$ROOT_REUNIONS/bootstrap", token = token)

    fun changes(token: String, since: String): Result =
        request(path = "$ROOT_REUNIONS/changes?since=${encoded(since)}", token = token)

    fun mutations(token: String, mutations: JSONArray): Result = request(
        path = "$ROOT_REUNIONS/mutations",
        method = "POST",
        token = token,
        jsonBody = JSONObject().put("mutations", mutations),
    )

    fun notesForEntity(token: String, entityType: String, entityId: String): Result = request(
        path = "$ROOT_REUNIONS/notes/entity/${encoded(entityType)}/${encoded(entityId)}",
        token = token,
    )

    fun notesQuickCreate(
        token: String, entityType: String, entityId: String, title: String, content: String, tags: String = "",
    ): Result = request(
        path = "$ROOT_REUNIONS/notes/entity/create",
        method = "POST",
        token = token,
        form = mapOf("entity_type" to entityType, "entity_id" to entityId, "title" to title, "content" to content, "tags" to tags),
    )

    fun notesAddTask(token: String, noteId: String, title: String, description: String = "", dueDate: String = ""): Result = request(
        path = "$ROOT_REUNIONS/notes/$noteId/tasks/create",
        method = "POST",
        token = token,
        form = mapOf("title" to title, "description" to description, "due_date" to dueDate),
    )

    /** Upload multipart (photo/rapport). Utilise OkHttp (deja present pour le WebSocket) —
     * HttpURLConnection ne facilite pas l'encodage multipart. */
    fun uploadPieceJointe(token: String, reunionId: String, file: File, typePiece: String, legende: String): Result {
        val mediaType = when (file.extension.lowercase()) {
            "png" -> "image/png"
            "jpg", "jpeg" -> "image/jpeg"
            "pdf" -> "application/pdf"
            else -> "application/octet-stream"
        }.toMediaTypeOrNull()

        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("type_piece", typePiece)
            .addFormDataPart("legende", legende)
            .addFormDataPart("fichier", file.name, file.asRequestBody(mediaType))
            .build()

        val httpRequest = Request.Builder()
            .url("$ROOT_REUNIONS/reunions/$reunionId/pieces-jointes")
            .addHeader("Authorization", "Token $token")
            .addHeader("Accept", "application/json")
            .post(body)
            .build()

        return okHttpClient.newCall(httpRequest).execute().use { response ->
            val text = response.body?.string().orEmpty()
            val json = try {
                if (text.isBlank()) JSONObject().put("success", response.isSuccessful) else JSONObject(text)
            } catch (_: Exception) {
                JSONObject().put("success", false).put("error", "Reponse serveur invalide (HTTP ${response.code})")
            }
            Result(response.code, json)
        }
    }

    // ---- Messaging (conversations temps reel) ----

    fun messagingBootstrap(token: String): Result = request(path = "$ROOT_MESSAGING/bootstrap", token = token)

    fun messagingChanges(token: String, since: String): Result =
        request(path = "$ROOT_MESSAGING/changes?since=${encoded(since)}", token = token)

    fun conversationCreate(token: String, type: String, participantIds: List<String>, nomGroupe: String? = null): Result {
        val payload = JSONObject().put("type", type).put("participant_ids", JSONArray(participantIds))
        nomGroupe?.let { payload.put("nom_groupe", it) }
        return request(path = "$ROOT_MESSAGING/conversations/create", method = "POST", token = token, jsonBody = payload)
    }

    /** Repli REST si le WebSocket n'est pas disponible — l'envoi normal passe par
     * ChatWebSocketClient (voir conversations/ChatWebSocketClient.kt). */
    fun messageSend(token: String, conversationId: String, contenu: String, type: String = "text"): Result = request(
        path = "$ROOT_MESSAGING/messages/send",
        method = "POST",
        token = token,
        jsonBody = JSONObject().put("conversation_id", conversationId).put("contenu", contenu).put("type", type),
    )

    fun messageRead(token: String, conversationId: String): Result =
        request(path = "$ROOT_MESSAGING/conversations/$conversationId/read", method = "POST", token = token, form = emptyMap())

    fun registerDevice(token: String, fcmToken: String, deviceLabel: String): Result = request(
        path = "$ROOT_MESSAGING/devices/register",
        method = "POST",
        token = token,
        form = mapOf("token" to fcmToken, "plateforme" to "android", "device_label" to deviceLabel),
    )

    fun unregisterDevice(token: String, fcmToken: String): Result = request(
        path = "$ROOT_MESSAGING/devices/unregister",
        method = "POST",
        token = token,
        form = mapOf("token" to fcmToken),
    )

    // ---- Interne ----

    private val okHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .build()
    }

    private fun encoded(value: String): String = URLEncoder.encode(value, "UTF-8")

    private fun request(
        path: String,
        method: String = "GET",
        token: String? = null,
        form: Map<String, String>? = null,
        jsonBody: JSONObject? = null,
    ): Result {
        val connection = URL(path).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = method
            connection.connectTimeout = 15_000
            connection.readTimeout = 60_000
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("User-Agent", "HydriaReunionsAndroid/1.0.0")
            if (!token.isNullOrBlank()) connection.setRequestProperty("Authorization", "Token $token")

            if (jsonBody != null) {
                val encodedBody = jsonBody.toString().toByteArray(Charsets.UTF_8)
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                connection.setFixedLengthStreamingMode(encodedBody.size)
                connection.outputStream.use { it.write(encodedBody) }
            } else if (form != null) {
                val encodedForm = form.entries.joinToString("&") {
                    "${URLEncoder.encode(it.key, "UTF-8")}=${URLEncoder.encode(it.value, "UTF-8")}"
                }.toByteArray(Charsets.UTF_8)
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                connection.setFixedLengthStreamingMode(encodedForm.size)
                connection.outputStream.use { it.write(encodedForm) }
            }

            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            val body = try {
                if (text.isBlank()) JSONObject().put("success", status in 200..299) else JSONObject(text)
            } catch (_: Exception) {
                val message = if (text.trimStart().startsWith("<!doctype html", ignoreCase = true) ||
                    text.trimStart().startsWith("<html", ignoreCase = true)
                ) {
                    "Service indisponible (HTTP $status). Reessayez plus tard."
                } else {
                    text.ifBlank { "Reponse serveur invalide (HTTP $status)" }
                }
                JSONObject().put("success", false).put("error", message)
            }
            Result(status, body)
        } finally {
            connection.disconnect()
        }
    }
}
