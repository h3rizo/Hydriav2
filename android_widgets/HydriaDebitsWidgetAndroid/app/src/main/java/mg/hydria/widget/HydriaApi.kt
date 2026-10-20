package mg.hydria.widget

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Appels réseau vers les APIs "widget/api" (déjà construites côté Django
 * pour le widget desktop Electron) — réutilisées telles quelles ici, même
 * définitions de stats, même mécanisme d'auth par token.
 */
object HydriaApi {
    private const val BASE_URL = "https://www.hydria.mg"
    private const val OPERATIONAL_ENDPOINT = "/widget/api/debits-source/"

    data class LoginResult(val success: Boolean, val token: String?, val error: String?)
    data class StatsResult(val success: Boolean, val stats: Map<String, Int>?, val error: String?)

    data class FilterOption(val id: String, val name: String) {
        override fun toString(): String = name
    }
    data class DistrictOption(val id: String, val name: String, val regionId: String)
    data class CommuneOption(val id: String, val name: String, val districtId: String)
    data class FiltersResult(
        val success: Boolean,
        val organisations: List<FilterOption>,
        val defaultOrganisationId: String?,
        val employees: List<FilterOption>,
        val regions: List<FilterOption>,
        val districts: List<DistrictOption>,
        val communes: List<CommuneOption>,
        val error: String?,
    )

    data class Commune(val communeId: String, val commune: String, val count: Int)
    data class District(val district: String, val districtId: String?, val communes: List<Commune>, val total: Int)
    data class GroupesResult(val success: Boolean, val total: Int, val districts: List<District>, val error: String?)

    data class DetailRow(val id: String?, val label: String, val sub: String?)
    data class DetailsResult(val success: Boolean, val total: Int, val shown: Int, val rows: List<DetailRow>, val error: String?)
    data class InfoRow(val title: String, val subtitle: String)
    data class DebitHistoryPoint(val date: String, val debit: Double)
    data class OuvrageDetail(
        val id: String,
        val name: String,
        val type: String,
        val year: String,
        val previousYear: String,
        val builder: String,
        val seasonal: Boolean,
        val observation: String,
        val stats: Map<String, Int>,
        val locations: List<InfoRow>,
        val management: List<InfoRow>,
        val tariffs: List<InfoRow>,
        val waterPoints: List<InfoRow>,
        val equipment: List<InfoRow>,
        val repairs: List<InfoRow>,
        val overduePayments: List<InfoRow>,
        val upcomingPayments: List<InfoRow>,
        val latestDebit: Double?,
        val debitThreshold: Double?,
        val debitGap: Double?,
        val debitComparison: String,
        val debitHistory: List<DebitHistoryPoint>,
        val fullUrl: String,
    )
    data class OuvrageDetailResult(val success: Boolean, val detail: OuvrageDetail?, val error: String?)

    /**
     * GET authentifié générique vers l'API "widget/api", factorisant la
     * logique réseau commune à fetchStats/fetchGroupes/fetchDetails
     * (mêmes en-têtes, même gestion 401, même lecture de flux).
     */
    private suspend fun authenticatedGet(path: String, token: String): Pair<Int, JSONObject>? = withContext(Dispatchers.IO) {
        try {
            val url = URL("$BASE_URL$path")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "GET"
            conn.setRequestProperty("Authorization", "Token $token")

            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream.bufferedReader().use { it.readText() }
            Pair(code, JSONObject(text))
        } catch (e: Exception) {
            null
        }
    }

    suspend fun login(username: String, password: String): LoginResult = withContext(Dispatchers.IO) {
        try {
            val url = URL("$BASE_URL/widget/api/login/")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")

            val body = "username=${URLEncoder.encode(username, "UTF-8")}" +
                "&password=${URLEncoder.encode(password, "UTF-8")}" +
                "&device_label=${URLEncoder.encode("Widget Android", "UTF-8")}"
            conn.outputStream.use { it.write(body.toByteArray()) }

            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream.bufferedReader().use { it.readText() }
            val json = JSONObject(text)

            if (json.optBoolean("success", false)) {
                LoginResult(true, json.getString("token"), null)
            } else {
                LoginResult(false, null, json.optString("error", "Erreur inconnue"))
            }
        } catch (e: Exception) {
            LoginResult(false, null, "Erreur réseau : ${e.message}")
        }
    }

