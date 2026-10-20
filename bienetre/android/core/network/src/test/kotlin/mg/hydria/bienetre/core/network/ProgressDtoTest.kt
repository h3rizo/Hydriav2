package mg.hydria.bienetre.core.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ProgressDtoTest {
    @Test
    fun mapsNullableBodyCompositionWithoutInventingValues() {
        val value = BodyMeasurementDto(
            id = 4,
            date = "2026-08-31",
            weightKg = "68.40",
            muscleMassKg = null,
            fatMassKg = "14.20",
        ).toModel()

        assertEquals(68.4, value.weightKg ?: 0.0, 0.0)
        assertNull(value.muscleMassKg)
        assertEquals(14.2, value.fatMassKg ?: 0.0, 0.0)
    }

    @Test
    fun mapsOnlyPrivatePhotoContentEndpoint() {
        val value = ProgressPhotoDto(7, "2026-08-31", "Départ", "/api/v1/progress/photos/7/content/", "now").toModel()

        assertEquals(7, value.id)
        assertEquals("/api/v1/progress/photos/7/content/", value.imageUrl)
        assertEquals("Départ", value.note)
    }
}
