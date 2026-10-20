package mg.hydria.desktop.screens

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.shared.database.HydriaSearchCacheGateway
import mg.hydria.shared.database.HydriaSnapshotGateway
import mg.hydria.shared.network.HydriaOperationsGateway
import mg.hydria.shared.rules.search.SearchRules
import org.json.JSONArray
import org.json.JSONObject

enum class SearchSection(val label: String) { ALL("Tout"), WORKS("Ouvrages"), PEOPLE("Personnes") }

/**
 * Reproduit SearchActivity (Android) cote Desktop, filtres compris :
 *  - onglet « Tout »      -> cases de categories (`selectedTypes`) transmises a
 *    `HydriaOperationsGateway.search(token, q, types, page)` ;
 *  - onglet « Personnes » -> type + statut (`people(token, q, type, status, page)`) ;
 *  - onglet « Ouvrages »  -> region / district / commune / employe responsable
 *    (`works(...)`), listes de reference via `workFilters(token)` (mises en cache
 *    SQLDelight sous "work_filters", repli hors-ligne).
 * Enchaînement inchange : reseau -> cache `HydriaSearchCacheGateway` -> repli
 * snapshot (`SearchRules.offlineWorksResults`). Aucune regle metier ici.
 */
class SearchController(private val session: DesktopSession) {
    companion object {
        /** Identique a SearchActivity.ALL_TYPES (ordre inclus). */
        val ALL_TYPES: List<Pair<String, String>> = listOf(
            "village" to "Villages", "ouvrage" to "Ouvrages", "commune" to "Communes",
            "planning" to "Plannings", "employe" to "Employes", "point_eau" to "Points d'eau",
            "representant" to "Representantes", "autorite" to "Autorites", "tiers" to "Tiers",
            "fournisseur" to "Fournisseurs", "equipement" to "Equipements",
            "designation" to "Designations", "modalite" to "Modalites", "carte_sociale" to "Cartes sociales",
        )
        val PEOPLE_TYPES: List<Pair<String, String>> = listOf(
            "" to "Tous les types",
            "abonne" to "Abonne", "employe" to "Employe", "representant" to "Representante",
            "autorite" to "Autorite", "tiers" to "Tiers", "fournisseur" to "Fournisseur",
        )
        val PEOPLE_STATUSES: List<Pair<String, String>> = listOf(
            "actif" to "Actifs seulement", "inactif" to "Inactifs seulement", "tous" to "Actifs et inactifs",
        )
        private const val WORK_FILTERS_KEY = "work_filters"
    }

    var section: SearchSection by mutableStateOf(SearchSection.ALL)
    var query: String by mutableStateOf("")
    var loading: Boolean by mutableStateOf(false)
    var results: List<JSONObject> by mutableStateOf(emptyList())
    var total: Int by mutableStateOf(0)
    var offlineCopy: Boolean by mutableStateOf(false)
    var message: String? by mutableStateOf(null)

    // ── Onglet « Tout » : categories ──
    var selectedTypes: Set<String> by mutableStateOf(
        ALL_TYPES.map { it.first }.filterNot { it == "planning" }.toSet(),
    )
        private set

    fun toggleType(id: String) {
        selectedTypes = if (id in selectedTypes) selectedTypes - id else selectedTypes + id
    }
    fun selectAllTypes() { selectedTypes = ALL_TYPES.map { it.first }.toSet() }
    fun clearTypes() { selectedTypes = emptySet() }

    // ── Onglet « Personnes » ──
    var peopleType: String by mutableStateOf("")
    var peopleStatus: String by mutableStateOf("actif")

    // ── Onglet « Ouvrages » : filtres geo ──
    var workRegion: String by mutableStateOf("")
    var workDistrict: String by mutableStateOf("")
    var workCommune: String by mutableStateOf("")
    var workEmployee: String by mutableStateOf("")
    var workFilters: JSONObject? by mutableStateOf(null)
        private set

