package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.*
import kotlin.test.*

class PlacementSelectionTest {
    private fun candidate(id: String, lon: Double? = null, village: String = "", name: String = id) =
        PlacementCandidate(id, GeoCategory.WATER_POINT, name, villageName = village,
            referenceLatitude = lon?.let { 0.0 }, referenceLongitude = lon)

    @Test fun nearbyCoordinatesExcludeDistantPointsAndMissingCoordinates() {
        val result = PlacementSelection.select(listOf(candidate("far", 1.0), candidate("near", 0.1), candidate("missing")),
            0.0, 0.0, true, emptySet())
        assertEquals(listOf("near"), result.candidates.map { it.first.id })
        assertTrue(result.usesNearbyCoordinates)
    }
    @Test fun distantFallbackIsSortedBeforeTheLimitAndPreservesItems() {
        val items = (300 downTo 1).map { candidate("$it", 1.0 + it / 1000.0) }
        val result = PlacementSelection.select(items, 0.0, 0.0, true, emptySet())
        assertEquals(200, result.candidates.size)
        assertEquals("1", result.candidates.first().first.id)
        assertEquals("200", result.candidates.last().first.id)
        assertSame(items.last(), result.candidates.first().first)
        assertFalse(result.usesNearbyCoordinates)
    }
    @Test fun unpositionedPointsMustServeNearbyVillagesAndUseProvidedSortKeys() {
        val items = listOf(candidate("b", village="A", name="Z"), candidate("a", village="a", name="A"),
            candidate("excluded"), candidate("positioned", 0.0))
        val result = PlacementSelection.select(items, 0.0, 0.0, false, setOf("a","b","positioned"))
        assertEquals(listOf("a","b"), result.candidates.map { it.first.id })
        assertTrue(result.candidates.all { it.second == null })
        assertFalse(result.usesNearbyCoordinates)
        assertTrue(PlacementSelection.select(items,0.0,0.0,false,emptySet()).candidates.isEmpty())
    }
    @Test fun partialCoordinatesHaveNoDistance() {
        val partial = candidate("a").copy(referenceLatitude=1.0)
        assertNull(PlacementSelection.distance(partial, 0.0, 0.0))
        assertEquals(listOf(partial), PlacementSelection.select(listOf(partial),0.0,0.0,false,setOf("a")).candidates.map { it.first })
    }
    @Test fun configurationClampsLimitsAndPreservesPermissions() {
        val low = NavigationConfig.fromServerValues(-1.0, -1.0, 0, false, false)
        assertEquals(NavigationConfig(5.0,5.0,1,false,false),low)
        assertEquals(NavigationConfig(200.0,500.0,12),NavigationConfig.fromServerValues(999.0,999.0,999))
        assertEquals(NavigationConfig(),NavigationConfig.fromServerValues())
        assertEquals(GeoCategory.LANDMARK, GeoCategory.fromStorage("unknown"))
        GeoCategory.entries.forEach { assertEquals(it,GeoCategory.fromStorage(it.storageKey)) }
    }
}
