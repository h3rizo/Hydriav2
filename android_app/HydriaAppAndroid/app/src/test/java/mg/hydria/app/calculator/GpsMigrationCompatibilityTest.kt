package mg.hydria.app.calculator

import org.junit.Assert.*
import org.junit.Test

class GpsMigrationCompatibilityTest {
    @Test fun generatedDmsCoordinatesMatchEveryDecimalAndError() {
        val directions = listOf("N" to "E", "S" to "O", "N" to "W", "s" to "e")
        for ((lat, lon) in directions) for (degree in listOf(0, 1, 18, 89, 90, 91)) for (minute in listOf(0, 30, 59, 60))
            for (seconds in listOf("0", "12,345678901", "59.99999999", "60")) {
                val value = "$lat $degree° $minute' $seconds\" / $lon 47° 30' 25.123456789\""
                assertEquals(value, LegacyGpsConverter.fromDms(value), GpsConverter.fromDms(value))
            }
        for (value in listOf("", "18° 30' 0\" 47° 0' 0\"", "N 18° 0' 0\" N 19° 0' 0\"", "N 18° 0' 0\" E 47° 0' 0\" extra",
            "N 90° 0' 0\" E 180° 0' 0\"", "N 90° 0' 1\" E 180° 0' 0\""))
            assertEquals(value, LegacyGpsConverter.fromDms(value), GpsConverter.fromDms(value))
    }
    @Test fun decimalFormatsBoundsAndRoundingMatchLegacy() {
        val latitudes = listOf("", "0", "-18,123456789", "90", "-90", "90.000000001", "-91", "invalid", "1e2")
        val longitudes = listOf("", "47.123456785", "180", "-180", "180.000000001", "-181", "invalid")
        for (lat in latitudes) for (lon in longitudes) {
            val expected = LegacyGpsConverter.fromDecimal(lat, lon)
            val actual = GpsConverter.fromDecimal(lat, lon)
            assertEquals("$lat / $lon", expected, actual)
            if (expected is mg.hydria.shared.calculator.GpsConversion.Success && actual is mg.hydria.shared.calculator.GpsConversion.Success)
                assertEquals(expected.coordinate.combined, actual.coordinate.combined)
        }
    }
}