    suspend fun fetchFilters(token: String, organisationId: String? = null): FiltersResult {
        val suffix = if (!organisationId.isNullOrBlank() && organisationId != "all") {
            "?organisation=${URLEncoder.encode(organisationId, "UTF-8")}"
        } else ""
        val response = authenticatedGet("/widget/api/filtres/$suffix", token)
            ?: return FiltersResult(false, emptyList(), null, emptyList(), emptyList(), emptyList(), emptyList(), "Erreur réseau")
        val (code, json) = response
        if (code == 401) return FiltersResult(false, emptyList(), null, emptyList(), emptyList(), emptyList(), emptyList(), "Session expirée")
        if (!json.optBoolean("success", false)) {
            return FiltersResult(false, emptyList(), null, emptyList(), emptyList(), emptyList(), emptyList(), json.optString("error", "Erreur inconnue"))
        }
        fun options(key: String): List<FilterOption> {
            val array = json.optJSONArray(key) ?: return emptyList()
            return (0 until array.length()).map { index ->
                array.getJSONObject(index).let { FilterOption(it.getString("id"), it.getString("nom")) }
            }
        }
        val districtsJson = json.getJSONArray("districts")
        val communesJson = json.getJSONArray("communes")
        return FiltersResult(
            success = true,
            organisations = options("organisations"),
            defaultOrganisationId = json.optString("default_organisation_id").takeIf { it.isNotBlank() && it != "null" },
            employees = options("employes"),
            regions = options("regions"),
            districts = (0 until districtsJson.length()).map { index ->
                districtsJson.getJSONObject(index).let {
                    DistrictOption(it.getString("id"), it.getString("nom"), it.getString("region_id"))
                }
            },
            communes = (0 until communesJson.length()).map { index ->
                communesJson.getJSONObject(index).let {
                    CommuneOption(it.getString("id"), it.getString("nom"), it.getString("district_id"))
                }
            },
            error = null,
        )
    }

    suspend fun fetchStats(token: String, filters: TokenStore.Filters = TokenStore.Filters()): StatsResult = withContext(Dispatchers.IO) {
        try {
            val url = URL("$BASE_URL${filteredPath(OPERATIONAL_ENDPOINT, filters)}")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "GET"
            conn.setRequestProperty("Authorization", "Token $token")

            val code = conn.responseCode
            if (code == 401) {
                return@withContext StatsResult(false, null, "Session expirée")
            }

            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream.bufferedReader().use { it.readText() }
            val json = JSONObject(text)

            if (json.optBoolean("success", false)) {
                val statsJson = json.getJSONObject("stats")
                val stats = mutableMapOf<String, Int>()
                // org.json.JSONObject.keys() renvoie un java.util.Iterator
                // brut (pas un Iterable Kotlin) — pas de .forEach dessus,
                // il faut une boucle while + hasNext()/next() classique.
                val keysIterator = statsJson.keys()
                while (keysIterator.hasNext()) {
                    val key = keysIterator.next()
                    stats[key] = statsJson.getInt(key)
                }
                StatsResult(true, stats, null)
            } else {
                StatsResult(false, null, json.optString("error", "Erreur inconnue"))
            }
        } catch (e: Exception) {
            StatsResult(false, null, "Erreur réseau : ${e.message}")
        }
    }

    /**
     * Regroupement District → Commune pour une stat géolocalisable
     * (ouvrages, points_eau, factures volumétriques/forfaitaires non pointées) — même endpoint que
     * le widget desktop Electron, même structure de réponse.
     */
    suspend fun fetchGroupes(
        statType: String,
        token: String,
        filters: TokenStore.Filters = TokenStore.Filters(),
    ): GroupesResult {
        val response = authenticatedGet(filteredPath("/widget/api/groupes/$statType/", filters), token)
            ?: return GroupesResult(false, 0, emptyList(), "Erreur réseau")

        val (code, json) = response
        if (code == 401) return GroupesResult(false, 0, emptyList(), "Session expirée")
        if (!json.optBoolean("success", false)) {
            return GroupesResult(false, 0, emptyList(), json.optString("error", "Erreur inconnue"))
        }

        val districtsJson = json.getJSONArray("districts")
        val districts = mutableListOf<District>()
        for (i in 0 until districtsJson.length()) {
            val d = districtsJson.getJSONObject(i)
            val communesJson = d.getJSONArray("communes")
            val communes = mutableListOf<Commune>()
            for (j in 0 until communesJson.length()) {
                val c = communesJson.getJSONObject(j)
                communes.add(Commune(c.getString("commune_id"), c.getString("commune"), c.getInt("count")))
            }
            districts.add(District(
                district = d.getString("district"),
                districtId = if (d.isNull("district_id")) null else d.getString("district_id"),
                communes = communes,
                total = d.getInt("total"),
            ))
        }
        return GroupesResult(true, json.getInt("total"), districts, null)
    }

