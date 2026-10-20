package mg.hydria.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TerrainMeasurementEngineTest {
    @Test(expected = IllegalArgumentException::class)
    fun divisionByZeroIsRejected() {
        TerrainMeasurementEngine.flowFromVolume(10.0, 0.0)
    }

    @Test
    fun firstFlowMeasurementHasNoVariation() {
        val result = TerrainMeasurementEngine.trend(0.31, emptyList())
        assertNull(result.previous)
        assertNull(result.variationPercent)
        assertEquals("Première mesure", result.trend)
    }

    @Test
    fun flowFromVolumeAndTimeIsCalculated() {
        assertEquals(0.5, TerrainMeasurementEngine.flowFromVolume(10.0, 20.0), 0.0001)
    }

    @Test
    fun headMeterThresholdsMatchOperationalRules() {
        assertEquals("Bon", TerrainMeasurementEngine.headMeter(0.0, 100.0, 96.0, 10).classification)
        assertEquals("Acceptable", TerrainMeasurementEngine.headMeter(0.0, 100.0, 92.0, 10).classification)
        assertEquals("À investiguer", TerrainMeasurementEngine.headMeter(0.0, 100.0, 85.0, 10).classification)
        assertEquals("Anormal", TerrainMeasurementEngine.headMeter(0.0, 100.0, 75.0, 10).classification)
    }
}
