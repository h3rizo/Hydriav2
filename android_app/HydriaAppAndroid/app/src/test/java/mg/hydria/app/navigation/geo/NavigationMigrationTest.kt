package mg.hydria.app.navigation.geo

import mg.hydria.app.navigation.model.*
import org.junit.Assert.*
import org.junit.Test
import kotlin.random.Random

class NavigationMigrationTest {
    @Test fun coordinatesMatchLegacyAcrossTheGlobe() {
        val random = Random(812)
        repeat(2000) {
            val a = random.nextDouble(-89.0, 89.0)
            val b = random.nextDouble(-180.0, 180.0)
            val c = random.nextDouble(-89.0, 89.0)
            val d = random.nextDouble(-180.0, 180.0)
            assertEquals(LegacyGeoMath.distanceMeters(a,b,c,d), GeoMath.distanceMeters(a,b,c,d), 0.000001)
            assertEquals(LegacyGeoMath.bearingDegrees(a,b,c,d), GeoMath.bearingDegrees(a,b,c,d), 0.000000001)
        }
    }
    @Test fun projectionAndDistanceLabelsMatchLegacy() {
        for (angle in -720..720) {
            val before = LegacyGeoMath.projectBearingToEdge(angle.toDouble(), 1080f, 1920f, 48f)
            val after = GeoMath.projectBearingToEdge(angle.toDouble(), 1080f, 1920f, 48f)
            assertEquals(before.x, after.x, 0.001f)
            assertEquals(before.y, after.y, 0.001f)
            assertEquals(before.rotationDegrees, after.rotationDegrees, 0f)
        }
        listOf(0.0, 999.4, 999.9, 1000.0, 1050.0, 12500.0).forEach {
            assertEquals(LegacyGeoMath.formatDistance(it), GeoMath.formatDistance(it))
        }
    }
    @Test fun groupingAndPriorityPreserveOrderAndOriginalCandidates() {
        val random = Random(92)
        repeat(100) {
            val candidates = List(40) { index ->
                IndicatorCandidate(GeoEntity("$index", GeoCategory.LANDMARK, "$index", latitude=0.0, longitude=0.0),
                    random.nextInt(10).toDouble(), random.nextDouble(-360.0, 720.0), index % 13 == 0)
            }
            for (limit in listOf(-1, 0, 1, 6, 100)) {
                val result = EdgeIndicatorEngine.prioritize(candidates, limit)
                assertEquals(LegacyEdgeIndicatorEngine.prioritize(candidates, limit), result)
                result.forEach { assertTrue(candidates.any { original -> original === it }) }
            }
            for (threshold in listOf(-1.0, 0.0, 12.0, 180.0)) {
                assertEquals(LegacyEdgeIndicatorEngine.groupByDirection(candidates, threshold),
                    EdgeIndicatorEngine.groupByDirection(candidates, threshold))
            }
        }
    }
}
