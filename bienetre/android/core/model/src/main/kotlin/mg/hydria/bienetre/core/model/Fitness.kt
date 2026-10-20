package mg.hydria.bienetre.core.model

data class WorkoutPlan(
    val id: Long,
    val objective: String,
    val startDate: String,
    val frequencyPerWeek: Int,
    val durationWeeks: Int,
    val active: Boolean,
)

data class WorkoutPlanItem(
    val id: Long,
    val weekIndex: Int,
    val plannedDate: String?,
    val weekday: String,
    val exerciseId: Long,
    val exerciseName: String,
    val imageUrl: String?,
    val sets: Int,
    val repetitions: Int,
    val durationSeconds: Int,
    val restSeconds: Int,
    val targetWeightKg: Double?,
    val suggestedWeightKg: Double?,
    val targetLevel: String,
    val coachNote: String,
    val status: String,
    val order: Int,
    val progressionHint: String,
)

data class WorkoutWeek(val index: Int, val startDate: String, val endDate: String, val items: List<WorkoutPlanItem>)
data class WorkoutCycle(val plan: WorkoutPlan?, val weeks: List<WorkoutWeek>)
data class TodayWorkout(val date: String, val weekIndex: Int?, val plan: WorkoutPlan?, val items: List<WorkoutPlanItem>)

data class WorkoutDaySession(
    val id: Long,
    val date: String,
    val startedAt: String,
    val endedAt: String?,
    val active: Boolean,
    val totalDurationSeconds: Int,
    val totalRestSeconds: Int,
    val totalTensionSeconds: Int,
    val completedItemsCount: Int,
    val analysis: String,
)

data class WorkoutHistoryEntry(
    val id: Long,
    val date: String,
    val exerciseName: String,
    val sets: Int,
    val repetitions: Int,
    val weightKg: Double?,
    val durationSeconds: Int,
    val comment: String,
)

data class FitnessOverview(
    val cycle: WorkoutCycle,
    val today: TodayWorkout,
    val daySession: WorkoutDaySession?,
    val history: List<WorkoutHistoryEntry>,
)
