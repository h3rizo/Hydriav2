package mg.hydria.app.volume

import mg.hydria.shared.volume.*
import org.json.*
import org.junit.Assert.*
import org.junit.Test

class VolumeResultGatewayTest {
    private fun payload() = JSONObject().put("account_key","a").put("local_uuid","id")
        .put("factures",JSONArray().put(JSONObject().put("id","invoice").put("montant","100")))
    private fun response() = JSONObject().put("local_uuid","id")
        .put("factures",JSONArray().put(JSONObject().put("id","invoice").put("montant","200")))
        .put("diamex_temporaire_id","diamex")

    @Test fun acceptanceValidatesBeforeReadingLocalData() {
        var reads = 0
        val read: (String)->JSONObject? = { reads++; null }
        assertThrows(IllegalArgumentException::class.java) {
            VolumeResultGateway.acceptedEntries("other",payload(),JSONObject(),read) { "time" }
        }
        assertEquals(0,reads)
        assertThrows(IllegalArgumentException::class.java) {
            VolumeResultGateway.acceptedEntries("a",payload(),response().put("local_uuid","wrong"),read) { "time" }
        }
        assertEquals(0,reads)
        assertThrows(JSONException::class.java) {
            VolumeResultGateway.acceptedEntries("a",payload(),JSONObject().put("local_uuid","id"),read) { "time" }
        }
        assertEquals(0,reads)
    }
    @Test fun acceptancePreservesServerCacheButReceiptKeepsSubmittedInvoices() {
        val payload = payload()
        val response = response()
        val recap = JSONObject().put("etat","en_attente")
        val audit = JSONObject().put("retained","value")
        val reads = mutableListOf<String>()
        val entries = VolumeResultGateway.acceptedEntries("a",payload,response,
            { key -> reads += key; if(key.startsWith("recap")) recap else audit }) { "time" }
        assertEquals(listOf("recap:id","audit:id"),reads)
        assertEquals(listOf("invoice:invoice","recap:id","receipt:id","audit:id"),entries.map { it.second })
        assertTrue(entries.all { it.first == "a" })
        assertSame(response.getJSONArray("factures").getJSONObject(0),entries[0].third)
        assertEquals("200",entries[0].third.getString("montant"))
        assertEquals("100",entries[2].third.getJSONArray("factures").getJSONObject(0).getString("montant"))
        assertEquals("200",response.getJSONArray("factures").getJSONObject(0).getString("montant"))
        assertSame(recap,entries[1].third)
        assertEquals("synchronisee",recap.getString("etat"))
        assertEquals("diamex",recap.getString("diamex_temporaire_id"))
        assertEquals("value",entries[3].third.getString("retained"))
        assertEquals("time",entries[3].third.getString("updated_at"))
    }
    @Test fun failureKeepsConflictPayloadAndStorageOrder() {
        for (status in listOf(409,500)) {
            val payload = payload()
            val server = response()
            val events = mutableListOf<String>()
            val writes = mutableMapOf<String,JSONObject>()
            VolumeResultGateway.recordFailure("id",payload,status,server,"error",
                { id,value -> assertSame(payload,value); events += "payload:$id" },
                { id,error -> events += "failed:$id:$error" },
                { key -> events += "read:$key"; if(key.startsWith("recap")) JSONObject() else null },
                { key,value -> events += "write:$key"; writes[key]=value })
            val expected = mutableListOf<String>()
            if(status==409) expected += "payload:id"
            expected += listOf("failed:id:error","read:recap:id","write:recap:id","read:audit:id","write:audit:id")
            assertEquals(expected,events)
            assertEquals(status==409,payload.has("_sync_conflict"))
            if(status==409) assertSame(server,payload.getJSONObject("_sync_conflict"))
            assertEquals(if(status==409) "refusee" else "en_attente",writes.getValue("recap:id").getString("etat"))
            assertEquals("refusee",writes.getValue("audit:id").getString("etat"))
            assertSame(payload,writes.getValue("audit:id").getJSONObject("payload"))
        }
    }
    @Test fun failedConflictWriteStopsBeforeOtherQueueChanges() {
        var marked = false
        assertThrows(IllegalStateException::class.java) {
            VolumeResultGateway.recordFailure("id",payload(),409,response(),"error",
                { _, _ -> error("storage") },{ _, _ -> marked=true },{ null },{ _, _ -> })
        }
        assertFalse(marked)
    }
    @Test fun manualReviewRequiresConflictBeforeReadingAndPreparesOnlyAuditAndRecap() {
        assertThrows(IllegalArgumentException::class.java) {
            VolumeResultGateway.reviewedEntries("a","id","review note",payload(),{ error("must not read") }) { "time" }
        }
        val reads = mutableListOf<String>()
        val entries = VolumeResultGateway.reviewedEntries("a","id"," review note ",
            payload().put("_sync_conflict",JSONObject.NULL),
            { key -> reads += key; if(key.startsWith("recap")) JSONObject() else null }) { "time" }
        assertEquals(listOf("audit:id","recap:id"),reads)
        assertEquals(listOf("audit:id","recap:id"),entries.map { it.second })
        entries.forEach {
            assertEquals("verification_manuelle",it.third.getString("etat"))
            assertEquals("review note",it.third.getString("note"))
        }
        assertEquals("time",entries[0].third.getString("updated_at"))
    }
}
