package mg.hydria.app.volume

import mg.hydria.shared.volume.VolumeCacheGateway
import org.json.*
import org.junit.Assert.*
import org.junit.Test

class VolumeCacheGatewayTest {
    @Test fun packStoresInvoicesSeparatelyAndMetadataContainsOnlyReferences() {
        val invoice = JSONObject().put("id","i").put("montant","100")
        val pack = JSONObject().put("ouvrage_id","w").put("mois","m").put("factures",JSONArray().put(invoice))
        val entries = VolumeCacheGateway.packEntries("account",pack)
        assertEquals(listOf("invoice:i","pack:w:m"),entries.map { it.second })
        assertTrue(entries.all { it.first == "account" })
        assertSame(invoice,entries[0].third)
        val reference = entries[1].third.getJSONArray("factures").getJSONObject(0)
        assertEquals(setOf("id"),reference.keys().asSequence().toSet())
        assertEquals("100",pack.getJSONArray("factures").getJSONObject(0).getString("montant"))
        assertNotSame(pack,entries[1].third)
    }
    @Test fun cachedInvoiceOverridesFallbackAndNumericSortPrecedesName() {
        fun invoice(id: String, index: String, name: String) =
            JSONObject().put("id",id).put("idxls",index).put("abonne",name)
        val original = invoice("a","1","A")
        val cached = invoice("a","10","A")
        val second = invoice("b","2","B")
        val invalid = invoice("c","bad","C")
        val overflow = invoice("d","999999999999999999999","D")
        val pack = JSONObject().put("factures",JSONArray().put(original).put(second).put(overflow).put(invalid))
        val result = VolumeCacheGateway.invoices(pack) { if(it=="invoice:a") cached else null }
        assertEquals(listOf("b","a","c","d"),result.map { it.getString("id") })
        assertSame(cached,result[1])
        assertSame(second,result[0])
    }
    @Test fun pendingOperationsStayAccountScopedAndActionsAreDistinct() {
        fun operation(account: String, action: String, id: String) = JSONObject().put("type","volume")
            .put("payload",JSONObject().put("account_key",account).put("action",action)
                .put("factures",JSONArray().put(JSONObject().put("id",id))))
        val first = operation("a","collect","i")
        val rows = JSONArray().put(JSONObject().put("type","reading")).put(first)
            .put(operation("b","point","i")).put(operation("a","collect","i"))
            .put(operation("a","point","other"))
        val pending = VolumeCacheGateway.pending(rows,"a")
        assertEquals(3,pending.size)
        assertSame(first,pending.first())
        assertEquals(setOf("collect"),VolumeCacheGateway.actions("i",pending))
        assertEquals(setOf("point"),VolumeCacheGateway.actions("other",pending))
        assertTrue(VolumeCacheGateway.actions("missing",pending).isEmpty())
        assertThrows(JSONException::class.java) { VolumeCacheGateway.pending(JSONArray().put("bad"),"a") }
    }
    @Test fun printOrderIsNumericByIdxlsIgnoringParcelle() {
        fun row(id: String, abonne: String, idxls: String, parcelle: String) =
            JSONObject().put("id", id).put("abonne", abonne).put("idxls", idxls).put("parcelle", parcelle)
        val rows = listOf(row("i10", "Andry", "10", "P01"), row("i2", "Zafy", "2", "P09"),
            row("sans", "Bako", "", "P01"), row("i9", "élise", "9", "P01"), row("i1", "Rabe", "1", "P05"))
        assertEquals(listOf("i1", "i2", "i9", "i10", "sans"), VolumeCacheGateway.printOrder(rows).map { it.getString("id") })
    }
}
