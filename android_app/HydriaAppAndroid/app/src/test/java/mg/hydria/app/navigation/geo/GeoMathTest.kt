package mg.hydria.app.navigation.geo

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GeoMathTest {
    @Test fun oneDegreeAtEquatorIsAbout111Km() {
        assertEquals(111_195.0, GeoMath.distanceMeters(0.0, 0.0, 0.0, 1.0), 150.0)
    }

    @Test fun cardinalBearingsAreCorrect() {
        assertEquals(0.0, GeoMath.bearingDegrees(0.0, 0.0, 1.0, 0.0), 0.01)
        assertEquals(90.0, GeoMath.bearingDegrees(0.0, 0.0, 0.0, 1.0), 0.01)
    }

    @Test fun relativeDirectionWrapsAroundNorth() {
        assertEquals(20.0, GeoMath.relativeDirectionDegrees(10.0, 350.0), 0.01)
        assertEquals(-20.0, GeoMath.relativeDirectionDegrees(350.0, 10.0), 0.01)
    }

    @Test fun edgeProjectionHitsExpectedSides() {
        val north = GeoMath.projectBearingToEdge(0.0, 1000f, 600f, 50f)
        val east = GeoMath.projectBearingToEdge(90.0, 1000f, 600f, 50f)
        assertEquals(50f, north.y, 0.1f)
        assertEquals(950f, east.x, 0.1f)
    }

    @Test fun coordinateValidationRejectsInvalidValues() {
        assertTrue(GeoMath.isValid(-18.9, 47.5))
        assertFalse(GeoMath.isValid(91.0, 47.5))
        assertFalse(GeoMath.isValid(-18.9, 181.0))
    }
}

