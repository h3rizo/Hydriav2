package mg.hydria.shared.readings

import kotlin.test.*

class SocialCardPreparationTest {
    @Test fun omitsZeroQuantityAndCalculatesVolumeFromBidons() {
        val result = SocialCardSelection.prepare(listOf(SocialCardQuantity("a", 30), SocialCardQuantity("b", 0), SocialCardQuantity("c", 5)), setOf("a", "b", "c"))
        assertNull(result.error)
        assertEquals(listOf("a", "c"), result.cards.map { it.id })
        assertEquals(0.6, result.cards[0].volume, 0.000001)
        assertEquals(0.7, result.totalVolume, 0.000001)
    }
    @Test fun invalidQuantitiesFailWithoutPartialPayload() {
        for (quantity in listOf(-1, 31, Int.MAX_VALUE)) {
            val result = SocialCardSelection.prepare(listOf(SocialCardQuantity("a", 1), SocialCardQuantity("b", quantity)), setOf("a", "b"))
            assertEquals(SocialCardError.INVALID_QUANTITY, result.error)
            assertTrue(result.cards.isEmpty())
        }
    }
    @Test fun evenUnusedCardsMustBeLinkedAndUnique() {
        assertEquals(SocialCardError.UNLINKED_OR_DUPLICATE_CARD,
            SocialCardSelection.prepare(listOf(SocialCardQuantity("other", 0)), setOf("a")).error)
        assertEquals(SocialCardError.UNLINKED_OR_DUPLICATE_CARD,
            SocialCardSelection.prepare(listOf(SocialCardQuantity("a", 0), SocialCardQuantity("a", 1)), setOf("a")).error)
    }
    @Test fun emptySelectionIsValid() {
        val result = SocialCardSelection.prepare(emptyList(), emptySet())
        assertNull(result.error)
        assertEquals(0.0, result.totalVolume)
        assertTrue(result.cards.isEmpty())
    }
}