    fun resetWorkFilters() { workRegion = ""; workDistrict = ""; workCommune = ""; workEmployee = "" }

    /** Options `{id,label}` d'une facette ouvrages, prefixees de « Tous ». */
    fun workOptions(key: String): List<JSONObject> {
        val rows = workFilters?.optJSONArray(key) ?: JSONArray()
        return listOf(JSONObject().put("id", "").put("label", "Tous")) +
            (0 until rows.length()).mapNotNull { rows.optJSONObject(it) }
    }

    /** Charge les listes de reference (reseau puis cache, repli cache hors-ligne). */
    suspend fun loadWorkFilters() {
        if (workFilters != null) return
        val token = session.token ?: return
        val fetched = withContext(Dispatchers.IO) {
            runCatching { HydriaOperationsGateway.workFilters(token) }.getOrNull()
        }
        val body = fetched?.takeIf { it.status in 200..299 }?.body
        if (body != null) {
            runCatching { HydriaSearchCacheGateway.save(WORK_FILTERS_KEY, body) }
            workFilters = body
        } else {
            workFilters = runCatching { HydriaSearchCacheGateway.payload(WORK_FILTERS_KEY) }.getOrNull()
        }
    }

    private var page = 1

    private fun cacheKey(): String = buildString {
        append("search:").append(section.name).append(':')
        append(query.trim().lowercase()).append(':')
        append(selectedTypes.sorted()).append(':')
        append(peopleType).append(':').append(peopleStatus).append(':')
        append(workRegion).append(':').append(workDistrict).append(':')
        append(workCommune).append(':').append(workEmployee).append(':').append(page)
    }

    suspend fun run() {
        val q = query.trim()
        page = 1
        if (section == SearchSection.ALL && q.length < 2) {
            reset("Saisissez au moins 2 caracteres pour lancer la recherche.")
            return
        }
        val token = session.token
        if (token.isNullOrBlank()) {
            reset("Session expiree : reconnectez-vous.")
            return
        }
        loading = true
        message = null
        val key = cacheKey()

        val outcome = withContext(Dispatchers.IO) {
            runCatching {
                when (section) {
                    SearchSection.ALL -> HydriaOperationsGateway.search(token, q, selectedTypes, page)
                    SearchSection.WORKS -> HydriaOperationsGateway.works(
                        token, q, page, workRegion, workDistrict, workCommune, workEmployee,
                    )
                    SearchSection.PEOPLE -> HydriaOperationsGateway.people(token, q, peopleType, peopleStatus, page)
                }
            }
        }
        loading = false

        outcome.onSuccess { result ->
            val body = result.body
            if (result.status in 200..299 && body.optBoolean("success", true)) {
                runCatching { HydriaSearchCacheGateway.save(key, body) }
                consume(body, offline = false)
            } else {
                message = body.optString("error", "Erreur HTTP ${result.status}")
                results = emptyList(); total = 0
            }
        }.onFailure {
            val cached = runCatching { HydriaSearchCacheGateway.payload(key) }.getOrNull()
                ?: offlineSnapshotResults(q)
            if (cached != null) consume(cached, offline = true)
            else reset("Recherche indisponible et rien en cache pour cette requete.")
        }
    }

    private fun consume(payload: JSONObject, offline: Boolean) {
        val rows = payload.optJSONArray("results") ?: JSONArray()
        results = (0 until rows.length()).mapNotNull { rows.optJSONObject(it) }
        total = payload.optInt("total", results.size)
        offlineCopy = offline
        message = if (results.isEmpty()) "Aucun resultat." else null
    }

    private fun offlineSnapshotResults(q: String): JSONObject? {
        if (section == SearchSection.PEOPLE) return null
        val works = HydriaSnapshotGateway.snapshot()
            ?.optJSONObject("terrain")?.optJSONArray("ouvrages") ?: return null
        return SearchRules.offlineWorksResults(works, q)
    }

    private fun reset(msg: String) {
        results = emptyList(); total = 0; offlineCopy = false; loading = false
        message = msg
    }
}
