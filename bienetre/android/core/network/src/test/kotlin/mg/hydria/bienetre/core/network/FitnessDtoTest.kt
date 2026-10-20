package mg.hydria.bienetre.core.network

import org.junit.Assert.assertEquals
import org.junit.Test

class FitnessDtoTest {
    @Test
    fun mapsExercisePrescriptionAndSuggestedWeight() {
        val item = WorkoutPlanItemDto(
            id = 5,
            exerciseId = 2,
            exerciseName = "Squat",
            sets = 4,
            repetitions = 10,
            restSeconds = 90,
            targetWeight = "42.50",
            suggestedWeight = "44.50",
            progressionHint = "Progression légère",
        ).toModel()

        assertEquals(4, item.sets)
        assertEquals(44.5, item.suggestedWeightKg ?: 0.0, 0.0)
        assertEquals("Progression légère", item.progressionHint)
    }

    @Test
    fun mapsServerSessionTimestampForTimerRecovery() {
        val session = WorkoutDaySessionDto(
            id = 7,
            date = "2026-08-31",
            startedAt = "2026-08-31T08:00:00Z",
            active = true,
            totalDuration = 120,
        ).toModel()

        assertEquals("2026-08-31T08:00:00Z", session.startedAt)
        assertEquals(true, session.active)
    }
}
