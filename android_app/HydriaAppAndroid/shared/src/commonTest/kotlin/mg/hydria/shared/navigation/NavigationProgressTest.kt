package mg.hydria.shared.navigation

import kotlin.test.*

class NavigationProgressTest {
    @Test fun smoothingTakesShortestPathAcrossNorthInBothDirections() {
        val clockwise = HeadingSmoother()
        assertEquals(350.0, clockwise.update(350.0))
        assertEquals(354.0, clockwise.update(10.0))
        assertEquals(357.2, clockwise.update(10.0), 0.000001)
        val counterclockwise = HeadingSmoother()
        assertEquals(10.0,counterclockwise.update(370.0))
        assertEquals(6.0,counterclockwise.update(-10.0))
    }
    @Test fun smoothingPreservesLegacySequence() {
        val smoother = HeadingSmoother()
        var previous: Double? = null
        for (angle in -720..720) {
            val raw = GeoMath.normalize360(angle.toDouble())
            val old = previous
            val expected = if (old == null) raw else
                GeoMath.normalize360(old + GeoMath.relativeDirectionDegrees(raw,old) * 0.2)
            assertEquals(expected,smoother.update(angle.toDouble()))
            previous = expected
        }
    }
    @Test fun freshnessIncludesExactlyTwoMinutesAndFutureTimestamps() {
        assertTrue(NavigationProgressRules.acceptsLocation(200_000,80_000))
        assertFalse(NavigationProgressRules.acceptsLocation(200_000,79_999))
        assertTrue(NavigationProgressRules.acceptsLocation(200_000,200_001))
    }
    @Test fun etaRequiresSpeedStrictlyAboveThreshold() {
        fun progress(speed: Float?) = NavigationProgressRules.calculate(0.0,0.0,0.0,0.001,0.0,speed,25.0)
        assertNull(progress(null).estimatedMinutes)
        assertNull(progress(0.8f).estimatedMinutes)
        assertNull(progress(-1f).estimatedMinutes)
        assertEquals(3,progress(0.81f).estimatedMinutes)
        assertEquals(2,progress(1f).estimatedMinutes)
        assertEquals(90.0,progress(1f).relativeDirectionDegrees,0.000001)
        assertFalse(progress(1f).hasArrived)
    }
    @Test fun arrivalIncludesExactRadiusAndZeroDistance() {
        val distance = GeoMath.distanceMeters(0.0,0.0,0.0,0.001)
        assertTrue(NavigationProgressRules.calculate(0.0,0.0,0.0,0.001,350.0,1f,distance).hasArrived)
        assertFalse(NavigationProgressRules.calculate(0.0,0.0,0.0,0.001,350.0,1f,distance-0.001).hasArrived)
        val zero = NavigationProgressRules.calculate(0.0,0.0,0.0,0.0,0.0,1f,0.0)
        assertTrue(zero.hasArrived)
        assertEquals(0,zero.estimatedMinutes)
    }
}
