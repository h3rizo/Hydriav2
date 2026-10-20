package mg.hydria.shared.planning

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class PlanningOption(val id: String, val label: String)
/** [query] : recherche libre par nom d'ouvrage ; hors panneau de filtres, donc non comptee dans activeFilterCount. */
data class PlanningFilters(val employeeId: String = "", val regionId: String = "",
    val districtId: String = "", val communeId: String = "", val query: String = "")
enum class PlanningFilter { EMPLOYEE, REGION, DISTRICT, COMMUNE }

/** [searchText] : texte interroge par la recherche libre (nom de l'ouvrage). */
data class PlanningRecord<T>(val entry: PlanningEntry<T>, val employees: List<PlanningOption>,
    val region: PlanningOption, val district: PlanningOption, val commune: PlanningOption,
    val searchText: String = "")

enum class PlanningFormError(val message: String) {
    EMPLOYEE("Sélectionnez un employé"), ACTIVITY("Sélectionnez une activité"),
    DATE_FORMAT("Date invalide : ce jour n'existe pas (AAAA-MM-JJ)")
}
data class PlanningDraft(val employeeId: String?, val activityId: String?, val date: String,
    val workId: String = "", val status: String = "en_cours", val remark: String = "", val existingId: String? = null)
data class PlanningFormResult(val error: PlanningFormError?, val fields: Map<String, String>?)

object PlanningFormRules {
    fun validate(draft: PlanningDraft): PlanningFormResult {
        val date = draft.date.trim()
        val error = when {
            draft.employeeId == null -> PlanningFormError.EMPLOYEE
            draft.activityId == null -> PlanningFormError.ACTIVITY
            !IsoDate.isReal(date) -> PlanningFormError.DATE_FORMAT
            else -> null
        }
        if (error != null) return PlanningFormResult(error, null)
        // Conserve le contrat du formulaire existant : ouvrage facultatif. La date doit etre une date
        // reelle (pas seulement bien formee). Django garde la validation metier finale.
        val fields = linkedMapOf("employe_id" to requireNotNull(draft.employeeId),
            "ouvrage_id" to draft.workId, "fiche_poste_id" to requireNotNull(draft.activityId),
            "date" to date, "statut" to draft.status, "remarque" to draft.remark.trim())
        draft.existingId?.takeIf { it.isNotBlank() }?.let { fields["id"] = it }
        return PlanningFormResult(null, fields)
    }
}

data class PlanningViewState<T>(
    val filters: PlanningFilters,
    val employeeOptions: List<PlanningOption>, val regionOptions: List<PlanningOption>,
    val districtOptions: List<PlanningOption>, val communeOptions: List<PlanningOption>,
    val items: List<T>, val totalCount: Int, val agenda: PlanningAgendaState<T>,
    val activeFilterCount: Int, val perimeterSummary: String,
    val formError: PlanningFormError? = null,
)

/** ViewModel commun sans Android ni JSON. Les evenements sont envoyes par le
 * thread UI de la plateforme ; aucun IO ni CoroutineScope a liberer ici.
 * Android retient l'instance dans son ViewModelStore ; Compose peut observer states.
 */
