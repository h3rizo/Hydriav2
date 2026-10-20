package mg.hydria.planningwidget

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

object HydriaApi {
    private const val BASE_URL = "https://www.hydria.mg"
    private const val ACTIVITES_PATH = "/widget/api/planning/activites/"
    private const val FILTRES_PATH = "/widget/api/planning/filtres/"

    data class LoginResult(val success: Boolean, val token: String? = null, val error: String? = null)

    data class PlanningActivite(
        val id: String,
        val date: String,
        val heure: String,
        val activite: String,
        val ouvrage: String,
        val commune: String,
        val employe: String,
        val base: String,
        val statut: String,
        val termine: Boolean,
        val termineAuto: Boolean,
        val remarque: String,
    )

    data class ActivitesResult(
        val success: Boolean,
        val debut: String = "",
        val fin: String = "",
        val activites: List<PlanningActivite> = emptyList(),
        val error: String? = null,
    )

    data class Option(val id: String, val nom: String, val parentId: String? = null)

    data class FiltresResult(
        val success: Boolean,
        val employes: List<Option> = emptyList(),
        val bases: List<Option> = emptyList(),
        val regions: List<Option> = emptyList(),
        val districts: List<Option> = emptyList(),
        val communes: List<Option> = emptyList(),
        val typesActivite: List<Option> = emptyList(),
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
                "&device_label=${URLEncoder.encode("Widget Android planning", "UTF-8")}"
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val json = readJson(connection)
            if (json.optBoolean("success")) LoginResult(true, json.optString("token"))
            else LoginResult(false, error = json.optString("error", "Connexion refusée"))
        } catch (error: Exception) {
            LoginResult(false, error = "Erreur réseau : ${error.message ?: "connexion impossible"}")
        }
    }

    suspend fun fetchActivites(
        token: String,
        debut: String,
        fin: String,
        employeId: String = "all",
        baseId: String = "all",
        regionId: String = "all",
        districtId: String = "all",
        communeId: String = "all",
        typeActiviteIds: List<String> = emptyList(),
    ): ActivitesResult = withContext(Dispatchers.IO) {
        try {
            val params = StringBuilder()
            params.append("debut=").append(URLEncoder.encode(debut, "UTF-8"))
            params.append("&fin=").append(URLEncoder.encode(fin, "UTF-8"))
            if (employeId.isNotBlank() && employeId != "all") params.append("&employe_id=").append(URLEncoder.encode(employeId, "UTF-8"))
            if (baseId.isNotBlank() && baseId != "all") params.append("&base_id=").append(URLEncoder.encode(baseId, "UTF-8"))
            if (communeId.isNotBlank() && communeId != "all") {
                params.append("&commune_id=").append(URLEncoder.encode(communeId, "UTF-8"))
            } else if (districtId.isNotBlank() && districtId != "all") {
                params.append("&district_id=").append(URLEncoder.encode(districtId, "UTF-8"))
            } else if (regionId.isNotBlank() && regionId != "all") {
                params.append("&region_id=").append(URLEncoder.encode(regionId, "UTF-8"))
            }
            typeActiviteIds.forEach { params.append("&type_activite_id=").append(URLEncoder.encode(it, "UTF-8")) }

            val url = "$BASE_URL$ACTIVITES_PATH?$params"
            val connection = (URL(url).openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 8_000
                readTimeout = 12_000
                setRequestProperty("Authorization", "Token $token")
            }
            val code = connection.responseCode
            val json = readJson(connection)
            if (code == 401) return@withContext ActivitesResult(false, error = "Session expirée. Reconnectez le widget.")
            if (!json.optBoolean("success")) return@withContext ActivitesResult(false, error = json.optString("error", "Erreur Hydria"))
            parseActivites(json)
        } catch (error: Exception) {
            ActivitesResult(false, error = "Erreur réseau : ${error.message ?: "connexion impossible"}")
        }
    }

    suspend fun fetchFiltres(token: String): FiltresResult = withContext(Dispatchers.IO) {
        try {
            val connection = (URL("$BASE_URL$FILTRES_PATH").openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 8_000
                readTimeout = 12_000
                setRequestProperty("Authorization", "Token $token")
            }
            val code = connection.responseCode
            val json = readJson(connection)
            if (code == 401) return@withContext FiltresResult(false, error = "Session expirée. Reconnectez le widget.")
            if (!json.optBoolean("success")) return@withContext FiltresResult(false, error = json.optString("error", "Erreur Hydria"))
            FiltresResult(
                success = true,
                employes = parseOptions(json.optJSONArray("employes"), "nom"),
                bases = parseOptions(json.optJSONArray("bases"), "nom"),
                regions = parseOptions(json.optJSONArray("regions"), "nom"),
                districts = parseOptions(json.optJSONArray("districts"), "nom", "region_id"),
                communes = parseOptions(json.optJSONArray("communes"), "nom", "district_id"),
                typesActivite = parseOptions(json.optJSONArray("types_activite"), "nom"),
            )
        } catch (error: Exception) {
            FiltresResult(false, error = "Erreur réseau : ${error.message ?: "connexion impossible"}")
        }
    }

    private fun parseOptions(array: org.json.JSONArray?, nameField: String, parentField: String? = null): List<Option> {
        val list = mutableListOf<Option>()
        if (array != null) for (index in 0 until array.length()) {
            val item = array.getJSONObject(index)
            list += Option(
                id = item.optString("id"),
                nom = item.optString(nameField, ""),
                parentId = if (parentField != null) item.optString(parentField).takeIf { it.isNotBlank() } else null,
            )
        }
        return list
    }

    private fun parseActivites(json: JSONObject): ActivitesResult {
        val array = json.optJSONArray("activites")
        val list = mutableListOf<PlanningActivite>()
        if (array != null) for (index in 0 until array.length()) {
            val item = array.getJSONObject(index)
            list += PlanningActivite(
                id = item.optString("id"),
                date = item.optString("date"),
                heure = item.optString("heure"),
                activite = item.optString("activite", "Activité"),
                ouvrage = item.optString("ouvrage", ""),
                commune = item.optString("commune", ""),
                employe = item.optString("employe", ""),
                base = item.optString("base", ""),
                statut = item.optString("statut", ""),
                termine = item.optBoolean("termine", false),
                termineAuto = item.optBoolean("termine_auto", false),
                remarque = item.optString("remarque", ""),
            )
        }
        return ActivitesResult(
            success = true,
            debut = json.optString("debut"),
            fin = json.optString("fin"),
            activites = list,
        )
    }

    private fun readJson(connection: HttpURLConnection): JSONObject {
        val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
        return JSONObject(stream.bufferedReader().use { it.readText() })
    }
}
