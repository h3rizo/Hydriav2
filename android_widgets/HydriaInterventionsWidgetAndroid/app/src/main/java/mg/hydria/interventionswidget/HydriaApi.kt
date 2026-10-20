package mg.hydria.interventionswidget

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

object HydriaApi {
    private const val BASE_URL = "https://www.hydria.mg"
    private const val QUEUE_PATH = "/widget/api/interventions/"
    private const val SEEN_PATH = "/widget/api/interventions/vue/"

    data class LoginResult(val success: Boolean, val token: String? = null, val error: String? = null)
    data class Photo(val index: Int, val name: String, val type: String, val isVideo: Boolean, val url: String)
    data class Intervention(
        val id: String,
        val activity: String,
        val ouvrage: String,
        val employee: String,
        val base: String,
        val note: String,
        val status: String,
        val interventionDate: String,
        val createdAt: String,
        val photos: List<Photo>,
    )
    data class QueueResult(
        val success: Boolean,
        val unseenCount: Int = 0,
        val weekCount: Int = 0,
        val current: Intervention? = null,
        val latestEvent: Intervention? = null,
        val error: String? = null,
    )

    suspend fun login(username: String, password: String): LoginResult = withContext(Dispatchers.IO) {
        try {
            val connection = (URL("$BASE_URL/widget/api/login/").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = 8_000
                readTimeout = 12_000
                setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            }
            val body = "username=${URLEncoder.encode(username, "UTF-8")}" +
                "&password=${URLEncoder.encode(password, "UTF-8")}" +
                "&device_label=${URLEncoder.encode("Widget Android interventions", "UTF-8")}" 
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val json = readJson(connection)
            if (json.optBoolean("success")) LoginResult(true, json.optString("token"))
            else LoginResult(false, error = json.optString("error", "Connexion refusée"))
        } catch (error: Exception) {
            LoginResult(false, error = "Erreur réseau : ${error.message ?: "connexion impossible"}")
        }
    }

    suspend fun fetchQueue(token: String): QueueResult = withContext(Dispatchers.IO) {
        requestQueue(QUEUE_PATH, token, null)
    }

    suspend fun markSeen(token: String, planningId: String): QueueResult = withContext(Dispatchers.IO) {
        requestQueue(SEEN_PATH, token, JSONObject().put("planning_id", planningId).toString())
    }

    suspend fun fetchPhoto(token: String, path: String, maxWidth: Int = 1600): Bitmap? = withContext(Dispatchers.IO) {
        try {
            var currentUrl = absoluteUrl(path)
            var connection: HttpURLConnection? = null
            repeat(4) {
                connection?.disconnect()
                connection = (URL(currentUrl).openConnection() as HttpURLConnection).apply {
                    instanceFollowRedirects = false
                    connectTimeout = 8_000
                    readTimeout = 12_000
                    setRequestProperty("Authorization", "Token $token")
                }
                val code = connection!!.responseCode
                if (code in 300..399) {
                    currentUrl = absoluteUrl(connection!!.getHeaderField("Location") ?: return@withContext null)
                } else {
                    if (code !in 200..299) return@withContext null
                    val bytes = connection!!.inputStream.use { input ->
                        val output = ByteArrayOutputStream()
                        input.copyTo(output)
                        output.toByteArray()
                    }
                    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
                    var sample = 1
                    while (bounds.outWidth / sample > maxWidth * 2) sample *= 2
                    return@withContext BitmapFactory.decodeByteArray(
                        bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample }
                    )
                }
            }
            null
        } catch (_: Exception) { null }
    }

    private fun requestQueue(path: String, token: String, body: String?): QueueResult {
        return try {
            val connection = (URL("$BASE_URL$path").openConnection() as HttpURLConnection).apply {
                requestMethod = if (body == null) "GET" else "POST"
                connectTimeout = 8_000
                readTimeout = 12_000
                setRequestProperty("Authorization", "Token $token")
                if (body != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                }
            }
            if (body != null) connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val json = readJson(connection)
            if (code == 401) return QueueResult(false, error = "Session expirée. Reconnectez le widget.")
            if (!json.optBoolean("success")) return QueueResult(false, error = json.optString("error", "Erreur Hydria"))
            parseQueue(json)
        } catch (error: Exception) {
            QueueResult(false, error = "Erreur réseau : ${error.message ?: "connexion impossible"}")
        }
    }

    private fun parseQueue(json: JSONObject): QueueResult {
        val item = json.optJSONObject("current")
        val current = item?.let {
            val photoArray = it.optJSONArray("photos")
            val photos = mutableListOf<Photo>()
            if (photoArray != null) for (index in 0 until photoArray.length()) {
                val photo = photoArray.getJSONObject(index)
                photos += Photo(
                    photo.optInt("index"), photo.optString("name"), photo.optString("type"),
                    photo.optBoolean("is_video"), photo.optString("url")
                )
            }
            Intervention(
                id = it.optString("id"), activity = it.optString("activite", "Réparation"),
                ouvrage = it.optString("ouvrage", "Sans ouvrage"), employee = it.optString("employe", "Non affecté"),
                base = it.optString("base"), note = it.optString("remarque"), status = it.optString("statut"),
                interventionDate = it.optString("date_intervention"), createdAt = it.optString("date_saisie"), photos = photos,
            )
        }
        val latestItem = json.optJSONObject("latest_event")
        val latestEvent = latestItem?.let {
            Intervention(
                id = it.optString("id"), activity = it.optString("activite", "Réparation"),
                ouvrage = it.optString("ouvrage", "Sans ouvrage"), employee = "", base = "",
                note = "", status = "", interventionDate = "",
                createdAt = it.optString("date_saisie_iso"), photos = emptyList(),
            )
        }
        return QueueResult(
            success = true,
            unseenCount = json.optInt("unseen_count"),
            weekCount = if (json.has("week_count")) json.optInt("week_count") else json.optInt("unseen_count"),
            current = current,
            latestEvent = latestEvent,
        )
    }

    private fun readJson(connection: HttpURLConnection): JSONObject {
        val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
        return JSONObject(stream.bufferedReader().use { it.readText() })
    }

    private fun absoluteUrl(path: String): String = when {
        path.startsWith("http://") || path.startsWith("https://") -> path
        path.startsWith("/") -> "$BASE_URL$path"
        else -> "$BASE_URL/$path"
    }
}
