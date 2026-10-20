package mg.hydria.shared.rules.search

import org.json.JSONArray
import org.json.JSONObject
import mg.hydria.shared.search.OfflineWorkSearch
import mg.hydria.shared.search.SearchWork

/** Conversion JSON du snapshot ; recherche dans commonMain. */
object SearchRules {
    /** Séparateur des 3 niveaux (région/district/commune) dans [worksGroupKey]. */
    const val GROUP_KEY_SEPARATOR = "\u0001"

    /**
     * Clé de regroupement région > district > commune pour la liste des ouvrages
     * (SearchActivity.renderGroupedWorks). Repris tel quel : mêmes libellés de
     * repli, mêmes 3 niveaux joints par [GROUP_KEY_SEPARATOR].
     */
    fun worksGroupKey(row: JSONObject): String = listOf(
        row.optString("region", "Région non renseignée"),
        row.optString("district", "District non renseigné"),
        row.optString("commune", "Commune non renseignée"),
    ).joinToString(GROUP_KEY_SEPARATOR)

    fun workSubtitle(item: JSONObject): String = OfflineWorkSearch.subtitle(
        item.optString("type"), item.optString("village"), item.optString("commune"))
    fun offlineWorksResults(works: JSONArray, query: String): JSONObject {
        val records = (0 until works.length()).map { index ->
            val work = works.getJSONObject(index)
            SearchWork(work, work.optString("nom"), work.optString("type"), work.optString("village"), work.optString("commune"))
        }
        val rows = JSONArray()
        OfflineWorkSearch.find(records, query).forEach { work ->
            rows.put(JSONObject().put("id", work.optString("id")).put("type", "ouvrage").put("type_display", "Ouvrage")
                .put("name", work.optString("nom")).put("title", work.optString("nom"))
                .put("subtitle", workSubtitle(work)).put("details", work))
        }
        return JSONObject().put("success", true).put("results", rows).put("total", rows.length()).put("has_next", false)
    }
}
