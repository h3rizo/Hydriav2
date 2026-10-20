package mg.hydria.shared.planning

import kotlinx.datetime.LocalDate
import kotlin.math.abs

/** Metadonnees de calendrier independantes du format de stockage de l'element. */
data class PlanningEntry<T>(
    val item: T,
    val date: String,
    val isWeekend: Boolean = false,
    val isHoliday: Boolean = false,
)

data class PlanningDayState(val isWeekend: Boolean, val isHoliday: Boolean)
enum class PlanningActivityKind { VALIDATED, REPAIR, REST, OTHER }

data class PlanningAgendaDay<T>(val dateKey: String, val items: List<T>, val state: PlanningDayState)

/** Etat immutable utilisable par un futur ViewModel Android ou Compose Desktop. */
data class PlanningAgendaState<T>(val days: List<PlanningAgendaDay<T>>, val selectedDate: String)

object PlanningAgenda {
    private val datePattern = Regex("\\d{4}-\\d{2}-\\d{2}")
    private val weekdays = listOf("LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE")
    private val shortWeekdays = listOf("LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM")
    private val months = listOf("janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre")

    // Conserve la convention historique : date absente/mal formee triee en dernier.
    // Une date syntaxiquement correcte mais impossible garde sa cle et ses libelles de secours.
    fun dateKey(rawDate: String): String = rawDate.take(10).takeIf { it.matches(datePattern) } ?: "9999-12-31"

    private fun parse(dateKey: String): LocalDate? = runCatching { LocalDate.parse(dateKey) }.getOrNull()

    fun weekdayLabel(dateKey: String): String = parse(dateKey)?.let { weekdays[it.dayOfWeek.ordinal] } ?: "DATE À CONFIRMER"
    fun shortWeekdayLabel(dateKey: String): String = parse(dateKey)?.let { shortWeekdays[it.dayOfWeek.ordinal] } ?: "—"
    fun dayNumberLabel(dateKey: String): String = parse(dateKey)?.dayOfMonth?.toString() ?: "—"
    fun fullDateLabel(dateKey: String): String = parse(dateKey)?.let {
        // DateTimeFormatter yyyy utilise l'annee de l'ere (1 pour l'annee ISO 0).
        val yearOfEra = if (it.year > 0) it.year else 1 - it.year
        "${it.dayOfMonth} ${months[it.month.ordinal]} ${yearOfEra.toString().padStart(4, '0')}"
    } ?: "Date non renseignée"

    fun dayState(dateKey: String, weekendFlag: Boolean, holidayFlag: Boolean): PlanningDayState =
        PlanningDayState((parse(dateKey)?.dayOfWeek?.ordinal ?: -1) >= 5 || weekendFlag, holidayFlag)

    fun dayIndicatorText(state: PlanningDayState): String = listOfNotNull(
        "FÉRIÉ".takeIf { state.isHoliday }, "WEEK-END".takeIf { state.isWeekend },
    ).joinToString(" · ")

    fun activityKind(validated: Boolean, activityType: String, jobLabel: String): PlanningActivityKind {
        val kind = "$activityType $jobLabel".lowercase()
        return when {
            validated -> PlanningActivityKind.VALIDATED
            "répar" in kind || "repar" in kind || "urgen" in kind || "panne" in kind -> PlanningActivityKind.REPAIR
            "congé" in kind || "conge" in kind || "repos" in kind || "férié" in kind -> PlanningActivityKind.REST
            else -> PlanningActivityKind.OTHER
        }
    }

    /** L'horloge vient de l'appelant : aucune dependance au fuseau ou au cycle de vie Android. */
    fun <T> prepare(entries: List<PlanningEntry<T>>, selectedDate: String, today: String): PlanningAgendaState<T> {
        val days = entries.sortedBy { dateKey(it.date) }.groupBy { dateKey(it.date) }.map { (key, group) ->
            PlanningAgendaDay(key, group.map { it.item }, dayState(key,
                group.any { it.isWeekend }, group.any { it.isHoliday }))
        }
        val active = selectedDate.takeIf { selection -> days.any { it.dateKey == selection } }
            ?: days.minByOrNull { distance(today, it.dateKey) }?.dateKey.orEmpty()
        return PlanningAgendaState(days, active)
    }

    private fun distance(today: String, dateKey: String): Long {
        val from = parse(today) ?: return Long.MAX_VALUE
        val to = parse(dateKey) ?: return Long.MAX_VALUE
        return abs(to.toEpochDays().toLong() - from.toEpochDays().toLong())
    }
}
