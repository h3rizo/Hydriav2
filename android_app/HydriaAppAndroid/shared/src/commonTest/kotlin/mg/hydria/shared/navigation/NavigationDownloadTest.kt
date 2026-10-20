package mg.hydria.shared.navigation

import kotlin.test.*

class NavigationDownloadTest {
    private data class Page(val count: Int, val next: String, val more: Boolean = true)

    @Test fun importsBeforeSavingAndUsesSavedCursorForNextRequest() {
        val events = mutableListOf<String>()
        val pages = ArrayDeque(listOf(Page(2,"b"), Page(3,"c",false)))
        val result = NavigationDownload.run("a",
            fetch = { events += "fetch:$it"; NavigationPage(pages.removeFirst(),true,"") },
            importPage = { events += "import:" + it.next; it.count },
            readCursor = { page, _ -> events += "read:" + page.next; NavigationPageCursor(page.next,page.more) },
            saveCursor = { events += "save:$it" },
        )
        assertEquals(listOf("fetch:a","import:b","read:b","save:b","fetch:b","import:c","read:c","save:c"),events)
        assertEquals(5,result.imported)
        assertEquals("5 élément(s) cartographique(s) actualisé(s)",result.message)
    }
    @Test fun httpFailureKeepsAlreadyImportedCountAndDoesNotSaveFailedPage() {
        var calls = 0
        val saved = mutableListOf<String>()
        val result = NavigationDownload.run(null,
            fetch = { calls++; NavigationPage(Page(4,"next"),calls==1,"Erreur serveur") },
            importPage = { it.count },
            readCursor = { page, _ -> NavigationPageCursor(page.next,page.more) },
            saveCursor = { saved += it },
        )
        assertEquals(2,calls)
        assertEquals(listOf("next"),saved)
        assertEquals(NavigationDownloadResult(4,"Erreur serveur · 4 élément(s) reçus"),result)
        val failure = NavigationDownload.run(null,
            fetch = { NavigationPage(Unit,false,"Refusé") },
            importPage = { error("must not import") },
            readCursor = { _, _ -> error("must not read") },
            saveCursor = { error("must not save") },
        )
        assertEquals(NavigationDownloadResult(0,"Refusé"),failure)
    }
    @Test fun repeatedBlankAndFinalCursorsStopWithoutAnotherRequest() {
        for (page in listOf(Page(0,"same"),Page(0," "),Page(0,"last",false))) {
            var calls = 0
            val saved = mutableListOf<String>()
            val result = NavigationDownload.run("same",
                fetch = { calls++; NavigationPage(page,true,"") },
                importPage = { it.count },
                readCursor = { value, _ -> NavigationPageCursor(value.next,value.more) },
                saveCursor = { saved += it },
            )
            assertEquals(1,calls)
            assertEquals(if(page.next.isBlank()) emptyList() else listOf(page.next),saved)
            assertEquals("Carte terrain à jour",result.message)
        }
    }
    @Test fun fiftyPageLimitSavesLastImportedCursor() {
        var calls = 0
        var saved: String? = null
        val result = NavigationDownload.run(null,
            fetch = { cursor ->
                assertEquals(if(calls==0) null else calls.toString(),cursor)
                calls++; NavigationPage(Page(1,calls.toString()),true,"")
            },
            importPage = { it.count },
            readCursor = { page, _ -> NavigationPageCursor(page.next,page.more) },
            saveCursor = { saved = it },
        )
        assertEquals(50,calls)
        assertEquals(50,result.imported)
        assertEquals("50",saved)
    }
    @Test fun importFailureDoesNotAdvanceCursorAndExceptionsPropagate() {
        var saved = false
        val failure = IllegalStateException("local import failed")
        val actual = assertFailsWith<IllegalStateException> {
            NavigationDownload.run(null,
                fetch = { NavigationPage(Unit,true,"") },
                importPage = { throw failure },
                readCursor = { _, _ -> error("must not read") },
                saveCursor = { saved = true },
            )
        }
        assertSame(failure,actual)
        assertFalse(saved)
    }
}
