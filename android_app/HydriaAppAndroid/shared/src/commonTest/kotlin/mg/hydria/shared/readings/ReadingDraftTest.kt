package mg.hydria.shared.readings

import kotlin.test.*

class ReadingDraftTest {
    private val key = ReadingDraftBook.key("ouvrage-1", "2026-10-20")
    private val day = 24L * 60 * 60 * 1000
    private val now = 1_800_000_000_000L
    private val emptyBaseline = ReadingFormSignature.of("", "", "0", emptyList())

    private fun book() = ReadingDraftBook(key)

    private fun ReadingDraftBook.putIndex(pointId: String, index: String, at: Long = now, baseline: List<String> = emptyBaseline) =
        put(pointId, index, "", "0", emptyList(), baseline, at)

    @Test fun campaignKeyIsOuvrageBarDate() {
        assertEquals("ouvrage-1|2026-10-20", key)
    }

    @Test fun oneDraftPerPoint() {
        val book = book()
        assertTrue(book.putIndex("p1", "10"))
        assertTrue(book.putIndex("p1", "11"))
        assertTrue(book.putIndex("p2", "20"))
        assertEquals(2, book.size)
        assertEquals("11", book.get("p1")?.index)
        assertEquals(setOf("p1", "p2"), book.pointIds())
        assertTrue(book.contains("p2"))
        assertNull(book.get("p3"))
    }

    @Test fun putKeepsEverythingTypedAndTheClock() {
        val book = book()
        val cards = listOf(ReadingDraftCard("c1", 3))
        book.put("p1", "130,67", "Fuite", "1,5", cards, emptyBaseline, now)
        val draft = assertNotNull(book.get("p1"))
        assertEquals("130,67", draft.index)
        assertEquals("Fuite", draft.remark)
        assertEquals("1,5", draft.nonBillable)
        assertEquals(cards, draft.cards)
        assertEquals(now, draft.savedAtMillis)
    }

    @Test fun draftIdenticalToTheBaselineIsNeverStored() {
        val book = book()
        assertFalse(book.put("p1", "", "", "0", emptyList(), emptyBaseline, now))
        assertFalse(book.put("p1", "  ", " ", "0,00", emptyList(), emptyBaseline, now))
        assertTrue(book.isEmpty())
    }

    @Test fun returningToTheBaselineRemovesTheDraft() {
        val book = book()
        assertTrue(book.putIndex("p1", "10"))
        assertFalse(book.putIndex("p1", ""))
        assertNull(book.get("p1"))
        // Mode correction : la référence est la valeur de la file.
        val queued = ReadingFormSignature.of("130.67", "", "0", emptyList())
        assertFalse(book.putIndex("p2", "130,67", baseline = queued))
        assertTrue(book.putIndex("p2", "131", baseline = queued))
    }

    @Test fun blankPointIdIsIgnored() {
        val book = book()
        assertFalse(book.putIndex(" ", "10"))
        assertTrue(book.isEmpty())
    }

    @Test fun removeAndClear() {
        val book = book()
        book.putIndex("p1", "10")
        book.putIndex("p2", "20")
        assertTrue(book.remove("p1"))
        assertFalse(book.remove("p1"))
        assertEquals(setOf("p2"), book.pointIds())
        book.clear()
        assertTrue(book.isEmpty())
    }

    @Test fun maxAgeIsThreeDaysInASingleConstant() {
        assertEquals(3 * day, ReadingDraftBook.MAX_AGE.inWholeMilliseconds)
    }

    @Test fun purgeRemovesDraftsOlderThanMaxAge() {
        val book = book()
        book.putIndex("fresh", "10", at = now - 2 * day)
        book.putIndex("limit", "11", at = now - 3 * day)
        book.putIndex("old", "12", at = now - 3 * day - 1)
        assertEquals(1, book.purge(now))
        assertEquals(setOf("fresh", "limit"), book.pointIds())
    }

