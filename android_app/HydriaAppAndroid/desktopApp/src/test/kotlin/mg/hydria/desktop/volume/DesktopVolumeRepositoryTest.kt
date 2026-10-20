package mg.hydria.desktop.volume

import mg.hydria.shared.database.HydriaDesktopDatabase
import mg.hydria.shared.database.HydriaSharedDatabaseHolder
import mg.hydria.shared.database.HydriaSyncQueueGateway
import mg.hydria.shared.volume.VolumeWorkflowGateway
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.file.Files
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class DesktopVolumeRepositoryTest {
    private val repo = DesktopVolumeRepository { "agent" }

    @BeforeTest
    fun setUp() {
        HydriaSharedDatabaseHolder.resetForTests()
        val dir = Files.createTempDirectory("hydria-volume").toFile()
        HydriaDesktopDatabase.init(File(dir, "hydria.db"))
    }

    private fun invoice(id: String, idxls: String, montant: String, validee: Boolean = false) = JSONObject()
        .put("id", id).put("idxls", idxls).put("abonne", "Abonne $idxls").put("numero", "F-$id")
        .put("montant", montant).put("version", "1").put("mois", "2026-08").put("ouvrage_id", "w1")
        .put("ouvrage", "Ambanja BP").put("validee", validee)

    private fun pack() = JSONObject().put("ouvrage_id", "w1").put("mois", "2026-08").put("generated_at", "2026-09-01")
        .put("factures", JSONArray().put(invoice("b", "10", "2000", true)).put(invoice("a", "2", "3000", true)))
        .put("diamex", JSONArray().put(JSONObject().put("id", "d1").put("montant", "5000").put("numero", "12").put("base", "B1")))

    @Test
    fun packRoundTripSortsByIdxls() {
        repo.savePack(pack())
        val stored = repo.read("pack:w1:2026-08")!!
        assertEquals(listOf("a", "b"), repo.invoices(stored).map { it.getString("id") })
    }

    @Test
    fun enqueueWritesQueueAuditAndRecapAndBlocksDuplicates() {
        repo.savePack(pack())
        val rows = repo.invoices(repo.read("pack:w1:2026-08")!!)
        val extra = JSONObject().put("date", "2026-09-02").put("journal_code", "CA")
        val recap = VolumeWorkflowGateway.recap(rows, rows, "2026-09-02", "CA")
        val id = repo.enqueue("collect", rows, extra, recap)

        assertEquals(1, repo.pending().size)
        assertEquals(setOf("collect"), repo.actions("a"))
        assertEquals(id, repo.read("last_recap:w1:2026-08")!!.getString("id"))
        assertEquals("5000", repo.read("recap:$id")!!.getString("total"))
        assertEquals("en_attente", repo.history().single().getString("etat"))
        assertFailsWith<IllegalArgumentException> { repo.enqueue("collect", rows, extra) }
    }

    @Test
    fun pendingPointingReconcilesDiamexEntry() {
        repo.savePack(pack())
        val p = repo.read("pack:w1:2026-08")!!
        val rows = repo.invoices(p)
        assertTrue(VolumeWorkflowGateway.matches(rows, p.getJSONArray("diamex").getJSONObject(0)))
        repo.enqueue("point", rows, JSONObject().put("diamex_id", "d1"))
        val entries = VolumeWorkflowGateway.reconciledEntries(p.getJSONArray("diamex"), repo.pending(), rows)
        assertTrue(entries.single().optBoolean("pointee"))
    }

    @Test
    fun conflictReviewClosesOperation() {
        repo.savePack(pack())
        val rows = repo.invoices(repo.read("pack:w1:2026-08")!!)
        val id = repo.enqueue("validate", rows)
        val payload = repo.pending().single().getJSONObject("payload").put("_sync_conflict", JSONObject().put("error", "version"))
        HydriaSyncQueueGateway.updatePayload(id, payload)
        assertFailsWith<IllegalArgumentException> { repo.reviewConflict(id, "court") }
        repo.reviewConflict(id, "Verifie en compta, piece 1234")
        assertTrue(repo.pending().isEmpty())
        assertEquals("verification_manuelle", repo.history().single().getString("etat"))
    }
}