    /**
     * Liste concise (max ~25 lignes) pour une stat, avec filtre optionnel
     * commune_id pour le drill-down depuis fetchGroupes. Même endpoint
     * que le widget desktop pour les stats non groupables (réparations,
     * forfait du jour).
     */
    suspend fun fetchDetails(
        statType: String,
        token: String,
        filters: TokenStore.Filters = TokenStore.Filters(),
        communeId: String? = null,
    ): DetailsResult {
        val effectiveFilters = if (communeId != null) filters.copy(communeId = communeId) else filters
        val filtered = filteredPath(OPERATIONAL_ENDPOINT, effectiveFilters)
        val separator = if (filtered.contains("?")) "&" else "?"
        val path = "$filtered${separator}status=${URLEncoder.encode(statType, "UTF-8")}"
        val response = authenticatedGet(path, token)
            ?: return DetailsResult(false, 0, 0, emptyList(), "Erreur réseau")

        val (code, json) = response
        if (code == 401) return DetailsResult(false, 0, 0, emptyList(), "Session expirée")
        if (!json.optBoolean("success", false)) {
            return DetailsResult(false, 0, 0, emptyList(), json.optString("error", "Erreur inconnue"))
        }

        val rowsJson = json.getJSONArray("rows")
        val rows = mutableListOf<DetailRow>()
        for (i in 0 until rowsJson.length()) {
            val r = rowsJson.getJSONObject(i)
            val sub = if (r.has("sub") && !r.isNull("sub")) r.getString("sub") else null
            rows.add(DetailRow(r.optString("id").takeIf { it.isNotBlank() }, r.optString("label", "—"), sub))
        }
        return DetailsResult(true, json.getInt("total"), json.getInt("shown"), rows, null)
    }

