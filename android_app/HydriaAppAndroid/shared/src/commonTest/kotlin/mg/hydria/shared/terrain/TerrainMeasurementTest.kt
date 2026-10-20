package mg.hydria.shared.terrain

import kotlin.test.*

class TerrainMeasurementTest {
    @Test fun flowRejectsNegativeVolumeAndNonPositiveDuration() {
        assertFailsWith<IllegalArgumentException> { TerrainMeasurementEngine.flowFromVolume(-1.0, 1.0) }
        assertFailsWith<IllegalArgumentException> { TerrainMeasurementEngine.flowFromVolume(1.0, 0.0) }
        assertEquals(0.5, TerrainMeasurementEngine.flowFromVolume(10.0, 20.0))
    }
    @Test fun trendThresholdsAndNewestValueRemainUnchanged() {
        val cases = mapOf(89.0 to "Baisse inhabituelle à vérifier", 90.0 to "Baisse légère", 98.0 to "Stable",
            102.0 to "Stable", 110.0 to "Hausse légère", 111.0 to "Hausse inhabituelle à vérifier")
        cases.forEach { (current, label) -> assertEquals(label, TerrainMeasurementEngine.trend(current, listOf(100.0, 50.0)).trend) }
        val trend = TerrainMeasurementEngine.trend(120.0, listOf(100.0, 80.0))
        assertEquals(100.0, trend.previous)
        assertEquals(100.0, trend.recentAverage)
        assertEquals(20.0, trend.delta)
        assertNull(TerrainMeasurementEngine.trend(1.0, listOf(0.0)).variationPercent)
    }
    @Test fun headMeterClassificationBoundariesAndReverseGap() {
        for ((downstream, label) in mapOf(96.0 to "Bon", 95.0 to "Acceptable", 90.0 to "À investiguer", 80.0 to "Anormal", 120.0 to "Anormal")) {
            assertEquals(label, TerrainMeasurementEngine.headMeter(0.0, 100.0, downstream, 10).classification)
        }
        assertEquals(10.0, TerrainMeasurementEngine.headMeter(0.0, 100.0, 80.0, 10).dailyAverage)
        assertEquals(100.0, TerrainMeasurementEngine.headMeter(0.0, 100.0, 80.0, 0).dailyAverage)
        assertFailsWith<IllegalArgumentException> { TerrainMeasurementEngine.headMeter(10.0, 9.0, 0.0, 1) }
    }
    @Test fun zeroVolumeKeepsExistingClassification() {
        val result = TerrainMeasurementEngine.headMeter(10.0, 10.0, 3.0, 2)
        assertEquals(0.0, result.gapPercent)
        assertEquals(-3.0, result.gap)
        assertEquals("Bon", result.classification)
    }
}
