package mg.hydria.app.calculator

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class SalaryConfigRepositoryTest {
    @Test fun checksumUsesTheSameCanonicalJsonContractAsDjango() {
        val configuration = JSONObject()
            .put("b", "é")
            .put("a", JSONArray().put(true).put(JSONObject.NULL).put("1.00"))
            .put("checksum", "ignored")
            .put("local_synced_at", 123L)
        assertEquals(
            "d95d1b1df55acf97dd0daa500c4561baa18655b7575c61f699374b7165ba8aa7",
            mg.hydria.shared.calculator.SalaryConfigParser.checksumOf(configuration),
        )
    }
}
