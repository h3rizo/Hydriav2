package mg.hydria.shared.navigation

import kotlin.test.*

class ImmediatePhotoUploadTest {
    @Test fun successfulResponseRemovesOnlyAfterSend() {
        val events = mutableListOf<String>()
        val result = ImmediatePhotoUpload.run({ events += "sync" },
            { events += "send"; PhotoUploadResponse(true,"unused") },
            { events += "remove" },{ error("must not fail") })
        assertEquals(listOf("sync","send","remove"),events)
        assertTrue(result.successful)
        assertEquals("Photo synchronisée",result.statusMessage)
    }
    @Test fun failureAndNetworkExceptionKeepPhotoWithoutRetry() {
        for (throws in listOf(false,true)) {
            var calls = 0
            var failure: String? = null
            val result = ImmediatePhotoUpload.run({},
                { calls++; if(throws) error("network"); PhotoUploadResponse(false,"server error") },
                { error("must not remove") },{ failure = it })
            assertEquals(1,calls)
            assertEquals(if(throws) "Synchronisation de la photo impossible" else "server error",failure)
            assertFalse(result.successful)
            assertEquals("Photo conservée pour une prochaine synchronisation",result.statusMessage)
        }
    }
    @Test fun storageFailuresPropagateInsteadOfBeingTreatedAsNetworkFailures() {
        var sent = false
        assertFailsWith<IllegalStateException> {
            ImmediatePhotoUpload.run({ error("storage") },{ sent=true; PhotoUploadResponse(true,"") },{},{})
        }
        assertFalse(sent)
        assertFailsWith<IllegalStateException> {
            ImmediatePhotoUpload.run({},{ PhotoUploadResponse(true,"") },{ error("remove") },{ error("wrong callback") })
        }
    }
}