class PlanningViewModel<T>(
    private val sortKey: (String) -> String = { it.lowercase() },
    /** Normalisation de la recherche libre (la plateforme fournit le pliage des accents). */
    private val normalize: (String) -> String = { it.lowercase().trim() },
) {
    private var records = emptyList<PlanningRecord<T>>()
    private var filters = PlanningFilters()
    private var selectedDate = ""
    private var today = ""
    private var formError: PlanningFormError? = null
    private val mutableState = MutableStateFlow(computeState())
    val states: StateFlow<PlanningViewState<T>> = mutableState.asStateFlow()
    val state: PlanningViewState<T> get() = mutableState.value

    fun replaceRecords(records: List<PlanningRecord<T>>, today: String) {
        this.records = records.toList()
        this.today = today
        publish()
    }

    fun selectFilter(field: PlanningFilter, id: String) {
        filters = when (field) {
            PlanningFilter.EMPLOYEE -> filters.copy(employeeId = id)
            PlanningFilter.REGION -> filters.copy(regionId = id, districtId = "", communeId = "")
            PlanningFilter.DISTRICT -> filters.copy(districtId = id, communeId = "")
            PlanningFilter.COMMUNE -> filters.copy(communeId = id)
        }
        publish()
    }

    /** Recherche libre par ouvrage : tous les mots saisis doivent apparaitre dans le nom. */
    fun setQuery(query: String) {
        if (query == filters.query) return
        filters = filters.copy(query = query)
        publish()
    }

    fun selectDate(dateKey: String) {
        if (state.agenda.days.none { it.dateKey == dateKey }) return
        selectedDate = dateKey
        mutableState.value = state.copy(agenda = state.agenda.copy(selectedDate = dateKey))
    }

    fun validateForm(draft: PlanningDraft): PlanningFormResult {
        val result = PlanningFormRules.validate(draft)
        formError = result.error
        mutableState.value = state.copy(formError = formError)
        return result
    }

    fun clearFormError() { formError = null; mutableState.value = state.copy(formError = null) }

    private fun options(values: List<PlanningOption>, allLabel: String): List<PlanningOption> =
        listOf(PlanningOption("", allLabel)) + values.filter { it.id.isNotBlank() && it.label.isNotBlank() }
            .distinctBy { it.id }.sortedBy { sortKey(it.label) }

    private fun computeState(): PlanningViewState<T> {
        val employees = options(records.flatMap { it.employees }, "Tous les employés")
        val regions = options(records.map { it.region }, "Toutes les régions")
        filters = filters.copy(
            employeeId = filters.employeeId.takeIf { id -> employees.any { it.id == id } }.orEmpty(),
            regionId = filters.regionId.takeIf { id -> regions.any { it.id == id } }.orEmpty())
        val regionRecords = records.filter { filters.regionId.isBlank() || it.region.id == filters.regionId }
        val districts = options(regionRecords.map { it.district }, "Tous les districts")
        filters = filters.copy(districtId = filters.districtId.takeIf { id -> districts.any { it.id == id } }.orEmpty())
        val districtRecords = regionRecords.filter { filters.districtId.isBlank() || it.district.id == filters.districtId }
        val communes = options(districtRecords.map { it.commune }, "Toutes les communes")
        filters = filters.copy(communeId = filters.communeId.takeIf { id -> communes.any { it.id == id } }.orEmpty())
        val terms = normalize(filters.query).split(' ').filter { it.isNotBlank() }
        val matching = districtRecords.filter { record ->
            (filters.communeId.isBlank() || record.commune.id == filters.communeId) &&
                (filters.employeeId.isBlank() || record.employees.any { it.id == filters.employeeId }) &&
                (terms.isEmpty() || normalize(record.searchText).let { text -> terms.all { text.contains(it) } })
        }
        val parts = listOfNotNull(
            employees.firstOrNull { it.id == filters.employeeId }?.label?.takeIf { filters.employeeId.isNotBlank() },
            regions.firstOrNull { it.id == filters.regionId }?.label?.takeIf { filters.regionId.isNotBlank() },
            districts.firstOrNull { it.id == filters.districtId }?.label?.takeIf { filters.districtId.isNotBlank() },
            communes.firstOrNull { it.id == filters.communeId }?.label?.takeIf { filters.communeId.isNotBlank() })
        val agenda = PlanningAgenda.prepare(matching.map { it.entry }, selectedDate, today)
        selectedDate = agenda.selectedDate
        return PlanningViewState(filters, employees, regions, districts, communes,
            matching.map { it.entry.item }, records.size, agenda, parts.size,
            if (parts.isEmpty()) "Périmètre affiché : tout le périmètre disponible"
            else "Périmètre affiché : ${parts.joinToString(" · ")}", formError)
    }

    private fun publish() { mutableState.value = computeState() }
}
