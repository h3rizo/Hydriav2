package mg.hydria.app.navigation.model

import mg.hydria.shared.navigation.GeoOperationPayloads
import org.junit.Assert.*
import org.junit.Test

class GeoOperationPayloadsTest {
    private fun entity() = GeoEntity("e",GeoCategory.WATER_POINT,"Point",latitude=1.0,longitude=2.0,
        serverUpdatedAt="base",isFieldMarker=true)
    private fun captured() = CapturedPosition(3.0,4.0,null,null,"date","carte")
    @Test fun markerPositionUsesLandmarkEndpointButKeepsLocalCategoryAndHistoryId() {
        val value = GeoOperationPayloads.updatePosition(entity(),"history",captured())
        assertEquals("landmark",value.getString("entity_kind"))
        assertEquals("water_point",value.getString("local_category"))
        assertEquals("e",value.getString("entity_id"))
        assertEquals("history",value.getString("local_uuid"))
        assertEquals("base",value.getString("base_updated_at"))
        assertTrue(value.getBoolean("replace_confirmed"))
        assertEquals(3.0,value.getDouble("latitude"),0.0)
        assertEquals(4.0,value.getDouble("longitude"),0.0)
        assertFalse(value.has("altitude"))
        assertFalse(value.has("accuracy_m"))
        assertEquals(setOf("operation_type","local_uuid","entity_kind","local_category","entity_id",
            "latitude","longitude","captured_at","capture_method","base_updated_at","replace_confirmed"),value.keys().asSequence().toSet())
    }
    @Test fun placementKeepsCandidateVersionAndExplicitReplacementFlag() {
        val candidate = PlacementCandidate("candidate",GeoCategory.EQUIPMENT,"Equipment",serverUpdatedAt="candidate-base")
        val value = GeoOperationPayloads.placeCandidate(candidate,"stored","history",
            captured().copy(altitude=12.0,accuracyMeters=7.0),false)
        assertEquals("equipment",value.getString("entity_kind"))
        assertEquals("equipment",value.getString("local_category"))
        assertEquals("stored",value.getString("entity_id"))
        assertEquals("candidate-base",value.getString("base_updated_at"))
        assertFalse(value.getBoolean("replace_confirmed"))
        assertEquals(12.0,value.getDouble("altitude"),0.0)
        assertEquals(7.0,value.getDouble("accuracy_m"),0.0)
    }
    @Test fun creationAndArchiveKeepTheirDistinctIdentifiersAndFields() {
        val created = GeoOperationPayloads.createLandmark(entity(),GeoCategory.EQUIPMENT,"type",captured())
        assertEquals("landmark_upsert",created.getString("operation_type"))
        assertEquals("e",created.getString("local_uuid"))
        assertEquals("equipment",created.getString("marker_category"))
        assertEquals("type",created.getString("type_repere_id"))
        assertEquals("Point",created.getString("nom"))
        assertEquals("date",created.getString("captured_at"))
        assertEquals("carte",created.getString("capture_method"))
        val archived = GeoOperationPayloads.archiveLandmark(entity(),"archive-history")
        assertEquals(setOf("operation_type","id","marker_category","local_uuid"),archived.keys().asSequence().toSet())
        assertEquals("landmark_archive",archived.getString("operation_type"))
        assertEquals("water_point",archived.getString("marker_category"))
        assertEquals("archive-history",archived.getString("local_uuid"))
    }
}
