package mg.hydria.shared.rules.terrain

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals

class TerrainEditRulesTest {
    private fun op(type: String, payload: JSONObject) = JSONObject().put("type", type).put("payload", payload)

    @Test fun versionOmiseSiUneAutreModificationAttend() {
        val empty = JSONArray()
        assertEquals("v1", TerrainEditRules.baseVersion(empty, "point_eau", "p1", "v1"))
        val pending = JSONArray()
            .put(op("terrain_data", JSONObject().put("point_id", "p1").put("telephone", "0341234567")))
            .put(op("terrain_photo", JSONObject().put("equipment_id", "e1").put("photo_data", "x")))
            .put(op("reading", JSONObject().put("point_eau_id", "p1")))
        assertEquals("", TerrainEditRules.baseVersion(pending, "point_eau", "p1", "v1"))
        assertEquals("v2", TerrainEditRules.baseVersion(pending, "point_eau", "p2", "v2"))
        assertEquals(listOf("téléphone"), TerrainEditRules.pendingLabels(pending, "point_eau", "p1"))
        assertEquals(listOf("photo"), TerrainEditRules.pendingLabels(pending, "equipement", "e1"))
    }
}
