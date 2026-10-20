package mg.hydria.app.navigation.model

import mg.hydria.shared.terrain.TerrainConfirmationGateway
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class TerrainConfirmationGatewayTest {
    @Test fun explicitNullCoordinateStillRequiresConfirmationAndAbsentNameDoesNot() {
        val payload = JSONObject().put("operation_type","update_point")
        val body = JSONObject().put("server_value",JSONObject())
        assertNull(TerrainConfirmationGateway.error("terrain_data",payload,body))
        payload.put("latitude",JSONObject.NULL)
        assertEquals("Le serveur n'a pas confirmé les coordonnées GPS.",
            TerrainConfirmationGateway.error("terrain_data",payload,body))
        body.getJSONObject("server_value").put("has_coordinates",true)
        assertNull(TerrainConfirmationGateway.error("terrain_data",payload,body))
        payload.put("subscriber_name"," Alice ")
        assertEquals("Le serveur n'a pas confirmé le nom de l'abonné.",
            TerrainConfirmationGateway.error("terrain_data",payload,body))
        body.getJSONObject("server_value").put("subscriber_name","Alice")
        assertNull(TerrainConfirmationGateway.error("terrain_data",payload,body))
    }
}
