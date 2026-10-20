package mg.hydria.bienetre.core.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DashboardDtoTest {
    @Test
    fun mapsRealDashboardFieldsAndPortionValues() {
        val dto = DashboardDto(
            date = "2026-08-31",
            profile = DashboardProfileDto(objectif = "maintien"),
            metrics = DashboardMetricsDto(
                targetCalories = 2200.0,
                targetProteins = 150.0,
                targetCarbohydrates = 250.0,
                targetFats = 70.0,
            ),
            meals = DashboardMealsDto(
                planned = listOf(
                    DashboardMealDto(3, "dejeuner", "Bol saumon", "mange", 2.0, 840.0),
                ),
                consumedTotals = NutritionTotalsDto(840.0, 72.0, 80.0, 28.0),
            ),
            progress = DashboardProgressDto(
                latestMeasurement = DashboardMeasurementDto("2026-08-30", 72.4, 34.6, 13.2),
                evolution = DashboardEvolutionDto(-0.8),
            ),
        )

        val dashboard = dto.toModel()

        assertEquals(38, dashboard.nutrition.calories.percent)
        assertEquals(840.0, dashboard.meals.single().calories, 0.0)
        assertEquals(72.4, dashboard.latestMeasurement?.weight ?: 0.0, 0.0)
        assertEquals(-0.8, dashboard.weightDelta ?: 0.0, 0.0)
    }

    @Test
    fun ignoresMeasurementWithoutDateInsteadOfInventingOne() {
        val dashboard = DashboardDto(
            date = "2026-08-31",
            progress = DashboardProgressDto(
                latestMeasurement = DashboardMeasurementDto(date = null, poids = 70.0),
            ),
        ).toModel()

        assertNull(dashboard.latestMeasurement)
        assertEquals(0, dashboard.nutrition.overallPercent)
    }
}

