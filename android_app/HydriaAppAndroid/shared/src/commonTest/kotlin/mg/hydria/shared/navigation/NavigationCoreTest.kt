package mg.hydria.shared.navigation

import kotlin.test.*

class NavigationCoreTest {
    @Test fun cardinalDirectionsAndNorthWrap() {
        assertEquals(111195.08, GeoMath.distanceMeters(0.0,0.0,0.0,1.0), 0.01)
        assertEquals(90.0, GeoMath.bearingDegrees(0.0,0.0,0.0,1.0), 0.00001)
        assertEquals(20.0, GeoMath.relativeDirectionDegrees(10.0,350.0))
        assertEquals(-180.0, GeoMath.relativeDirectionDegrees(180.0,0.0))
        assertEquals(0.0, GeoMath.distanceMeters(-18.9,47.5,-18.9,47.5))
    }
    @Test fun invalidCoordinatesAndViewportAreRejected() {
        assertFalse(GeoMath.isValid(Double.NaN, 0.0))
        assertFalse(GeoMath.isValid(0.0, Double.POSITIVE_INFINITY))
        assertFailsWith<IllegalArgumentException> { GeoMath.distanceMeters(91.0,0.0,0.0,0.0) }
        assertFailsWith<IllegalArgumentException> { GeoMath.bearingDegrees(0.0,181.0,0.0,0.0) }
        assertFailsWith<IllegalArgumentException> { GeoMath.projectBearingToEdge(0.0,100f,100f,50f) }
    }
    @Test fun destinationsStaySeparateAndNorthDirectionsGroup() {
        val candidates = listOf(
            IndicatorCandidate("a", 10.0, 355.0),
            IndicatorCandidate("b", 20.0, 5.0),
            IndicatorCandidate("target", 100.0, 0.0, true),
            IndicatorCandidate("c", 30.0, 16.0),
        )
        assertEquals(listOf(listOf("target"),listOf("a","b"),listOf("c")),
            EdgeIndicatorEngine.groupByDirection(candidates).map { it.map { it.entity } })
        assertEquals(listOf("target"), EdgeIndicatorEngine.prioritize(candidates, 0).map { it.entity })
        assertTrue(EdgeIndicatorEngine.groupByDirection(emptyList<IndicatorCandidate<String>>()).isEmpty())
    }
    @Test fun projectionHitsAllFourEdges() {
        assertEquals(50f, GeoMath.projectBearingToEdge(0.0,1000f,600f,50f).y, 0.001f)
        assertEquals(950f, GeoMath.projectBearingToEdge(90.0,1000f,600f,50f).x, 0.001f)
        assertEquals(550f, GeoMath.projectBearingToEdge(180.0,1000f,600f,50f).y, 0.001f)
        assertEquals(50f, GeoMath.projectBearingToEdge(270.0,1000f,600f,50f).x, 0.001f)
    }
}
