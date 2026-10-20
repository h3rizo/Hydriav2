package mg.hydria.app

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

object HydriaApi {
    private const val BASE_URL = "https://www.hydria.mg"

    data class Result(val status: Int, val body: JSONObject) {
        val successful: Boolean get() = status in 200..299 && body.optBoolean("success", true)
        val error: String get() = body.optString("error", "Erreur HTTP $status")
    }

    fun login(username: String, password: String, deviceLabel: String): Result =
        request(
            path = "/mobile/api/login/",
            method = "POST",
            form = mapOf("username" to username, "password" to password, "device_label" to deviceLabel)
        )

    fun prepareTour(token: String, snapshotVersion: String? = null): Result = request(
        path = "/plannings/api/preparer-tournee/?horizon_jours=14" +
            (snapshotVersion?.takeIf { it.isNotBlank() }?.let { "&snapshot_version=${URLEncoder.encode(it, "UTF-8")}" } ?: ""),
        token = token
    )

    /** Historique des débits de source d'un ouvrage + niveau de criticité (même logique que la page web). */
    fun ouvrageDebits(token: String, ouvrageId: String): Result = request(
        path = "/plannings/api/mobile/ouvrage/${URLEncoder.encode(ouvrageId, "UTF-8")}/debits/",
        token = token
    )

