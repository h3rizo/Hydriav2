package mg.hydria.bienetre.core.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ProfileDtoTest {
    @Test
    fun convertsDecimalStringsReturnedByDjango() {
        val profile = ProfileDto(
            id = 4,
            username = "aina",
            heightCm = "168.50",
            weightKg = "62.40",
            activitiesPerWeek = 3,
            averageDurationMinutes = 45,
            fastingMode = "jeune_16_8",
        ).toModel()

        assertEquals(168.5, profile.heightCm ?: 0.0, 0.0)
        assertEquals(62.4, profile.referenceWeightKg ?: 0.0, 0.0)
        assertEquals("jeune_16_8", profile.fastingMode)
    }

    @Test
    fun invalidLegacyDecimalDoesNotCrashProfileScreen() {
        val profile = ProfileDto(id = 5, username = "fara", heightCm = "invalide").toModel()
        assertNull(profile.heightCm)
    }
}

