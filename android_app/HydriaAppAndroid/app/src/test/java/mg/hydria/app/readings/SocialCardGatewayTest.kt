package mg.hydria.app.readings

import mg.hydria.shared.rules.readings.SocialCardGateway
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SocialCardGatewayTest {
    @Test fun replacesStaleVolumeAndSendsOnlyRegisteredCardFields() {
        val card = JSONObject("""{"id":"a","quantite_bidons":10,"volume_total":99,"numero_carte":"123","beneficiaire":"Nom"}""")
        val prepared = SocialCardGateway.prepare(listOf(card), setOf("a"))
        val result = SocialCardGateway.payload(prepared).getJSONObject(0)
        assertEquals(3, result.length())
        assertEquals("a", result.getString("id"))
        assertEquals(10, result.getInt("quantite_bidons"))
        assertEquals(0.2, result.getDouble("volume_total"), 0.000001)
        assertEquals(99.0, card.getDouble("volume_total"), 0.0)
    }
    @Test(expected = IllegalArgumentException::class) fun invalidSelectionCannotBeSerialized() {
        val prepared = SocialCardGateway.prepare(listOf(JSONObject("""{"id":"outside","quantite_bidons":1}""")), setOf("a"))
        SocialCardGateway.payload(prepared)
    }
}
