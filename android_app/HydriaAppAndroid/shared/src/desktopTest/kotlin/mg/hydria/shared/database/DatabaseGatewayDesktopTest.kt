package mg.hydria.shared.database

import org.json.JSONObject
import java.io.File
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Verifie que les facades DB (aujourd'hui en jvmCommonMain, partagees
 * Android + Desktop) fonctionnent avec le driver JDBC du Desktop, schema
 * cree automatiquement au premier acces. Premier test unitaire de ces
 * facades : sur Android elles n'etaient couvertes que par des tests
 * instrumentes.
 */
class DatabaseGatewayDesktopTest {
    private lateinit var dbFile: File

    @BeforeTest
    fun setUp() {
        HydriaSharedDatabaseHolder.resetForTests()
        dbFile = File.createTempFile("hydria-test-", ".db").also { it.delete() }
        HydriaDesktopDatabase.init(dbFile)
    }

    @AfterTest
    fun tearDown() {
        HydriaSharedDatabaseHolder.resetForTests()
        dbFile.delete()
    }

    @Test
    fun searchCacheRoundTrips() {
        assertNull(HydriaSearchCacheGateway.payload("k"))
        HydriaSearchCacheGateway.save("k", JSONObject().put("total", 3), now = 111L)
        assertEquals(3, HydriaSearchCacheGateway.payload("k")?.getInt("total"))
        assertEquals(111L, HydriaSearchCacheGateway.updatedAt("k"))
        HydriaSearchCacheGateway.save("k", JSONObject().put("total", 7), now = 222L)
        assertEquals(7, HydriaSearchCacheGateway.payload("k")?.getInt("total"))
    }

    @Test
    fun snapshotSurvivesChunkingBoundary() {
        assertNull(HydriaSnapshotGateway.snapshot())
        val big = "x".repeat(300 * 1024) // > CHUNK_CHARS (256 Ko) => plusieurs chunks
        HydriaSnapshotGateway.saveSnapshot(JSONObject().put("blob", big).put("n", 1))
        val restored = HydriaSnapshotGateway.snapshot()
        assertEquals(1, restored?.getInt("n"))
        assertEquals(big, restored?.getString("blob"))
        HydriaSnapshotGateway.clearSnapshot()
        assertNull(HydriaSnapshotGateway.snapshot())
    }

    @Test
    fun syncQueueEnqueueListAndRemove() {
        assertEquals(0, HydriaSyncQueueGateway.pendingCount())
        HydriaSyncQueueGateway.enqueue("u1", "reading", JSONObject().put("point", "p1"))
        HydriaSyncQueueGateway.enqueueIfAbsent("u1", "reading", JSONObject().put("point", "dup"))
        assertEquals(1, HydriaSyncQueueGateway.pendingCount())
        val pending = HydriaSyncQueueGateway.pending()
        assertEquals("u1", pending.getJSONObject(0).getString("local_uuid"))
        assertEquals("p1", pending.getJSONObject(0).getJSONObject("payload").getString("point"))
        HydriaSyncQueueGateway.markFailed("u1", "boom")
        assertTrue(HydriaSyncQueueGateway.pending().getJSONObject(0).getString("last_error").isNotEmpty())
        HydriaSyncQueueGateway.remove("u1")
        assertEquals(0, HydriaSyncQueueGateway.pendingCount())
    }
}
