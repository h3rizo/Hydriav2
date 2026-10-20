package mg.hydria.app.navigation.model

import mg.hydria.shared.navigation.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class GeoSyncResultGatewayTest {
    @Test fun markerCategoryDefaultDoesNotReplaceExplicitEmptyCategory() {
        val payload = JSONObject().put("id","m")
        assertEquals("landmark", GeoSyncResultGateway.changes("landmark_upsert",payload,false).single().category)
        payload.put("marker_category","")
        assertEquals("", GeoSyncResultGateway.changes("landmark_upsert",payload,false).single().category)
    }
    @Test fun positionUsesLocalIdentityAndHistoryUuidInsteadOfMarkerId() {
        val payload = JSONObject().put("entity_id","p").put("id","wrong")
            .put("entity_kind","water_point").put("local_category","").put("local_uuid","h")
        assertEquals(listOf(
            GeoSyncChange(GeoSyncChangeKind.ENTITY_SYNCED,"water_point","p"),
            GeoSyncChange(GeoSyncChangeKind.HISTORY_SYNCED,id="h"),
        ),GeoSyncResultGateway.changes("geo_position_upsert",payload,false))
    }
}
