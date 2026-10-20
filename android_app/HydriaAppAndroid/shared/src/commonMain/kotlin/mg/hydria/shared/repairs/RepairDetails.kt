package mg.hydria.shared.repairs

import kotlinx.datetime.LocalDate
import mg.hydria.shared.planning.PlanningAgenda

data class RepairPendingAction(val type: String, val planningId: String)

/** Texte de la colonne de retard d'une carte de réparation : [value] gros, [caption] en dessous (peut être vide). */
data class OverdueLabel(val value: String, val caption: String, val late: Boolean)

object RepairDetails {
    fun pendingCompletionIds(actions: List<RepairPendingAction>): Set<String> = actions
        .filter { it.type == "finish_repair" && it.planningId.isNotBlank() }.map { it.planningId }.toSet()

    fun isCompleted(completed: Boolean, status: String): Boolean = completed || status.trim().lowercase() in
        setOf("terminee", "terminée", "termine", "terminé", "cloturee", "clôturée", "done", "completed")

    fun workKey(id: String, name: String): String = id.takeIf { it.isNotBlank() } ?: name.trim().lowercase()
    fun activityLabel(title: String, job: String, activity: String): String =
        listOf(title, job, activity).firstOrNull { it.isNotBlank() } ?: "Réparation"
    fun priorityLabel(priority: String): String = priority.ifBlank { "Normale" }
    fun criticality(code: String, label: String): Int {
        val priority = "$code ${priorityLabel(label)}".lowercase()
        return when {
            "crit" in priority -> 5
            "urgent" in priority -> 4
            "haut" in priority || "élev" in priority || "elev" in priority -> 3
            "normal" in priority || "moyen" in priority -> 2
            else -> 1
        }
    }
    fun dateKey(rawDate: String): String = PlanningAgenda.dateKey(rawDate)

    /** Le jour courant est fourni par la plateforme, dans son fuseau local. */
    fun overdueDays(rawDate: String, today: String): Int? {
        val key = rawDate.take(10)
        if (!key.matches(Regex("\\d{4}-\\d{2}-\\d{2}"))) return null
        return runCatching { (LocalDate.parse(today).toEpochDays() - LocalDate.parse(key).toEpochDays()).toInt() }.getOrNull()
    }

    /**
     * Libellé du retard à partir de [overdueDays] (positif = en retard, négatif = à venir, null = date inconnue).
     * « 224 j » + « RETARD » ; « AUJ. » le jour même ; « dans 5 j » à venir. Jamais de signe négatif :
     * « -224 » se lisait à l'envers de la convention « J-5 » et n'était légendé nulle part (REP_PLAN-11).
     */
    fun overdueLabel(overdueDays: Int?): OverdueLabel? = when {
        overdueDays == null -> null
        overdueDays > 0 -> OverdueLabel("$overdueDays j", "RETARD", true)
        overdueDays == 0 -> OverdueLabel("AUJ.", "", false)
        else -> OverdueLabel("dans ${-overdueDays} j", "", false)
    }

    /**
     * Une réparation compte sur le badge de l'onglet seulement si elle est échue (au moins 1 jour de
     * retard), non terminée et dans le périmètre : le badge signale l'urgence, pas tout ce qui reste à faire.
     */
    fun countsOnTabBadge(completed: Boolean, outsidePerimeter: Boolean, overdueDays: Int?): Boolean =
        !completed && !outsidePerimeter && overdueDays != null && overdueDays > 0
}
