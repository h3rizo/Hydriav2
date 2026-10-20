package mg.hydria.shared.rules.planning

import org.json.JSONObject
import mg.hydria.shared.planning.PlanningAgenda
import mg.hydria.shared.planning.PlanningAgendaState
import mg.hydria.shared.planning.PlanningEntry
import mg.hydria.shared.planning.PlanningActivityKind

typealias PlanningDayState = mg.hydria.shared.planning.PlanningDayState

/** Adaptateur de compatibilite JVM : JSON uniquement ici, regles dans commonMain. */
object PlanningRules {
    fun dateKey(planning: JSONObject): String = PlanningAgenda.dateKey(planning.optString("date"))
    fun weekdayLabel(dateKey: String): String = PlanningAgenda.weekdayLabel(dateKey)
    fun shortWeekdayLabel(dateKey: String): String = PlanningAgenda.shortWeekdayLabel(dateKey)
    fun dayNumberLabel(dateKey: String): String = PlanningAgenda.dayNumberLabel(dateKey)
    fun fullDateLabel(dateKey: String): String = PlanningAgenda.fullDateLabel(dateKey)
    fun dayState(dateKey: String, plannings: List<JSONObject>): PlanningDayState =
        PlanningAgenda.dayState(dateKey, plannings.any { it.optBoolean("weekend") }, plannings.any { it.optBoolean("jour_ferie") })
    fun dayIndicatorText(state: PlanningDayState): String = PlanningAgenda.dayIndicatorText(state)
    fun activityKind(planning: JSONObject): PlanningActivityKind = PlanningAgenda.activityKind(
        planning.optBoolean("valide"), planning.optString("type_activite"), planning.optString("fiche_poste"))
    fun agenda(plannings: List<JSONObject>, selectedDate: String, today: String): PlanningAgendaState<JSONObject> =
        PlanningAgenda.prepare(plannings.map { PlanningEntry(it, it.optString("date"),
            it.optBoolean("weekend"), it.optBoolean("jour_ferie")) }, selectedDate, today)
}