    /** Dernière version publiée de l'app (fichier statique, sans authentification) ; null si injoignable. */
    fun latestAppVersion(): JSONObject? = runCatching {
        val connection = URL("$BASE_URL/static/downloads/android/version.json?t=${System.currentTimeMillis()}")
            .openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 8_000
            connection.readTimeout = 8_000
            if (connection.responseCode !in 200..299) null
            else JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
        } finally {
            connection.disconnect()
        }
    }.getOrNull()

    /** Classement des contributeurs Terrain : periode = absolu | mois | semaine | jour. */
    fun terrainRanking(token: String, period: String): Result = request(
        path = "/plannings/api/mobile/terrain/classement/?periode=${URLEncoder.encode(period, "UTF-8")}",
        token = token
    )

    fun pointInvoices(token: String, pointId: String): Result = request(
        path = "/plannings/api/mobile/point-eau/$pointId/factures/",
        token = token
    )

    fun saveReading(token: String, payload: JSONObject): Result = request(
        path = "/facturation/api/save-releve-terrain/",
        method = "POST",
        token = token,
        form = mutableMapOf(
            "point_eau_id" to payload.getString("point_eau_id"),
            "date_releve" to payload.getString("date_releve"),
            "nouvel_index" to payload.getDouble("nouvel_index").toString(),
            "volume_non_facture" to payload.optDouble("volume_non_facture", 0.0).toString(),
            "remarque" to payload.optString("remarque"),
            "cartes_sociales" to payload.optString("cartes_sociales", "[]")
        ).apply {
            listOf(
                "local_uuid", "point_latitude", "point_longitude", "point_photo_data", "point_photo_name", "point_photo_type",
                "terrain_latitude", "terrain_longitude", "terrain_gps_accuracy_m", "terrain_distance_point_m", "terrain_captured_at",
                "montant", "ticket_local"
            ).forEach { key ->
                if (payload.has(key) && !payload.isNull(key)) this[key] = payload.optString(key)
            }
        }
    )

    fun finishRepair(token: String, planningId: String): Result = request(
        path = "/plannings/reparations/api/$planningId/marquer-terminee/",
        method = "POST",
        token = token,
        form = emptyMap()
    )

    fun saveRepair(token: String, payload: JSONObject): Result = savePlanningLike(
        token, payload, "/plannings/api/mobile/reparation/enregistrer/"
    )

    fun saveRepairPhoto(token: String, payload: JSONObject): Result = request(
        path = "/plannings/api/mobile/reparation/${payload.getString("planning_id")}/photo/",
        method = "POST",
        token = token,
        jsonBody = JSONObject(payload.toString()).apply {
            remove("planning_id")
            keys().asSequence().filter { it.startsWith("_sync_") }.toList().forEach { remove(it) }
        },
    )

    fun savePlanning(token: String, payload: JSONObject): Result = savePlanningLike(
        token, payload, "/plannings/api/mobile/planning/enregistrer/"
    )

    fun saveTerrainItem(token: String, payload: JSONObject): Result {
        val form = mutableMapOf<String, String>()
        val keys = payload.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            if (!key.startsWith("_sync_") && !payload.isNull(key)) form[key] = payload.optString(key)
        }
        return request(
            path = "/plannings/api/mobile/terrain/sync-item/",
            method = "POST",
            token = token,
            form = form,
        )
    }

    fun pointageToday(token: String): Result =
        request(path = "/api/mobile/v1/pointage/aujourdhui", token = token)

    /** 200 = validé ; 422 = refus métier définitif (corps : code + message). */
    fun pointagePointer(token: String, payload: JSONObject): Result = request(
        path = "/api/mobile/v1/pointage/pointer",
        method = "POST",
        token = token,
        form = jsonForm(payload),
    )

    fun pointageDeclarer(token: String, payload: JSONObject): Result = request(
        path = "/api/mobile/v1/pointage/declarer",
        method = "POST",
        token = token,
        form = jsonForm(payload),
    )

    fun pointageEquipe(token: String, date: String? = null): Result = request(
        path = "/api/mobile/v1/pointage/equipe" + (date?.let { "?date=${URLEncoder.encode(it, "UTF-8")}" } ?: ""),
        token = token,
    )

    fun saveNavigationPosition(token: String, payload: JSONObject): Result = request(
        path = "/navigation-terrain/api/mobile/positions/upsert/",
        method = "POST",
        token = token,
        form = jsonForm(payload),
    )

    fun saveNavigationLandmark(token: String, payload: JSONObject): Result = request(
        path = if (payload.optString("operation_type") == "landmark_archive") {
            "/navigation-terrain/api/mobile/reperes/${payload.optString("id")}/archive/"
        } else {
            "/navigation-terrain/api/mobile/reperes/upsert/"
        },
        method = "POST",
        token = token,
        form = jsonForm(payload),
    )

    fun saveNavigationPhoto(token: String, payload: JSONObject): Result = request(
        path = "/navigation-terrain/api/mobile/reperes/${payload.optString("entity_id")}/photos/",
        method = "POST",
        token = token,
        form = jsonForm(payload),
    )

    fun navigationConfig(token: String): Result = request(
        path = "/navigation-terrain/api/mobile/config/",
        token = token,
    )

    fun navigationRoute(
        token: String, fromLat: Double, fromLon: Double, toLat: Double, toLon: Double, profile: String,
    ): Result = request(
        path = "/navigation-terrain/api/mobile/itineraire/?from_lat=$fromLat&from_lon=$fromLon" +
            "&to_lat=$toLat&to_lon=$toLon&profil=${encoded(profile)}",
        token = token,
    )

    fun salaryCalculationConfig(token: String, checksum: String = ""): Result = request(
        path = "/mobile/api/salary-calculation-config/" +
            checksum.takeIf { it.isNotBlank() }?.let { "?checksum=${encoded(it)}" }.orEmpty(),
        token = token,
    )

    fun search(token: String, query: String, types: Set<String>, page: Int = 1): Result = request(
        path = "/recherche/api/mobile/search/?q=${encoded(query)}&types=${encoded(types.joinToString(","))}&page=$page&page_size=20",
        token = token,
    )

    fun people(token: String, query: String, type: String, status: String, page: Int = 1): Result = request(
        path = "/recherche/api/mobile/personnes/?search=${encoded(query)}&type=${encoded(type)}&statut=${encoded(status)}&page=$page",
        token = token,
    )

    fun works(
        token: String,
        query: String,
        page: Int = 1,
        region: String = "",
        district: String = "",
        commune: String = "",
        employee: String = "",
    ): Result = request(
        path = "/recherche/api/mobile/ouvrages/?q=${encoded(query)}&page=$page&page_size=20" +
            "&region=${encoded(region)}&district=${encoded(district)}&commune=${encoded(commune)}&employee=${encoded(employee)}",
        token = token,
    )

    fun workFilters(token: String): Result = request(
        path = "/recherche/api/mobile/ouvrages/filtres/",
        token = token,
    )

    fun interventions(
        token: String,
        page: Int = 1,
        includeOtherBases: Boolean = false,
        status: String = "",
        sort: String = "created",
    ): Result = request(
        path = "/recherche/api/mobile/interventions/?page=$page&page_size=20&all_bases=${if (includeOtherBases) 1 else 0}&status=${encoded(status)}&sort=${encoded(sort)}",
        token = token,
    )

    fun postponeIntervention(token: String, planningId: String, date: String): Result = request(
        path = "/recherche/api/mobile/interventions/${encoded(planningId)}/reporter/",
        method = "POST",
        token = token,
        form = mapOf("date" to date),
    )

    fun deleteIntervention(token: String, planningId: String): Result = request(
        path = "/recherche/api/mobile/interventions/${encoded(planningId)}/supprimer/",
        method = "POST",
        token = token,
        form = emptyMap(),
    )

    fun interventionOptions(token: String, workId: String): Result = request(
        path = "/recherche/ouvrages/${encoded(workId)}/interventions/options/",
        token = token,
    )

    fun updateIntervention(token: String, workId: String, planningId: String, payload: JSONObject): Result = request(
        path = "/recherche/ouvrages/${encoded(workId)}/interventions/${encoded(planningId)}/modifier/",
        method = "POST",
        token = token,
        jsonBody = payload,
    )

    fun searchDetail(token: String, type: String, id: String): Result = request(
        path = "/recherche/api/mobile/details/${encoded(type)}/${encoded(id)}/",
        token = token,
    )

    fun personDetail(token: String, type: String, id: String): Result = request(
        path = "/recherche/api/mobile/personnes/${encoded(type)}/${encoded(id)}/",
        token = token,
    )

    private fun encoded(value: String): String = URLEncoder.encode(value, "UTF-8")

    fun volumeBootstrap(token: String, ouvrageId: String = "", month: String = ""): Result = request(
        path = "/facturation/api/mobile/volume/bootstrap/?ouvrage_id=${encoded(ouvrageId)}&mois=${encoded(month)}",
        token = token,
    )

    fun volumeOperation(token: String, payload: JSONObject): Result = request(
        path = "/facturation/api/mobile/volume/sync/", method = "POST", token = token,
        jsonBody = JSONObject(payload.toString()).apply {
            keys().asSequence().filter { it.startsWith("_sync_") }.toList().forEach { remove(it) }
        },
    )

    fun navigationEntities(token: String, cursor: String?, bbox: String?, limit: Int = 500): Result {
        val query = buildList {
            add("limit=$limit")
            cursor?.takeIf { it.isNotBlank() }?.let { add("cursor=${URLEncoder.encode(it, "UTF-8")}") }
            bbox?.takeIf { it.isNotBlank() }?.let { add("bbox=${URLEncoder.encode(it, "UTF-8")}") }
        }.joinToString("&")
        return request(path = "/navigation-terrain/api/mobile/entities/?$query", token = token)
    }

    private fun jsonForm(payload: JSONObject): Map<String, String> = buildMap {
        val keys = payload.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            if (!key.startsWith("_sync_") && !payload.isNull(key)) put(key, payload.optString(key))
        }
    }

    private fun savePlanningLike(token: String, payload: JSONObject, path: String): Result {
        val form = mutableMapOf<String, String>()
        listOf("id", "employe_id", "fiche_poste_id", "ouvrage_id", "date", "remarque", "statut", "priorite",
            "equipement_id", "point_eau_id", "composants_ids").forEach { key ->
            if (payload.has(key) && !payload.isNull(key)) form[key] = payload.optString(key)
        }
        return request(path = path, method = "POST", token = token, form = form)
    }

    private fun request(
        path: String,
        method: String = "GET",
        token: String? = null,
        form: Map<String, String>? = null,
        jsonBody: JSONObject? = null,
    ): Result {
        val connection = URL(BASE_URL + path).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = method
            connection.connectTimeout = 15_000
            // Le premier préchargement peut contenir plusieurs centaines
            // d'ouvrages/points d'eau pour un compte de coordination.
            connection.readTimeout = 120_000
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("User-Agent", "HydriaTerrainAndroid/2.1.4")
            if (!token.isNullOrBlank()) connection.setRequestProperty("Authorization", "Token $token")
            if (jsonBody != null) {
                val encoded = jsonBody.toString().toByteArray(Charsets.UTF_8)
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                connection.setFixedLengthStreamingMode(encoded.size)
                connection.outputStream.use { it.write(encoded) }
            } else if (form != null) {
                val encoded = form.entries.joinToString("&") {
                    "${URLEncoder.encode(it.key, "UTF-8")}=${URLEncoder.encode(it.value, "UTF-8")}" 
                }.toByteArray(Charsets.UTF_8)
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                connection.setFixedLengthStreamingMode(encoded.size)
                connection.outputStream.use { it.write(encoded) }
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
                    "Service de synchronisation indisponible (HTTP $status). Mettez à jour l'application ou réessayez plus tard."
                } else {
                    text.ifBlank { "Réponse serveur invalide (HTTP $status)" }
                }
                JSONObject().put("success", false).put("error", message)
            }
            Result(status, body)
        } finally {
            connection.disconnect()
        }
    }
}
