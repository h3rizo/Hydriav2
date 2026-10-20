package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.*
import kotlin.test.*

class IndicatorSelectionTest {
    private fun entity(id: String, lon: Double, category: GeoCategory = GeoCategory.WATER_POINT) =
        GeoEntity(id,category,id,latitude=0.0,longitude=lon)

    @Test fun visibleEdgesAreInclusiveAndHiddenCategoriesAreNeverProjected() {
        val items = listOf(entity("inside",1.0),entity("edge",2.0),
            entity("outside",3.0),entity("hidden",4.0,GeoCategory.LANDMARK))
        val projected = mutableListOf<String>()
        val result = IndicatorSelection.select(items,setOf(GeoCategory.WATER_POINT),0.0,0.0,0.0,null,100f,100f,6) {
            projected += it.id
            when(it.id) {
                "inside" -> ScreenPoint(50f,50f)
                "edge" -> ScreenPoint(100f,0f)
                else -> ScreenPoint(101f,50f)
            }
        }
        assertEquals(listOf("inside","edge","outside"),projected)
        assertEquals(listOf("outside"),result.map { it.entity.id })
    }
    @Test fun destinationHasPriorityBeforeLimitAndBearingUsesCamera() {
        val near = entity("near",0.001)
        val target = entity("target",1.0)
        val result = IndicatorSelection.select(listOf(near,target),GeoCategory.entries.toSet(),
            0.0,0.0,350.0,"target",100f,100f,1) { ScreenPoint(-1f,0f) }
        assertSame(target,result.single().entity)
        assertTrue(result.single().isDestination)
        assertEquals(100.0,result.single().relativeBearingDegrees,0.000001)
    }
    @Test fun onscreenDestinationIsExcludedAndEqualDistancesKeepInputOrder() {
        val items = listOf(entity("b",1.0),entity("a",1.0),entity("target",2.0))
        val result = IndicatorSelection.select(items,GeoCategory.entries.toSet(),0.0,0.0,0.0,"target",100f,100f,6) {
            if (it.id == "target") ScreenPoint(50f,50f) else ScreenPoint(0f,-1f)
        }
        assertEquals(listOf("b","a"),result.map { it.entity.id })
    }
    @Test fun nearestTouchPreservesIdentityAndStrictRadiusBoundary() {
        val first = ScreenPoint(3f,4f)
        val second = ScreenPoint(-3f,-4f)
        assertNull(IndicatorSelection.nearestHit(listOf(first,second),0f,0f,5f) { it })
        assertSame(first,IndicatorSelection.nearestHit(listOf(first,second),0f,0f,5.01f) { it })
        assertSame(second,IndicatorSelection.nearestHit(listOf(first,second),-3f,-4f,1f) { it })
        assertNull(IndicatorSelection.nearestHit(emptyList<ScreenPoint>(),0f,0f,54f) { it })
    }
}
