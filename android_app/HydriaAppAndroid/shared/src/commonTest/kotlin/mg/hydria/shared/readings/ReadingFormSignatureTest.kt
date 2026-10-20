package mg.hydria.shared.readings

import kotlin.test.*

class ReadingFormSignatureTest {
    private fun sig(index: String = "", remark: String = "", nonBillable: String = "0", cards: List<ReadingDraftCard> = emptyList()) =
        ReadingFormSignature.of(index, remark, nonBillable, cards)

    @Test fun emptyFormEqualsTheBaseline() {
        // Formulaire d'un point sans saisie : champs vides, « 0 » dans le volume non facturé.
        val baseline = sig()
        assertEquals(baseline, sig(index = "", remark = "", nonBillable = "0"))
        assertEquals(baseline, sig(index = "  ", remark = "   ", nonBillable = "0"))
    }

    @Test fun commaIsTheSameAsDotInTheIndex() {
        assertEquals(sig(index = "130.67"), sig(index = "130,67"))
        assertEquals(sig(index = "130.67"), sig(index = " 130,67 "))
    }

    @Test fun oneMoreDigitIsDifferent() {
        assertNotEquals(sig(index = "130.67"), sig(index = "130.678"))
        assertNotEquals(sig(), sig(index = "1"))
        assertNotEquals(sig(), sig(remark = "Fuite"))
    }

    @Test fun surroundingSpacesAreIgnoredInTheRemark() {
        assertEquals(sig(remark = "Fuite"), sig(remark = "  Fuite \n"))
        assertNotEquals(sig(remark = "Fuite"), sig(remark = "Fu ite"))
    }

    @Test fun emptyZeroAndDecimalZeroGiveTheSameNonBillableKey() {
        // Cas 1A-SUIVI-1-a : effacer le « 0 » du champ ne doit pas compter comme une saisie.
        val keys = listOf("", " ", "0", "0,00", "0.00", "0.0", "00").map { sig(nonBillable = it) }
        keys.forEach { assertEquals(keys.first(), it) }
        assertEquals("0.0", keys.first()[2])
    }

    @Test fun nonZeroNonBillableIsDifferentWhateverTheSeparator() {
        assertNotEquals(sig(nonBillable = "0"), sig(nonBillable = "1"))
        assertEquals(sig(nonBillable = "2.5"), sig(nonBillable = "2,50"))
    }

    @Test fun unreadableNonBillableKeepsItsText() {
        val unreadable = sig(nonBillable = "abc")
        assertNotEquals(sig(nonBillable = "0"), unreadable)
        assertEquals("abc", unreadable[2])
        assertNotEquals(unreadable, sig(nonBillable = "abd"))
    }

    @Test fun cardsAreWrittenIdColonBidons() {
        val signature = sig(cards = listOf(ReadingDraftCard("c1", 3), ReadingDraftCard("c2", 0)))
        assertEquals("c1:3,c2:0", signature[3])
        assertNotEquals(signature, sig(cards = listOf(ReadingDraftCard("c1", 4), ReadingDraftCard("c2", 0))))
        assertNotEquals(signature, sig())
    }

    @Test fun orderOfTheCardsHasNoEffect() {
        val a = ReadingDraftCard("c1", 3)
        val b = ReadingDraftCard("c2", 7)
        assertEquals(sig(cards = listOf(a, b)), sig(cards = listOf(b, a)))
    }

    @Test fun signatureHasFourEntriesInTheHistoricOrder() {
        val signature = sig(index = "12,5", remark = " ok ", nonBillable = "1,5", cards = listOf(ReadingDraftCard("c1", 2)))
        assertEquals(listOf("12.5", "ok", "1.5", "c1:2"), signature)
    }
}
