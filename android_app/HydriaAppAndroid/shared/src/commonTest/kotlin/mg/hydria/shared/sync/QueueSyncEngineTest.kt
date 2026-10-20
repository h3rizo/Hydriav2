package mg.hydria.shared.sync

import kotlin.test.*

class QueueSyncEngineTest {
    private data class Operation(val id: String, val volume: Boolean = false)
    private class Fixture {
        val events = mutableListOf<String>()
        val responses = mutableMapOf<String,QueueResponse<String>>()
        val confirmations = mutableMapOf<String,String>()
        var throwAt: String? = null
        var afterError: String? = null
        fun event(value: String) {
            events += value
            if (throwAt == value) throw IllegalStateException("failure:$value")
        }
        fun run(vararg ops: Operation): String? = runItems { ops.asIterable() }
        fun runItems(items: () -> Iterable<Operation>): String? = QueueSyncEngine.run<Operation,String,String>(
            operations = items,
            id = { event("id:" + it.id); it.id },
            isVolume = { it.volume },
            syncVolume = { event("volume:" + it.id); responses[it.id] ?: QueueResponse(true,200,"","body") },
            markSynchronizing = { event("sync:$it") },
            payload = { event("payload:" + it.id); it.id },
            send = { op, _ -> event("send:" + op.id); responses[op.id] ?: QueueResponse(true,200,"","body") },
            recordConflict = { op, _, body -> assertEquals("body",body); event("conflict:" + op.id) },
            confirmationError = { op, _, _ -> event("confirm:" + op.id); confirmations[op.id] },
            markSynced = { op, _ -> event("accepted:" + op.id) },
            remove = { event("remove:$it") },
            markFailed = { id,error -> event("failed:$id:$error") },
            afterQueue = { event("after"); afterError },
        )
    }
    @Test fun successfulOperationsAreAcceptedBeforeRemovalAndRefreshComesLast() {
        val f = Fixture()
        assertNull(f.run(Operation("a"),Operation("b")))
        assertEquals(listOf("id:a","sync:a","payload:a","send:a","confirm:a","accepted:a","remove:a",
            "id:b","sync:b","payload:b","send:b","confirm:b","accepted:b","remove:b","after"),f.events)
    }
    @Test fun httpConflictFailureAndRejectedConfirmationContinueWithoutRemovingFailures() {
        val f = Fixture()
        f.responses["a"] = QueueResponse(false,409,"conflict","body")
        f.responses["b"] = QueueResponse(false,500,"server","body")
        f.confirmations["c"] = "unconfirmed"
        assertEquals("unconfirmed",f.run(Operation("a"),Operation("b"),Operation("c"),Operation("d")))
        assertTrue(f.events.indexOf("conflict:a") < f.events.indexOf("failed:a:conflict"))
        assertFalse(f.events.contains("confirm:a"))
        assertFalse(f.events.contains("conflict:b"))
        assertEquals(listOf("remove:d"),f.events.filter { it.startsWith("remove:") })
        assertEquals("after",f.events.last())
    }
    @Test fun volumeOwnsItsQueueChangesAndDoesNotClearPreviousFailure() {
        val f = Fixture()
        f.responses["v"] = QueueResponse(false,409,"volume error","body")
        assertEquals("volume error",f.run(Operation("v",true),Operation("a")))
        assertEquals(listOf("id:v","volume:v"),f.events.take(2))
        assertFalse(f.events.any { it == "sync:v" || it == "conflict:v" || it == "remove:v" })
        assertTrue(f.events.contains("remove:a"))
    }
    @Test fun networkOrPayloadFailureMarksActiveItemAndStopsBatch() {
        for (stage in listOf("sync","payload","send","accepted","remove")) {
            val f = Fixture()
            f.throwAt = "$stage:a"
            assertEquals("failure:$stage:a",f.run(Operation("a"),Operation("b")))
            assertEquals("failed:a:failure:$stage:a",f.events.last())
            assertFalse(f.events.contains("id:b"))
            assertFalse(f.events.contains("after"))
        }
    }
    @Test fun volumeAndRowDecodeExceptionsDoNotMarkUnrelatedItems() {
        val f = Fixture()
        f.throwAt = "volume:v"
        assertEquals("failure:volume:v",f.run(Operation("a"),Operation("v",true),Operation("b")))
        assertFalse(f.events.any { it.startsWith("failed:") })
        val rows = Fixture()
        assertEquals("broken row",rows.runItems {
            Iterable { sequence {
                yield(Operation("a"))
                throw IllegalArgumentException("broken row")
            }.iterator() }
        })
        assertTrue(rows.events.contains("remove:a"))
        assertFalse(rows.events.any { it.startsWith("failed:") })
        assertFalse(rows.events.contains("after"))
    }
    @Test fun refreshFailureOverridesEarlierFailureWithoutChangingCompletedItems() {
        val f = Fixture()
        f.responses["a"] = QueueResponse(false,500,"old","body")
        f.afterError = "refresh"
        assertEquals("refresh",f.run(Operation("a"),Operation("b")))
        assertTrue(f.events.contains("remove:b"))
        f.throwAt = "after"
        f.events.clear()
        assertEquals("failure:after",f.run(Operation("b")))
        assertFalse(f.events.any { it.startsWith("failed:") })
    }
    @Test fun missingExceptionMessageKeepsConnectionFallbackAndEmptyQueueStillRefreshes() {
        val f = Fixture()
        assertEquals("Connexion interrompue",f.runItems { throw Exception() })
        assertTrue(f.events.isEmpty())
        assertNull(f.run())
        assertEquals(listOf("after"),f.events)
    }
}
