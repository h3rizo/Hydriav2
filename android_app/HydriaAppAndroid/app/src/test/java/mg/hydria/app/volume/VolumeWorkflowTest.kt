package mg.hydria.app.volume

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.math.BigDecimal

class VolumeWorkflowTest {
    private fun invoice(id: String, amount: String = "100.10") = JSONObject()
        .put("id", id).put("montant", amount).put("ouvrage_id", "w").put("ouvrage", "Village")
        .put("mois", "2026-09").put("validee", true).put("abonne", "Abonné $id").put("idxls", id)

    @Test fun collectionShowsAllUnpointedButBlocksAlreadyCollected() {
        val due = invoice("1")
        val collected = invoice("2").put("encaissee", true)
        val pointed = invoice("3").put("pointee", true)
        assertEquals(2, VolumeWorkflow.unpointed(listOf(due, collected, pointed)).size)
        assertTrue(VolumeWorkflow.collectable(due, emptySet()))
        assertFalse(VolumeWorkflow.collectable(collected, emptySet()))
        assertFalse(VolumeWorkflow.collectable(due, setOf("collect")))
        assertFalse(VolumeWorkflow.collectable(pointed, emptySet()))
    }
    @Test fun pointRequiresExactSelectedSumAndAvailableEntry() {
        val rows = listOf(invoice("1"), invoice("2", "200.20"))
        val entry = JSONObject().put("montant", "300.30")
        assertTrue(VolumeWorkflow.matches(rows, entry))
        assertFalse(VolumeWorkflow.matches(rows.take(1), entry))
        assertFalse(VolumeWorkflow.matches(rows, entry.put("pointee", true)))
        assertFalse(VolumeWorkflow.matches(rows, null))
    }
    @Test fun recapFreezesInvoicesAndPointedGrid() {
        val first = invoice("15")
        val second = invoice("19").put("pointee", true)
        val recap = VolumeWorkflow.recap(listOf(first), listOf(first, second), "2026-09-06", "00PERS")
        first.put("montant", "9000")
        assertEquals("100.10", recap.getString("total"))
        assertEquals("100.10", recap.getJSONArray("factures").getJSONObject(0).getString("montant"))
        assertEquals("19", recap.getJSONArray("idxls_pointes").getString(0))
        assertEquals("en_attente", recap.getString("etat"))
    }
    @Test(expected = IllegalArgumentException::class) fun recapRejectsMixedMonths() {
        VolumeWorkflow.recap(listOf(invoice("1"), invoice("2").put("mois", "2026-10")), emptyList(), "2026-09-06", "00PERS")
    }
    @Test fun wholeBatchTotalsIncludeEveryReadingAndMarkCalculationErrors() {
        val rows = listOf(invoice("1"), invoice("2"), invoice("3"))
        assertEquals(BigDecimal("300.30"), VolumeWorkflow.total(rows))
        assertTrue(rows.all(VolumeWorkflow::calculable))
        assertFalse(VolumeWorkflow.calculable(invoice("4").put("erreur_calcul", "Tarif absent")))
    }
}
