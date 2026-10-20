package mg.hydria.app.navigation.geo

import mg.hydria.app.navigation.model.GeoCategory
import mg.hydria.app.navigation.model.GeoEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class EdgeIndicatorEngineTest {
    private fun candidate(id: String, distance: Double, bearing: Double, destination: Boolean = false) =
        IndicatorCandidate(GeoEntity(id, GeoCategory.LANDMARK, id, latitude = 0.0, longitude = 0.0), distance, bearing, destination)

    @Test fun destinationAlwaysComesFirst() {
        val result = EdgeIndicatorEngine.prioritize(listOf(candidate("near", 10.0, 0.0), candidate("target", 500.0, 90.0, true)), 2)
        assertEquals("target", result.first().entity.id)
    }

    @Test fun resultIsLimitedAndNearestFirst() {
        val result = EdgeIndicatorEngine.prioritize((1..10).map { candidate("$it", it.toDouble(), it * 20.0) }, 6)
        assertEquals(6, result.size)
        assertEquals("1", result.first().entity.id)
    }

    @Test fun closeDirectionsAreGroupedButDestinationStaysAlone() {
        val groups = EdgeIndicatorEngine.groupByDirection(
            listOf(candidate("a", 20.0, 10.0), candidate("b", 30.0, 17.0), candidate("target", 100.0, 15.0, true))
        )
        assertEquals(2, groups.size)
        assertTrue(groups.any { it.size == 2 })
        assertTrue(groups.any { it.singleOrNull()?.isDestination == true })
    }
}

