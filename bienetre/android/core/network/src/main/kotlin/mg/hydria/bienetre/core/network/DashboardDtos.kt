package mg.hydria.bienetre.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import mg.hydria.bienetre.core.model.Dashboard
import mg.hydria.bienetre.core.model.DashboardMeal
import mg.hydria.bienetre.core.model.DashboardMeasurement
import mg.hydria.bienetre.core.model.DashboardShoppingItem
import mg.hydria.bienetre.core.model.DashboardWorkout
import mg.hydria.bienetre.core.model.NutrientProgress
import mg.hydria.bienetre.core.model.NutritionProgress

@Serializable
data class DashboardDto(
    val date: String,
    val profile: DashboardProfileDto = DashboardProfileDto(),
    val metrics: DashboardMetricsDto = DashboardMetricsDto(),
    val meals: DashboardMealsDto = DashboardMealsDto(),
    val fitness: DashboardFitnessDto = DashboardFitnessDto(),
    val progress: DashboardProgressDto = DashboardProgressDto(),
    val shopping: List<DashboardShoppingListDto> = emptyList(),
    val suggestions: List<String> = emptyList(),
)

@Serializable
data class DashboardProfileDto(val objectif: String? = null)

@Serializable
data class DashboardMetricsDto(
    @SerialName("objectif_calories") val targetCalories: Double? = null,
    @SerialName("objectif_proteines_g") val targetProteins: Double? = null,
    @SerialName("objectif_glucides_g") val targetCarbohydrates: Double? = null,
    @SerialName("objectif_lipides_g") val targetFats: Double? = null,
    val message: String? = null,
    @SerialName("missing_fields") val missingFields: List<String> = emptyList(),
)

@Serializable
data class DashboardMealsDto(
    val planned: List<DashboardMealDto> = emptyList(),
    @SerialName("consumed_totals") val consumedTotals: NutritionTotalsDto = NutritionTotalsDto(),
)

@Serializable
data class NutritionTotalsDto(
    val calories: Double = 0.0,
    @SerialName("proteines_g") val proteins: Double = 0.0,
    @SerialName("glucides_g") val carbohydrates: Double = 0.0,
    @SerialName("lipides_g") val fats: Double = 0.0,
)

@Serializable
data class DashboardMealDto(
    val id: Long,
    val repas: String,
    @SerialName("recipe_nom") val recipeName: String,
    val statut: String,
    @SerialName("nombre_portions") val portions: Double,
    val calories: Double,
)

@Serializable
data class DashboardFitnessDto(
    @SerialName("planned_workout") val plannedWorkout: List<DashboardWorkoutDto> = emptyList(),
)

@Serializable
data class DashboardWorkoutDto(
    val id: Long,
    val exercise: String,
    val series: Int,
    val repetitions: Int? = null,
    @SerialName("duree_secondes") val durationSeconds: Int? = null,
    val termine: Boolean = false,
)

@Serializable
data class DashboardProgressDto(
    @SerialName("latest_measurement") val latestMeasurement: DashboardMeasurementDto? = null,
    val evolution: DashboardEvolutionDto = DashboardEvolutionDto(),
)

@Serializable
data class DashboardMeasurementDto(
    val date: String? = null,
    val poids: Double? = null,
    @SerialName("masse_musculaire_kg") val muscleMass: Double? = null,
    @SerialName("masse_graisseuse_kg") val fatMass: Double? = null,
)

@Serializable
data class DashboardEvolutionDto(@SerialName("poids_delta") val weightDelta: Double? = null)

@Serializable
data class DashboardShoppingListDto(val items: List<DashboardShoppingItemDto> = emptyList())

@Serializable
data class DashboardShoppingItemDto(
    val id: Long,
    @SerialName("ingredient_nom") val name: String,
    @SerialName("ingredient_icone") val icon: String? = null,
    @SerialName("quantite_totale") val quantity: Double,
    val unite: String,
    val checked: Boolean,
)

fun DashboardDto.toModel(): Dashboard {
    val totals = meals.consumedTotals
    val measurement = progress.latestMeasurement?.takeIf { it.date != null }?.let {
        DashboardMeasurement(
            date = requireNotNull(it.date),
            weight = it.poids,
            muscleMass = it.muscleMass,
            fatMass = it.fatMass,
        )
    }
    return Dashboard(
        date = date,
        objective = profile.objectif,
        metricsMessage = metrics.message,
        missingProfileFields = metrics.missingFields,
        nutrition = NutritionProgress(
            calories = NutrientProgress(totals.calories, metrics.targetCalories),
            proteins = NutrientProgress(totals.proteins, metrics.targetProteins),
            carbohydrates = NutrientProgress(totals.carbohydrates, metrics.targetCarbohydrates),
            fats = NutrientProgress(totals.fats, metrics.targetFats),
        ),
        meals = meals.planned.map {
            DashboardMeal(it.id, it.repas, it.recipeName, it.statut, it.portions, it.calories)
        },
        workouts = fitness.plannedWorkout.map {
            DashboardWorkout(it.id, it.exercise, it.series, it.repetitions, it.durationSeconds, it.termine)
        },
        shoppingItems = shopping.flatMap { it.items }.distinctBy { it.id }.map {
            DashboardShoppingItem(it.id, it.name, it.icon, it.quantity, it.unite, it.checked)
        },
        latestMeasurement = measurement,
        weightDelta = progress.evolution.weightDelta,
        suggestions = suggestions,
    )
}

