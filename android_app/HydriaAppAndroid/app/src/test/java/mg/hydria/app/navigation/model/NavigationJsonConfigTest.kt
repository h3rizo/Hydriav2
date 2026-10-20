package mg.hydria.app.navigation.model

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class NavigationJsonConfigTest {
    @Test fun nestedAndDirectJsonUseSharedLimitsAndPreservePermissions() {
        val value = JSONObject().put("arrival_radius_m", 999).put("accuracy_warning_m", 1)
            .put("max_edge_indicators", 0)
            .put("permissions", JSONObject().put("modify_positions", false).put("create_landmarks", false))
        val expected = NavigationConfig(200.0,5.0,1,false,false)
        assertEquals(expected,NavigationConfig.fromJson(value))
        assertEquals(expected,NavigationConfig.fromJson(JSONObject().put("config",value)))
        assertEquals(NavigationConfig(),NavigationConfig.fromJson(JSONObject()))
    }
}
