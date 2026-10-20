package mg.hydria.shared.rules.planning

import mg.hydria.shared.planning.*
import org.json.JSONObject
import java.text.Normalizer
import java.util.Locale

/** Conversion du snapshot historique. Aucun acces reseau ou stockage dans ce relais. */
class PlanningViewModelGateway {
    private val model = PlanningViewModel<JSONObject>(
        sortKey = { it.lowercase(Locale.getDefault()) },
        normalize = ::foldForSearch,
    )
    val state: PlanningViewState<JSONObject> get() = model.state

    fun replaceItems(items: List<JSONObject>, today: String) = model.replaceRecords(items.map(::record), today)
    fun selectFilter(field: PlanningFilter, id: String) = model.selectFilter(field, id)
    /** Recherche libre par nom d'ouvrage (accents et casse ignores). */
    fun setQuery(query: String) = model.setQuery(query)
    fun selectDate(dateKey: String) = model.selectDate(dateKey)
    fun clearFormError() = model.clearFormError()
    fun validateForm(draft: PlanningDraft): PlanningFormResult = model.validateForm(draft)

    private fun record(item: JSONObject): PlanningRecord<JSONObject> = PlanningRecord(
        PlanningEntry(item, item.optString("date"), item.optBoolean("weekend"), item.optBoolean("jour_ferie")),
        employees(item), geo(item, "region"), geo(item, "district"), geo(item, "commune"),
        searchText = item.optString("ouvrage_nom"))

    private fun foldForSearch(value: String): String =
        Normalizer.normalize(value, Normalizer.Form.NFD).replace(Regex("\\p{M}+"), "")
            .lowercase(Locale.ROOT).trim()

    private fun geo(item: JSONObject, key: String): PlanningOption {
        val label = item.optString(key).trim()
        val id = item.optString("${key}_id").trim().ifBlank { if (label.isBlank()) "" else "nom:$label" }
        return PlanningOption(id, label)
    }

    private fun employees(item: JSONObject): List<PlanningOption> {
        val result = mutableListOf<PlanningOption>()
        val array = item.optJSONArray("employes")
        if (array != null) for (index in 0 until array.length()) {
            val employee = array.optJSONObject(index) ?: continue
            val label = employee.optString("nom").trim()
            if (label.isNotBlank()) result.add(PlanningOption(employee.optString("id").ifBlank { "nom:$label" }, label))
        }
        if (result.isEmpty()) {
            listOf(item.optString("employe"), item.optString("assigne_a"), item.optString("participants"))
                .flatMap { it.split(',') }.map { it.trim() }.filter { it.isNotBlank() }
                .forEach { result.add(PlanningOption("nom:$it", it)) }
        }
        return result.distinctBy { it.id }
    }
}
