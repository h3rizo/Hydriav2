package mg.hydria.app.calculator

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GpsConverterTest {
    @Test fun exampleDmsConvertsToExpectedCoordinates() {
        val result = GpsConverter.fromDms("S 17°01'19,4\" E049°28'45,5\"") as mg.hydria.shared.calculator.GpsConversion.Success
        assertEquals("-17.02205556, 49.47930556", result.coordinate.combined)
    }

    @Test fun orientationsAndInputOrderAreSupported() {
        val westFirst = GpsConverter.fromDms("w 10°30'00\" n 20°15'00\"") as mg.hydria.shared.calculator.GpsConversion.Success
        assertEquals("20.25000000, -10.50000000", westFirst.coordinate.combined)
        val east = GpsConverter.fromDms("N 0°00'00\" O 0°00'00\"") as mg.hydria.shared.calculator.GpsConversion.Success
        assertEquals("0.00000000, 0.00000000", east.coordinate.combined)
    }

    @Test fun decimalPointCommaAndRangesAreValidated() {
        assertEquals("-17.50000000, 49.25000000", (GpsConverter.fromDecimal(" -17,5 ", "49.25") as mg.hydria.shared.calculator.GpsConversion.Success).coordinate.combined)
        invalidDecimal("91", "0", GpsError.LATITUDE_RANGE)
        invalidDecimal("0", "181", GpsError.LONGITUDE_RANGE)
    }

    @Test fun dmsMinutesSecondsPolesDuplicatesAndOrientationAreValidated() {
        invalidDms("N 10°60'00\" E 20°00'00\"", GpsError.INVALID_MINUTES)
        invalidDms("N 10°00'60\" E 20°00'00\"", GpsError.INVALID_SECONDS)
        invalidDms("N 90°00'01\" E 20°00'00\"", GpsError.LATITUDE_RANGE)
        invalidDms("N 10°00'00\" E 180°00'01\"", GpsError.LONGITUDE_RANGE)
        invalidDms("N 10°00'00\" S 11°00'00\" E 20°00'00\"", GpsError.DUPLICATE_COORDINATE)
        invalidDms("10°00'00\" 20°00'00\"", GpsError.ORIENTATION_MISSING)
    }

    private fun invalidDms(value: String, error: GpsError) {
        val result = GpsConverter.fromDms(value)
        assertTrue(result is mg.hydria.shared.calculator.GpsConversion.Invalid)
        assertEquals(error, (result as mg.hydria.shared.calculator.GpsConversion.Invalid).error)
    }

    private fun invalidDecimal(latitude: String, longitude: String, error: GpsError) {
        val result = GpsConverter.fromDecimal(latitude, longitude)
        assertTrue(result is mg.hydria.shared.calculator.GpsConversion.Invalid)
        assertEquals(error, (result as mg.hydria.shared.calculator.GpsConversion.Invalid).error)
    }
}
