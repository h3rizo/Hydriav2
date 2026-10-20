package mg.hydria.app.repairs

import mg.hydria.app.HydriaColors
import mg.hydria.app.Tone
import org.json.JSONArray
import org.json.JSONObject

/**
 * Relais fin vers le module partage `shared` (Phase 0 de la migration
 * KMP). Le code metier reel a demenage vers
 * shared/src/jvmCommonMain/kotlin/mg/hydria/shared/rules/repairs/RepairRules.kt ;
 * ce fichier ne fait plus que le pointer.
 *
 * priorityTone()/priorityColor() restent ici (pas dans shared) car
 * HydriaColors/Tone sont des types Android definis dans HydriaVisuals.kt :
 * le module partage ne connait que la criticite (Int 1-5) via criticality().
 */
object RepairRules {
    fun pendingCompletionIds(pending: JSONArray): Set<String> =
        mg.hydria.shared.rules.repairs.RepairRules.pendingCompletionIds(pending)

    fun isCompleted(repair: JSONObject): Boolean =
        mg.hydria.shared.rules.repairs.RepairRules.isCompleted(repair)

    fun workKey(repair: JSONObject): String =
        mg.hydria.shared.rules.repairs.RepairRules.workKey(repair)

    fun activityLabel(repair: JSONObject): String =
        mg.hydria.shared.rules.repairs.RepairRules.activityLabel(repair)

    fun priorityLabel(repair: JSONObject): String =
        mg.hydria.shared.rules.repairs.RepairRules.priorityLabel(repair)

    fun criticality(repair: JSONObject): Int =
        mg.hydria.shared.rules.repairs.RepairRules.criticality(repair)

    fun priorityTone(repair: JSONObject): Tone = when (criticality(repair)) {
        5, 4 -> Tone.ERROR
        3 -> Tone.WARNING
        else -> Tone.INFO
    }

    /** Couleur de TEXTE de la priorité (jetons de texte : contraste suffisant en mode clair). */
    fun priorityColor(repair: JSONObject): Int = when (criticality(repair)) {
        5, 4 -> HydriaColors.errorText
        3 -> HydriaColors.warningText
        else -> HydriaColors.cyanText
    }

    fun dateKey(repair: JSONObject): String =
        mg.hydria.shared.rules.repairs.RepairRules.dateKey(repair)

    fun overdueDays(repair: JSONObject): Int? =
        mg.hydria.shared.rules.repairs.RepairRules.overdueDays(repair)

    fun overdueLabel(repair: JSONObject): mg.hydria.shared.repairs.OverdueLabel? =
        mg.hydria.shared.rules.repairs.RepairRules.overdueLabel(repair)

    fun countsOnTabBadge(repair: JSONObject, completed: Boolean): Boolean =
        mg.hydria.shared.rules.repairs.RepairRules.countsOnTabBadge(repair, completed)
}
