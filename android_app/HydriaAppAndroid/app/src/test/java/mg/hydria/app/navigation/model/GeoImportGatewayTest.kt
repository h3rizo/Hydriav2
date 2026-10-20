package mg.hydria.app.navigation.model

import mg.hydria.shared.navigation.GeoImportGateway
import org.json.*
import org.junit.Assert.*
import org.junit.Test

class GeoImportGatewayTest {
    private fun item() = JSONObject().put("id","p").put("latitude",-18.9).put("longitude",47.5)
    @Test fun entityFallbacksAndMarkerCategoryPreserveServerMeaning() {
        val body = item().put("nom"," ").put("name","Point").put("type","").put("type_label","Borne")
            .put("ouvrage_id","").put("coordinates_accuracy",12.0).put("altitude","invalid")
        val value = GeoImportGateway.entity(body,GeoCategory.WATER_POINT,"work")!!
        assertEquals("Point",value.name)
        assertEquals("Borne",value.typeLabel)
        assertEquals("work",value.ouvrageId)
        assertEquals(12.0,value.accuracyMeters!!,0.0)
        assertNull(value.altitude)
        assertFalse(value.isFieldMarker)
        val marker = GeoImportGateway.entity(body.put("marker_category","water_point"),GeoCategory.LANDMARK,"")!!
        assertEquals(GeoCategory.WATER_POINT,marker.category)
        assertTrue(marker.isFieldMarker)
        assertEquals(GeoCategory.LANDMARK,
            GeoImportGateway.entity(body.put("marker_category","unknown"),GeoCategory.LANDMARK,"")!!.category)
    }
    @Test fun invalidCoordinatesRejectMapEntityButRetainPlacementCandidate() {
        val body = item().put("latitude",91.0)
        assertNull(GeoImportGateway.entity(body,GeoCategory.WATER_POINT,""))
        assertEquals(91.0,GeoImportGateway.placement(body,GeoCategory.WATER_POINT,"")!!.referenceLatitude!!,0.0)
        body.remove("latitude")
        body.put("reference_latitude",1.0).put("reference_longitude",2.0)
        assertNull(GeoImportGateway.entity(body,GeoCategory.WATER_POINT,""))
        assertNull(GeoImportGateway.placement(body,GeoCategory.WATER_POINT,"")!!.referenceLatitude)
        body.put("latitude",JSONObject.NULL)
        assertNull(GeoImportGateway.entity(body,GeoCategory.WATER_POINT,""))
    }
    @Test fun absentVillageLinksPreserveWhileExplicitEmptyLinksClear() {
        val body = item()
        fun links() = GeoImportGateway.placement(body,GeoCategory.WATER_POINT,"")!!.servedVillageIds
        assertNull(links())
        body.put("village_ids",JSONArray())
        assertEquals("",links())
        body.put("village_ids",JSONArray().put("a").put("").put("b").put("a")).put("village_id","b")
        assertEquals("a,b",links())
        body.put("village_ids",JSONObject.NULL).put("village_id","")
        assertEquals("",links())
    }
    @Test fun placementDefaultsEmptyIdAndPrecisionFallbackStayCompatible() {
        val body = item().put("id"," ")
        assertNull(GeoImportGateway.placement(body,GeoCategory.EQUIPMENT,"work"))
        body.put("id","e").put("accuracy_m","bad").put("coordinates_accuracy",7.5)
        val placement = GeoImportGateway.placement(body,GeoCategory.EQUIPMENT,"work")!!
        assertEquals("Équipement",placement.name)
        assertEquals("work",placement.ouvrageId)
        assertFalse(placement.hasPhoto)
        assertEquals(7.5,GeoImportGateway.entity(body,GeoCategory.EQUIPMENT,"")!!.accuracyMeters!!,0.0)
        body.put("accuracy_m",3.0).put("name","")
        assertEquals("",GeoImportGateway.entity(body,GeoCategory.EQUIPMENT,"")!!.name)
        assertEquals(3.0,GeoImportGateway.entity(body,GeoCategory.EQUIPMENT,"")!!.accuracyMeters!!,0.0)
    }
}
