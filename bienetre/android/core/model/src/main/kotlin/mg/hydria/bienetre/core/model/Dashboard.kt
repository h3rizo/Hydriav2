package mg.hydria.bienetre.core.model

data class Dashboard(
    val date: String,
    val objective: String?,
    val metricsMessage: String?,
    val missingProfileFields: List<String>,
    val nutrition: NutritionProgress,
    val meals: List<DashboardMeal>,
    val workouts: List<DashboardWorkout>,
    val shoppingItems: List<DashboardShoppingItem>,
    val latestMeasurement: DashboardMeasurement?,
    val weightDelta: Double?,
    val suggestions: List<String>,
)

data class NutritionProgress(
    val calories: NutrientProgress,
    val proteins: NutrientProgress,
    val carbohydrates: NutrientProgress,
    val fats: NutrientProgress,
) {
    val overallPercent: Int
        get() = listOf(calories, proteins, carbohydrates, fats)
            .filter { it.target != null && it.target > 0.0 }
            .map { it.percent }
            .takeIf { it.isNotEmpty() }
            ?.average()
            ?.toInt()
            ?: 0
}

data class NutrientProgress(val consumed: Double, val target: Double?) {
    val percent: Int
        get() = if (target == null || target <= 0.0) 0
        else ((consumed / target) * 100).toInt().coerceIn(0, 100)
}

data class DashboardMeal(
    val id: Long,
    val type: String,
    val recipeName: String,
    val status: String,
    val portions: Double,
    val calories: Double,
)

data class DashboardWorkout(
    val id: Long,
    val exercise: String,
    val sets: Int,
    val repetitions: Int?,
    val durationSeconds: Int?,
    val completed: Boolean,
)

data class DashboardShoppingItem(
    val id: Long,
    val name: String,
    val icon: String?,
    val quantity: Double,
    val unit: String,
    val checked: Boolean,
)

data class DashboardMeasurement(
    val date: String,
    val weight: Double?,
    val muscleMass: Double?,
    val fatMass: Double?,
)

