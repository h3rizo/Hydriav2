package mg.hydria.bienetre.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import mg.hydria.bienetre.core.model.*

@Serializable data class WorkoutPlanDto(
    val id: Long,
    @SerialName("objectif") val objective: String,
    @SerialName("date_debut") val startDate: String,
    @SerialName("frequence_semaine") val frequency: Int,
    @SerialName("duree_semaines") val durationWeeks: Int,
    @SerialName("actif") val active: Boolean,
)
@Serializable data class WorkoutPlanItemDto(
    val id: Long,
    @SerialName("semaine_index") val weekIndex: Int = 1,
    @SerialName("date_prevue") val plannedDate: String? = null,
    @SerialName("jour_semaine") val weekday: String = "",
    @SerialName("exercise") val exerciseId: Long,
    @SerialName("exercise_nom") val exerciseName: String = "",
    @SerialName("exercise_image_url") val remoteImageUrl: String? = null,
    @SerialName("exercise_image_file_url") val uploadedImageUrl: String? = null,
    @SerialName("series") val sets: Int = 0,
    @SerialName("repetitions") val repetitions: Int = 0,
    @SerialName("duree_secondes") val durationSeconds: Int = 0,
    @SerialName("repos_secondes") val restSeconds: Int = 0,
    @SerialName("poids_kg") val targetWeight: String? = null,
    @SerialName("suggested_weight_kg") val suggestedWeight: String? = null,
    @SerialName("niveau_cible") val targetLevel: String = "",
    @SerialName("note_coach") val coachNote: String = "",
    @SerialName("statut") val status: String = "prevu",
    @SerialName("ordre") val order: Int = 1,
    @SerialName("progression_hint") val progressionHint: String = "",
)
@Serializable data class WorkoutWeekDto(
    @SerialName("week_index") val index: Int,
    @SerialName("date_debut") val startDate: String,
    @SerialName("date_fin") val endDate: String,
    val items: List<WorkoutPlanItemDto> = emptyList(),
)
@Serializable data class WorkoutCycleDto(val plan: WorkoutPlanDto? = null, val weeks: List<WorkoutWeekDto> = emptyList())
@Serializable data class TodayWorkoutDto(
    val date: String,
    @SerialName("week_index") val weekIndex: Int? = null,
    val plan: WorkoutPlanDto? = null,
    val items: List<WorkoutPlanItemDto> = emptyList(),
)
@Serializable data class WorkoutDaySessionDto(
    val id: Long,
    val date: String,
    @SerialName("started_at") val startedAt: String,
    @SerialName("ended_at") val endedAt: String? = null,
    @SerialName("is_active") val active: Boolean,
    @SerialName("total_duration_seconds") val totalDuration: Int = 0,
    @SerialName("total_rest_seconds") val totalRest: Int = 0,
    @SerialName("total_time_under_tension_seconds") val totalTension: Int = 0,
    @SerialName("completed_items_count") val completedCount: Int = 0,
    @SerialName("analysis_summary") val analysis: String = "",
)
@Serializable data class WorkoutDaySessionEnvelope(val session: WorkoutDaySessionDto? = null)
@Serializable data class WorkoutHistoryDto(
    val id: Long,
    val date: String,
    @SerialName("exercice_nom") val exerciseName: String = "",
    @SerialName("series_realisees") val sets: Int = 0,
    @SerialName("repetitions_realisees") val repetitions: Int = 0,
    @SerialName("poids_utilise_kg") val weight: String? = null,
    @SerialName("duree_effective_secondes") val duration: Int = 0,
    @SerialName("commentaire") val comment: String = "",
)
@Serializable data class WorkoutGenerateRequest(
    @SerialName("date_debut") val startDate: String,
    @SerialName("frequence_semaine") val frequency: Int,
    @SerialName("duree_semaines") val durationWeeks: Int,
    @SerialName("replace_active") val replaceActive: Boolean = true,
)
@Serializable data class WorkoutCompleteRequest(
    @SerialName("workout_plan_item_id") val itemId: Long,
    val date: String,
    @SerialName("day_session_id") val daySessionId: Long?,
    @SerialName("series_realisees") val sets: Int,
    @SerialName("repetitions_realisees") val repetitions: Int,
    @SerialName("poids_utilise_kg") val weight: String?,
    @SerialName("repos_secondes_effectif") val restSeconds: Int,
    @SerialName("duree_effective_secondes") val durationSeconds: Int,
    @SerialName("commentaire") val comment: String,
)
@Serializable data class WorkoutPostponeRequest(
    @SerialName("workout_plan_item_id") val itemId: Long,
    @SerialName("new_date") val newDate: String,
)

internal fun WorkoutPlanDto.toModel() = WorkoutPlan(id, objective, startDate, frequency, durationWeeks, active)
internal fun WorkoutPlanItemDto.toModel() = WorkoutPlanItem(id, weekIndex, plannedDate, weekday, exerciseId, exerciseName, uploadedImageUrl ?: remoteImageUrl, sets, repetitions, durationSeconds, restSeconds, targetWeight.decimalOrNull(), suggestedWeight.decimalOrNull(), targetLevel, coachNote, status, order, progressionHint)
internal fun WorkoutCycleDto.toModel() = WorkoutCycle(plan?.toModel(), weeks.map { WorkoutWeek(it.index, it.startDate, it.endDate, it.items.map(WorkoutPlanItemDto::toModel)) })
internal fun TodayWorkoutDto.toModel() = TodayWorkout(date, weekIndex, plan?.toModel(), items.map(WorkoutPlanItemDto::toModel))
internal fun WorkoutDaySessionDto.toModel() = WorkoutDaySession(id, date, startedAt, endedAt, active, totalDuration, totalRest, totalTension, completedCount, analysis)
internal fun WorkoutHistoryDto.toModel() = WorkoutHistoryEntry(id, date, exerciseName, sets, repetitions, weight.decimalOrNull(), duration, comment)
private fun String?.decimalOrNull() = this?.replace(',', '.')?.toDoubleOrNull()
