package mg.hydria.app.volume

import mg.hydria.shared.volume.*
import org.json.*
import org.junit.Assert.*
import org.junit.Test

class VolumeMigrationTest {
    private fun invoice(id: String, amount: String) = JSONObject().put("id",id).put("montant",amount)
        .put("version","version").put("ouvrage_id","work").put("ouvrage","Village").put("mois","month")
        .put("idxls",id).put("abonne","Name").put("numero","F-"+id)
    @Test fun decimalTotalsEligibilityAndMatchingAreIdenticalToLegacy() {
        val amounts = listOf("0","0.00","100.10","200.20","1E+30","0.00000000000000001","-15.20","","bad")
        for (first in amounts) for (second in amounts) {
            val rows = listOf(invoice("a",first),invoice("b",second))
            assertEquals(LegacyVolumeWorkflow.total(rows),VolumeWorkflow.total(rows))
            for (row in rows) {
                for (pointed in listOf(false,true)) for(collected in listOf(false,true)) for(validated in listOf(false,true)) {
                    row.put("pointee",pointed).put("encaissee",collected).put("validee",validated)
                    for (actions in listOf(emptySet(),setOf("validate"),setOf("collect"),setOf("point"))) {
                        assertEquals(LegacyVolumeWorkflow.collectable(row,actions),VolumeWorkflow.collectable(row,actions))
                    }
                    assertEquals(LegacyVolumeWorkflow.calculable(row),VolumeWorkflow.calculable(row))
                }
            }
            val entry = JSONObject().put("montant",LegacyVolumeWorkflow.total(rows).toPlainString())
            assertEquals(LegacyVolumeWorkflow.matches(rows,entry),VolumeWorkflow.matches(rows,entry))
            assertEquals(LegacyVolumeWorkflow.matches(rows,entry.put("pointee",true)),VolumeWorkflow.matches(rows,entry))
        }
    }
    @Test fun conflictedAndStatusLabelAreIdenticalToLegacy() {
        val target = invoice("a", "10").put("numero_diamex", "DX-9")
        // File d'attente : une operation en conflit qui cite "a", une sans conflit, une en conflit qui cite "b".
        val pending = listOf(
            JSONObject().put("payload", JSONObject().put("_sync_conflict", JSONObject())
                .put("factures", JSONArray().put(JSONObject().put("id", "a")))),
            JSONObject().put("payload", JSONObject()
                .put("factures", JSONArray().put(JSONObject().put("id", "a")))),
            JSONObject().put("payload", JSONObject().put("_sync_conflict", JSONObject())
                .put("factures", JSONArray().put(JSONObject().put("id", "b")))),
        )
        for (subset in listOf(emptyList<JSONObject>(), pending.take(1), pending.drop(1), pending)) {
            assertEquals(
                LegacyVolumeWorkflow.conflicted(target, subset),
                VolumeWorkflow.conflicted(target, subset),
            )
        }
        for (conflicted in listOf(false, true)) {
            for (pointed in listOf(false, true)) for (collected in listOf(false, true)) for (validated in listOf(false, true)) {
                target.put("pointee", pointed).put("encaissee", collected).put("validee", validated)
                for (actions in listOf(emptySet(), setOf("validate"), setOf("collect"), setOf("point"), setOf("collect", "point"))) {
                    assertEquals(
                        LegacyVolumeWorkflow.statusLabel(target, actions, conflicted),
                        VolumeWorkflow.statusLabel(target, actions, conflicted),
                    )
                }
            }
        }
    }
    @Test fun reconciledEntriesFlagPointedLinesIdenticallyToLegacy() {
        val diamex = JSONArray()
            .put(JSONObject().put("id", "d1").put("numero", "DX-1").put("base", "B1"))
            .put(JSONObject().put("id", "d2").put("numero", "DX-2").put("base", "B2"))
            .put(JSONObject().put("id", "d3").put("numero", "DX-3").put("base", "B3"))
        val pending = listOf(JSONObject().put("payload", JSONObject().put("diamex_id", "d2")))
        val invoices = listOf(
            JSONObject().put("pointee", true).put("numero_diamex", "DX-3").put("base_diamex", "B3"),
            JSONObject().put("pointee", false).put("numero_diamex", "DX-1").put("base_diamex", "B1"),
        )
        val legacy = LegacyVolumeWorkflow.reconciledEntries(diamex, pending, invoices)
        val actual = VolumeWorkflowGateway.reconciledEntries(diamex, pending, invoices)
        assertEquals(legacy.map { it.toString() }, actual.map { it.toString() })
        assertEquals(listOf(false, true, true), actual.map { it.optBoolean("pointee") })
        // le pack d'origine n'est pas muté
        assertFalse(diamex.getJSONObject(1).has("pointee"))
    }
    @Test fun recapMatchesLegacyAndFreezesSelectedInvoiceFields() {
        val row = invoice("a","100.10")
        val other = invoice("b","200.20").put("pointee",true)
        val rows = listOf(row)
        val all = listOf(row,other,other)
        val expected = LegacyVolumeWorkflow.recap(rows,all,"date","journal")
        val actual = VolumeWorkflowGateway.recap(rows,all,"date","journal") { "fixed-time" }
        assertEquals(expected.toString(),actual.toString())
        row.put("montant","999")
        assertEquals("100.10",actual.getJSONArray("factures").getJSONObject(0).getString("montant"))
        assertEquals(1,actual.getJSONArray("idxls_pointes").length())
    }
    @Test fun operationPayloadCopiesExtrasAndFreezesOnlyRequiredInvoiceFields() {
        val row = invoice("a","123.4500")
        val extra = JSONObject().put("action","wrong").put("local_uuid","wrong").put("account_key","wrong")
            .put("custom",JSONObject().put("x",1))
        val payload = VolumeOperationGateway.payload("collect",listOf(row),extra,"uuid","account")
        assertEquals("collect",payload.getString("action"))
        assertEquals("uuid",payload.getString("local_uuid"))
        assertEquals("account",payload.getString("account_key"))
        assertEquals("wrong",extra.getString("action"))
        assertNotSame(extra.getJSONObject("custom"),payload.getJSONObject("custom"))
        val selected = payload.getJSONArray("factures").getJSONObject(0)
        assertEquals(setOf("id","version","montant"),selected.keys().asSequence().toSet())
        row.put("montant","999").put("version","changed")
        assertEquals("123.4500",selected.getString("montant"))
        assertEquals("version",selected.getString("version"))
        assertThrows(JSONException::class.java) {
            VolumeOperationGateway.payload("collect",listOf(JSONObject().put("id","a")),JSONObject(),"uuid","account")
        }
    }
    @Test fun localEntriesPreserveAccountOrderAuditPayloadAndRecapCopy() {
        val payload = JSONObject().put("local_uuid","uuid")
        val recap = JSONObject().put("ouvrage_id","work").put("mois","month")
        val entries = VolumeOperationGateway.localEntries("account","uuid",payload,recap) { "time" }
        assertEquals(listOf("audit:uuid","recap:uuid","last_recap:work:month"),entries.map { it.second })
        assertTrue(entries.all { it.first == "account" })
        assertSame(payload,entries[0].third.getJSONObject("payload"))
        assertEquals("time",entries[0].third.getString("created_at"))
        assertFalse(recap.has("local_uuid"))
        assertEquals("uuid",entries[1].third.getString("local_uuid"))
        assertEquals("uuid",entries[2].third.getString("id"))
        assertEquals(1,VolumeOperationGateway.localEntries("account","uuid",payload,null) { "time" }.size)
    }
}
