package mg.hydria.app.planning

import org.json.JSONObject

/**
 * Relais fin vers le module partage `shared` (Phase 0 de la migration
 * KMP). Les regles sont dans commonMain/planning/PlanningAgenda.kt ;
 * l'adaptateur jvmCommonMain convertit uniquement les JSONObject.
 * ce fichier ne fait plus que le pointer, pour ne rien casser des appels
 * existants (MainActivity, etc.) pendant la transition.
 */
typealias PlanningDayState = mg.hydria.shared.rules.planning.PlanningDayState

object PlanningRules {
    fun dateKey(planning: JSONObject): String =
        mg.hydria.shared.rules.planning.PlanningRules.dateKey(planning)

    fun weekdayLabel(dateKey: String): String =
        mg.hydria.shared.rules.planning.PlanningRules.weekdayLabel(dateKey)

    fun fullDateLabel(dateKey: String): String =
        mg.hydria.shared.rules.planning.PlanningRules.fullDateLabel(dateKey)

    fun dayState(dateKey: String, plannings: List<JSONObject>): PlanningDayState =
        mg.hydria.shared.rules.planning.PlanningRules.dayState(dateKey, plannings)

    fun dayIndicatorText(state: PlanningDayState): String =
        mg.hydria.shared.rules.planning.PlanningRules.dayIndicatorText(state)

    fun shortWeekdayLabel(dateKey: String): String =
        mg.hydria.shared.rules.planning.PlanningRules.shortWeekdayLabel(dateKey)

    fun dayNumberLabel(dateKey: String): String =
        mg.hydria.shared.rules.planning.PlanningRules.dayNumberLabel(dateKey)

    fun activityKind(planning: JSONObject): mg.hydria.shared.planning.PlanningActivityKind =
        mg.hydria.shared.rules.planning.PlanningRules.activityKind(planning)

    fun agenda(plannings: List<JSONObject>, selectedDate: String, today: String) =
        mg.hydria.shared.rules.planning.PlanningRules.agenda(plannings, selectedDate, today)
}