    suspend fun fetchOuvrageDetail(
        ouvrageId: String,
        token: String,
        filters: TokenStore.Filters = TokenStore.Filters(),
    ): OuvrageDetailResult {
        val response = authenticatedGet(filteredPath("/widget/api/ouvrages/$ouvrageId/", filters), token)
            ?: return OuvrageDetailResult(false, null, "Erreur réseau")
        val (code, json) = response
        if (code == 401) return OuvrageDetailResult(false, null, "Session expirée")
        if (!json.optBoolean("success", false)) {
            return OuvrageDetailResult(false, null, json.optString("error", "Erreur inconnue"))
        }
        val ouvrage = json.getJSONObject("ouvrage")
        val statsJson = ouvrage.getJSONObject("stats")
        val stats = mapOf(
            "Points d'eau" to statsJson.optInt("points_eau"),
            "Équipements" to statsJson.optInt("equipements"),
            "Compteurs" to statsJson.optInt("compteurs"),
            "Plannings" to statsJson.optInt("plannings"),
        )

        fun rows(arrayName: String, transform: (JSONObject) -> InfoRow): List<InfoRow> {
            val array = ouvrage.optJSONArray(arrayName) ?: return emptyList()
            return (0 until array.length()).map { transform(array.getJSONObject(it)) }
        }
        val locations = rows("localisations") { item ->
            val villages = item.optJSONArray("villages")
            val villageText = if (villages == null) "" else (0 until villages.length())
                .joinToString(", ") { villages.optString(it) }
            InfoRow(
                item.optString("commune", "Commune"),
                listOf(item.optString("district"), item.optString("region"), villageText)
                    .filter { it.isNotBlank() }.joinToString(" · "),
            )
        }
        val management = rows("modalites") { item ->
            InfoRow(
                item.optString("type_gestion", "Gestion"),
                listOf(item.optString("gestionnaire"), item.optString("paiement"), item.optString("statut"))
                    .filter { it.isNotBlank() }.joinToString(" · "),
            )
        }
        val tariffs = rows("tarifs") { item ->
            val tranches = item.optJSONArray("tranches")
            val trancheText = if (tranches == null) "" else (0 until tranches.length()).joinToString(" · ") { index ->
                val tranche = tranches.getJSONObject(index)
                "≤ ${tranche.optInt("seuil")} m³ : ${tranche.optInt("tarif")} Ar/m³"
            }
            InfoRow(
                item.optString("type_point_eau", "Tarif"),
                listOf("Abonnement ${item.optInt("prix_abonnement")} Ar", trancheText)
                    .filter { it.isNotBlank() }.joinToString(" · "),
            )
        }
        val waterPoints = rows("points_eau") { item ->
            InfoRow(
                item.optString("nom").ifBlank { item.optString("code", "Point d'eau") },
                listOf(item.optString("code"), item.optString("type"), item.optString("village"))
                    .filter { it.isNotBlank() }.joinToString(" · "),
            )
        }
        val equipment = rows("equipements") { item ->
            val volume = item.optString("volume_m3").takeIf { it.isNotBlank() && it != "null" }?.let { "$it m³" } ?: ""
            InfoRow(
                item.optString("nom", "Équipement"),
                listOf(item.optString("code"), item.optString("type"), item.optString("statut"), volume)
                    .filter { it.isNotBlank() }.joinToString(" · "),
            )
        }
        val repairs = rows("reparations_non_terminees") { item ->
            InfoRow(
                item.optString("titre", "Réparation"),
                listOf(item.optString("statut"), item.optString("date"), item.optString("priorite"), item.optString("responsable"))
                    .filter { it.isNotBlank() }.joinToString(" · "),
            )
        }
        fun paymentRows(name: String) = rows(name) { item ->
            InfoRow(
                item.optString("point_eau", "Point d’eau"),
                listOf(item.optString("type"), item.optString("date"), "${item.optString("montant", "0")} Ar")
                    .filter { it.isNotBlank() }.joinToString(" · "),
            )
        }
        val debitSource = ouvrage.optJSONObject("debit_source")
        fun nullableDouble(key: String): Double? = if (debitSource == null || debitSource.isNull(key)) null else debitSource.optDouble(key)
        val debitHistoryJson = debitSource?.optJSONArray("historique")
        val debitHistory = if (debitHistoryJson == null) emptyList() else (0 until debitHistoryJson.length()).map { index ->
            debitHistoryJson.getJSONObject(index).let { DebitHistoryPoint(it.optString("date"), it.optDouble("debit")) }
        }
        return OuvrageDetailResult(
            true,
            OuvrageDetail(
                id = ouvrage.getString("id"),
                name = ouvrage.optString("nom"),
                type = ouvrage.optString("type"),
                year = ouvrage.optString("annee_realisation").takeUnless { it == "null" } ?: "",
                previousYear = ouvrage.optString("annee_realisation_avant").takeUnless { it == "null" } ?: "",
                builder = ouvrage.optString("intervenant"),
                seasonal = ouvrage.optBoolean("saisonnier"),
                observation = ouvrage.optString("observation"),
                stats = stats,
                locations = locations,
                management = management,
                tariffs = tariffs,
                waterPoints = waterPoints,
                equipment = equipment,
                repairs = repairs,
                overduePayments = paymentRows("paiements_echus_non_pointes"),
                upcomingPayments = paymentRows("prochains_paiements"),
                latestDebit = nullableDouble("dernier_debit"),
                debitThreshold = nullableDouble("seuil_minimum"),
                debitGap = nullableDouble("ecart_seuil"),
                debitComparison = debitSource?.optString("comparaison") ?: "",
                debitHistory = debitHistory,
                fullUrl = ouvrage.optString("full_url"),
            ),
            null,
        )
    }

    private fun filteredPath(path: String, filters: TokenStore.Filters): String {
        val params = linkedMapOf<String, String>()
        if (filters.organisationId != "all") params["organisation"] = filters.organisationId
        if (filters.employeeId != "all") params["employe_id"] = filters.employeeId
        if (filters.regionId != "all") params["region_id"] = filters.regionId
        if (filters.districtId != "all") params["district_id"] = filters.districtId
        if (filters.communeId != "all") params["commune_id"] = filters.communeId
        if (params.isEmpty()) return path
        return path + "?" + params.entries.joinToString("&") {
            "${URLEncoder.encode(it.key, "UTF-8")}=${URLEncoder.encode(it.value, "UTF-8")}"
        }
    }
}
