package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.*
import kotlin.test.*

class NavigationFormRulesTest {
    @Test fun nameTrimsInputButKeepsFallbackExactly() {
        assertEquals("Repère",NavigationFormRules.landmarkName(" Repère ","Type"))
        assertEquals(" Type ",NavigationFormRules.landmarkName("  "," Type "))
    }
    @Test fun partialCoordinatesCountAsMissingAndProximityOnlyRestrictsMissing() {
        fun item(id: String, lat: Double?, lon: Double?) = PlacementCandidate(id,GeoCategory.WATER_POINT,id,
            referenceLatitude=lat,referenceLongitude=lon)
        assertEquals(CoordinateAvailability(3,2,1),NavigationFormRules.coordinates(
            listOf(item("a",null,null),item("b",1.0,null),item("c",null,2.0),item("d",1.0,2.0)),setOf("a","b")))
        assertEquals(CoordinateAvailability(0,0,0),NavigationFormRules.coordinates(emptyList(),emptySet()))
    }
}
