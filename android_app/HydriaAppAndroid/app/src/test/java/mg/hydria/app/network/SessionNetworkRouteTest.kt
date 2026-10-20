package mg.hydria.app.network

import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class SessionNetworkRouteTest {
    @Test fun failedProbeKeepsLegacyForEveryCall() {
        var probes = 0
        val route = SessionNetworkRoute { probes++; error("engine unavailable") }
        repeat(2) { assertEquals("legacy", route.call({ error("must not run") }, { "legacy" })) }
        assertEquals(1, probes)
        assertFalse(route.enabled)
    }

    @Test fun transportFailureRetriesThisCallThenStaysLegacy() {
        val route = SessionNetworkRoute {}
        var sharedCalls = 0
        var legacyCalls = 0
        repeat(2) {
            assertEquals("legacy", route.call({ sharedCalls++; error("offline") }, { legacyCalls++; "legacy" }))
        }
        assertEquals(1, sharedCalls)
        assertEquals(2, legacyCalls)
        assertFalse(route.enabled)
    }

    @Test fun serverErrorsDoNotChangeTransportOrReplayWrites() {
        val route = SessionNetworkRoute {}
        for (status in listOf(200, 400, 401, 403, 409, 500)) {
            assertEquals(status, route.call({ status }, { error("HTTP response must not be retried") }))
            assertTrue(route.enabled)
        }
    }

    @Test fun fallbackFailureStillDisablesKtor() {
        val route = SessionNetworkRoute {}
        assertTrue(runCatching { route.call({ error("Ktor") }, { error("legacy") }) }.isFailure)
        assertFalse(route.enabled)
        assertEquals(42, route.call({ error("must not run") }, { 42 }))
    }

    @Test fun domainsAreIndependent() {
        val first = SessionNetworkRoute {}
        val second = SessionNetworkRoute {}
        first.call({ error("offline") }, { 0 })
        assertEquals(1, second.call({ 1 }, { error("unrelated fallback") }))
        assertTrue(second.enabled)
    }

    @Test fun concurrentCallUsesLegacyAfterFirstTransportFailure() {
        val route = SessionNetworkRoute {}
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val secondStarted = CountDownLatch(1)
        val sharedCalls = AtomicInteger()
        val pool = Executors.newFixedThreadPool(2)
        try {
            val first = pool.submit<Int> {
                route.call({ sharedCalls.incrementAndGet(); entered.countDown()
                    check(release.await(5, TimeUnit.SECONDS)); error("offline") }, { 1 })
            }
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            val second = pool.submit<Int> {
                secondStarted.countDown()
                route.call({ sharedCalls.incrementAndGet(); 99 }, { 2 })
            }
            assertTrue(secondStarted.await(5, TimeUnit.SECONDS))
            release.countDown()
            assertEquals(1, first.get(5, TimeUnit.SECONDS))
            assertEquals(2, second.get(5, TimeUnit.SECONDS))
            assertEquals(1, sharedCalls.get())
        } finally { release.countDown(); pool.shutdownNow() }
    }
}
