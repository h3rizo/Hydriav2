package mg.hydria.shared.readings

import kotlin.test.*

class SocialCardSelectionTest {
    @Test fun acceptsOnlyLinkedIdsWithoutDuplicates() {
        assertTrue(SocialCardSelection.validIds(listOf("a", "b"), setOf("a", "b", "c")))
        assertFalse(SocialCardSelection.validIds(listOf("a", "a"), setOf("a")))
        assertFalse(SocialCardSelection.validIds(listOf("other-point"), setOf("a")))
    }
    @Test fun rejectsFreeTextCardsAndMissingIdentifiers() {
        assertFalse(SocialCardSelection.validIds(listOf(""), setOf("a")))
        assertFalse(SocialCardSelection.validIds(listOf(" "), setOf(" ")))
        assertFalse(SocialCardSelection.validIds(listOf("unregistered-number"), emptySet()))
    }
    @Test fun noCardRequiredAndPointChangeInvalidatesFormerSelection() {
        assertTrue(SocialCardSelection.validIds(emptyList(), emptySet()))
        assertTrue(SocialCardSelection.validIds(listOf("a"), setOf("a")))
        assertFalse(SocialCardSelection.validIds(listOf("a"), setOf("b")))
    }
}