    @Test fun purgeRemovesDraftsOfUnknownPoints() {
        val book = book()
        book.putIndex("p1", "10")
        book.putIndex("gone", "11")
        assertEquals(1, book.purge(now, knownPointIds = setOf("p1", "p2")))
        assertEquals(setOf("p1"), book.pointIds())
        // Sans liste de points connus, seul l'âge compte.
        book.putIndex("anyone", "12")
        assertEquals(0, book.purge(now))
    }

    @Test fun jsonRoundTripKeepsEveryDraft() {
        val book = book()
        book.put("p1", "130,67", "Fuite \"visible\"\nrue", "1,5", listOf(ReadingDraftCard("c1", 3), ReadingDraftCard("c2", 0)), emptyBaseline, now)
        book.putIndex("p2", "20", at = now - day)
        val back = ReadingDraftBook.fromJson(key, book.toJson(), now)
        assertEquals(key, back.campaignKey)
        assertEquals(book.pointIds(), back.pointIds())
        assertEquals(book.get("p1"), back.get("p1"))
        assertEquals(book.get("p2"), back.get("p2"))
    }

    @Test fun loadingPurgesOldDraftsAndUnknownPoints() {
        val book = book()
        book.putIndex("fresh", "10")
        book.putIndex("old", "11", at = now - 4 * day)
        book.putIndex("gone", "12")
        val back = ReadingDraftBook.fromJson(key, book.toJson(), now, knownPointIds = setOf("fresh", "old"))
        assertEquals(setOf("fresh"), back.pointIds())
    }

    @Test fun draftOfAnotherCampaignIsIgnored() {
        val book = book()
        book.putIndex("p1", "10")
        val otherDay = ReadingDraftBook.key("ouvrage-1", "2026-10-21")
        val otherSite = ReadingDraftBook.key("ouvrage-2", "2026-10-20")
        assertTrue(ReadingDraftBook.fromJson(otherDay, book.toJson(), now).isEmpty())
        assertTrue(ReadingDraftBook.fromJson(otherSite, book.toJson(), now).isEmpty())
        assertEquals(otherDay, ReadingDraftBook.fromJson(otherDay, book.toJson(), now).campaignKey)
    }

    @Test fun corruptedJsonGivesAnEmptyBookWithoutException() {
        listOf(null, "", "   ", "not json", "{", "[]", "{\"campaignKey\": 12}", "{\"campaignKey\":\"$key\",\"drafts\":\"x\"}", "\u0000\u0001")
            .forEach { text ->
                val back = ReadingDraftBook.fromJson(key, text, now)
                assertTrue(back.isEmpty(), "livre vide attendu pour : $text")
                assertEquals(key, back.campaignKey)
            }
    }

    @Test fun jsonFromANewerVersionWithExtraFieldsIsStillRead() {
        val text = "{\"campaignKey\":\"$key\",\"extra\":1,\"drafts\":[{\"pointId\":\"p1\",\"index\":\"5\",\"savedAtMillis\":$now,\"futur\":true}]}"
        val back = ReadingDraftBook.fromJson(key, text, now)
        assertEquals("5", back.get("p1")?.index)
    }

    @Test fun draftWithoutPointIdIsDroppedOnLoad() {
        val text = "{\"campaignKey\":\"$key\",\"drafts\":[{\"pointId\":\"\",\"index\":\"5\",\"savedAtMillis\":$now}]}"
        assertTrue(ReadingDraftBook.fromJson(key, text, now).isEmpty())
    }

    @Test fun cardsRemovedFromThePointAreIgnoredOnRestore() {
        val draft = ReadingDraft("p1", "10", cards = listOf(ReadingDraftCard("c1", 3), ReadingDraftCard("gone", 2)))
        assertEquals(listOf(ReadingDraftCard("c1", 3)), draft.cardsAmong(setOf("c1", "c2")))
        assertTrue(draft.cardsAmong(emptySet()).isEmpty())
    }

    @Test fun draftSignatureUsesTheFormNormalisation() {
        val draft = ReadingDraft("p1", index = "130,67", nonBillable = "")
        assertEquals(ReadingFormSignature.of("130.67", "", "0", emptyList()), draft.signature())
    }
}
