package mg.hydria.app.navigation.model

import mg.hydria.shared.navigation.GeoLocalGateway
import org.json.*
import org.junit.Assert.*
import org.junit.Test

class GeoLocalGatewayTest {
    private fun row() = JSONObject().put("entity_id","p").put("name","Point").put("category","water_point")
        .put("latitude",-18.9).put("longitude",47.5)
    @Test fun localStateAndIdentitySurviveDecoding() {
        val value = GeoLocalGateway.entity(row().put("id","wrong").put("nom","Wrong")
            .put("sync_state","conflict").put("server_updated_at","version")
            .put("is_field_marker",true).put("altitude",123.0).put("accuracy_m",8.0))
        assertEquals("p",value.id)
        assertEquals("Point",value.name)
        assertEquals("conflict",value.syncState)
        assertEquals("version",value.serverUpdatedAt)
        assertTrue(value.isFieldMarker)
        assertEquals(123.0,value.altitude!!,0.0)
        assertEquals(8.0,value.accuracyMeters!!,0.0)
    }
    @Test fun optionalInvalidNumbersAndUnknownCategoryKeepFallbacks() {
        val value = GeoLocalGateway.entity(row().put("altitude","NaN").put("accuracy_m","Infinity")
            .put("category","unknown"))
        assertNull(value.altitude)
        assertNull(value.accuracyMeters)
        assertEquals(GeoCategory.LANDMARK,value.category)
        assertEquals("synced",value.syncState)
        assertFalse(value.isFieldMarker)
        assertEquals("",value.code)
        assertNull(GeoLocalGateway.entity(row().put("altitude",JSONObject.NULL)).altitude)
    }
    @Test fun placementUsesStoredReferenceCoordinatesAndPreservesVillageIds() {
        val value = GeoLocalGateway.placement(row().put("reference_latitude",-18.8)
            .put("reference_longitude","bad").put("served_village_ids","a,, ,b,a, c ")
            .put("has_photo",true).put("ouvrage_id","w"),GeoCategory.EQUIPMENT)
        assertEquals(GeoCategory.EQUIPMENT,value.category)
        assertEquals(-18.8,value.referenceLatitude!!,0.0)
        assertNull(value.referenceLongitude)
        assertEquals(setOf("a","b"," c "),value.servedVillageIds)
        assertTrue(value.hasPhoto)
        assertEquals("w",value.ouvrageId)
        assertNull(GeoLocalGateway.placement(row(),GeoCategory.WATER_POINT).referenceLatitude)
    }
    @Test fun requiredLocalFieldsStillRejectCorruptRows() {
        for (key in listOf("entity_id","name","category","latitude","longitude")) {
            val body = row().apply { remove(key) }
            assertThrows(JSONException::class.java) { GeoLocalGateway.entity(body) }
        }
        for (key in listOf("entity_id","name")) {
            val body = row().apply { remove(key) }
            assertThrows(JSONException::class.java) { GeoLocalGateway.placement(body,GeoCategory.WATER_POINT) }
        }
    }
}
