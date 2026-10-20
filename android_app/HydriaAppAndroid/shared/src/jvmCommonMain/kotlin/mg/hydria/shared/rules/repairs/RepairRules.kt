package mg.hydria.shared.rules.repairs

import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import java.time.ZoneId
import mg.hydria.shared.repairs.OverdueLabel
import mg.hydria.shared.repairs.RepairDetails
import mg.hydria.shared.repairs.RepairPendingAction

/** Adaptateur JSON et horloge locale ; les règles résident dans commonMain. */
object RepairRules {
    /** « Aujourd'hui » se compte à l'heure de Madagascar, quel que soit le fuseau de l'appareil. */
    private val ZONE = ZoneId.of("Indian/Antananarivo")

    fun pendingCompletionIds(pending: JSONArray): Set<String> = runCatching {
        RepairDetails.pendingCompletionIds((0 until pending.length()).mapNotNull { index ->
            val action = pending.optJSONObject(index) ?: return@mapNotNull null
            RepairPendingAction(action.optString("type"), action.optJSONObject("payload")?.optString("planning_id").orEmpty())
        })
    }.getOrDefault(emptySet())
    fun isCompleted(repair: JSONObject): Boolean = RepairDetails.isCompleted(repair.optBoolean("terminee"),
        repair.optString("statut_code", repair.optString("statut")))
    fun workKey(repair: JSONObject): String = RepairDetails.workKey(repair.optString("ouvrage_id"), repair.optString("ouvrage_nom", "Sans ouvrage"))
    fun activityLabel(repair: JSONObject): String = RepairDetails.activityLabel(repair.optString("titre"), repair.optString("fiche_poste"), repair.optString("activite"))
    fun priorityLabel(repair: JSONObject): String = RepairDetails.priorityLabel(repair.optString("priorite", "Normale"))
    fun criticality(repair: JSONObject): Int = RepairDetails.criticality(repair.optString("priorite_code"), priorityLabel(repair))
    fun dateKey(repair: JSONObject): String = RepairDetails.dateKey(repair.optString("date_prevue"))
    fun overdueDays(repair: JSONObject): Int? = RepairDetails.overdueDays(repair.optString("date_prevue"), LocalDate.now(ZONE).toString())
    fun overdueLabel(repair: JSONObject): OverdueLabel? = RepairDetails.overdueLabel(overdueDays(repair))
    /** Vrai si la réparation compte sur le badge de l'onglet : échue, non terminée, dans le périmètre. */
    fun countsOnTabBadge(repair: JSONObject, completed: Boolean): Boolean =
        RepairDetails.countsOnTabBadge(completed, repair.optBoolean("hors_perimetre"), overdueDays(repair))
}
