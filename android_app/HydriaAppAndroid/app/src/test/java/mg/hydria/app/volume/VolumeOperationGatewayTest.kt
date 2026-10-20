package mg.hydria.app.volume

import mg.hydria.shared.volume.VolumeOperationGateway
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

/** CALC_VOL-02 : libellé « ouvrage · mois · montant » qui préfixe les erreurs de synchronisation. */
class VolumeOperationGatewayTest {
    private fun payload(vararg rows: Pair<String, String>) = JSONObject().put("local_uuid", "op")
        .put("factures", JSONArray().apply {
            rows.forEach { (id, amount) -> put(JSONObject().put("id", id).put("montant", amount)) }
        })

    @Test fun describeNamesWorkMonthAndTotalAmount() {
        val cache = mapOf("invoice:f1" to JSONObject().put("ouvrage", "Ambanja BP").put("mois", "2026-09"))
        assertEquals("Ambanja BP · 2026-09 · 127500.5 Ar",
            VolumeOperationGateway.describe(payload("f1" to "125000.00", "f2" to "2500.50"), cache::get))
    }

    @Test fun describeDropsPlainTrailingZerosOfAWholeAmount() {
        val cache = mapOf("invoice:f1" to JSONObject().put("ouvrage", "Sahavato").put("mois", "2026-08"))
        assertEquals("Sahavato · 2026-08 · 100 Ar", VolumeOperationGateway.describe(payload("f1" to "100.00"), cache::get))
    }

    @Test fun describeOmitsWhatTheLocalCacheDoesNotKnow() {
        assertEquals("1500 Ar", VolumeOperationGateway.describe(payload("absent" to "1500"), { null }))
        assertEquals("0 Ar", VolumeOperationGateway.describe(JSONObject().put("local_uuid", "op"), { null }))
    }
}
