package mg.hydria.shared.readings

import kotlin.test.*

class ReadingFormLayoutTest {
    private fun open(required: Boolean = false, blank: Boolean = true, kiosk: Boolean = false, hidden: Boolean = false) =
        ReadingFormLayout.shouldOpenDetails(required, blank, kiosk, hidden)

    @Test fun detailsStayClosedForANormalPoint() {
        assertFalse(open())
        assertFalse(open(required = false, blank = false))
    }

    @Test fun detailsOpenWhenTheRemarkIsRequiredAndEmpty() {
        assertTrue(open(required = true, blank = true))
    }

    @Test fun detailsStayClosedOnceTheRequiredRemarkIsFilledIn() {
        assertFalse(open(required = true, blank = false))
    }

    @Test fun detailsOpenForAKioskWithSocialCards() {
        assertTrue(open(kiosk = true))
        assertTrue(open(kiosk = true, required = true, blank = false))
    }

    @Test fun detailsOpenWhenADraftOrACorrectionHoldsAHiddenValue() {
        assertTrue(open(hidden = true))
    }

    @Test fun anyHiddenFieldFilledCountsAsAHiddenValue() {
        assertTrue(ReadingFormLayout.hasHiddenValues("Fuite", "0", emptyList()))
        assertTrue(ReadingFormLayout.hasHiddenValues("", "1,5", emptyList()))
        assertTrue(ReadingFormLayout.hasHiddenValues("", "0", listOf(ReadingDraftCard("c1", 2))))
        assertTrue(ReadingFormLayout.hasHiddenValues("", "abc", emptyList()))
    }

    @Test fun defaultValuesAreNotHiddenValues() {
        assertFalse(ReadingFormLayout.hasHiddenValues("", "0", emptyList()))
        assertFalse(ReadingFormLayout.hasHiddenValues("  ", "", emptyList()))
        assertFalse(ReadingFormLayout.hasHiddenValues("", "0,00", emptyList()))
        assertFalse(ReadingFormLayout.hasHiddenValues("", "0", listOf(ReadingDraftCard("c1", 0))))
    }
}
