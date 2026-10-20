package mg.hydria.shared.repairs

import mg.hydria.shared.planning.IsoDate
import mg.hydria.shared.planning.PlanningDraft
import mg.hydria.shared.planning.PlanningFormRules

/**
 * Cible d'une réparation : un équipement OU un point d'eau (jamais les deux) et le ou les
 * composants concernés. Un brouillon sans cible (`target = null`) n'envoie aucun de ces champs,
 * ce qui laisse la cible enregistrée côté serveur inchangée.
 */
data class RepairTarget(val equipmentId: String = "", val pointEauId: String = "",
    val componentIds: List<String> = emptyList())

data class RepairDraft(val employeeId: String?, val activityId: String?, val workId: String,
    val date: String, val status: String = "en_cours", val priority: String = "normale",
    val remark: String = "", val existingId: String? = null, val target: RepairTarget? = null)
enum class RepairFormError(val message: String) {
    EMPLOYEE("Sélectionnez un employé"), ACTIVITY("Sélectionnez une activité"),
    WORK("Sélectionnez un ouvrage"), DATE_FORMAT("Date invalide : ce jour n'existe pas (AAAA-MM-JJ)"),
    TARGET_CONFLICT("Choisissez un équipement ou un point d'eau, pas les deux"),
    COMPONENTS_WITHOUT_TARGET("Choisissez la cible avant les composants")
}
data class RepairFormResult(val error: RepairFormError?, val fields: Map<String, String>?)

object RepairFormRules {
    fun validate(draft: RepairDraft): RepairFormResult {
        val error = when {
            draft.employeeId == null -> RepairFormError.EMPLOYEE
            draft.activityId == null -> RepairFormError.ACTIVITY
            draft.workId.isBlank() -> RepairFormError.WORK
            !IsoDate.isReal(draft.date) -> RepairFormError.DATE_FORMAT
            draft.target != null && draft.target.equipmentId.isNotBlank() && draft.target.pointEauId.isNotBlank() ->
                RepairFormError.TARGET_CONFLICT
            draft.target != null && draft.target.componentIds.isNotEmpty() &&
                draft.target.equipmentId.isBlank() && draft.target.pointEauId.isBlank() ->
                RepairFormError.COMPONENTS_WITHOUT_TARGET
            else -> null
        }
        if (error != null) return RepairFormResult(error, null)
        val base = PlanningFormRules.validate(PlanningDraft(draft.employeeId, draft.activityId,
            draft.date, draft.workId, draft.status, draft.remark, draft.existingId))
        val fields = requireNotNull(base.fields) + ("priorite" to draft.priority)
        val target = draft.target ?: return RepairFormResult(null, fields)
        // Le serveur lit un formulaire (une seule valeur par cle) : les composants voyagent en "a,b,c".
        return RepairFormResult(null, fields + mapOf(
            "equipement_id" to target.equipmentId.trim(),
            "point_eau_id" to target.pointEauId.trim(),
            "composants_ids" to target.componentIds.map { it.trim() }.filter { it.isNotEmpty() }.distinct().joinToString(","),
        ))
    }
}
