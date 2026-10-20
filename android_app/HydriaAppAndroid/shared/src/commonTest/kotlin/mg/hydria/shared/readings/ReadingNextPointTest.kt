package mg.hydria.shared.readings

import kotlin.test.*

class ReadingNextPointTest {
    private val ids = listOf("p1", "p2", "p3", "p4")

    @Test fun nextPointIsTheOneThatFollowsInTheDisplayedOrder() {
        assertEquals("p2", ReadingNextPoint.after(ids, "p1", setOf("p1")))
        assertEquals("p4", ReadingNextPoint.after(ids, "p3", setOf("p3")))
    }

    @Test fun endOfListGoesBackToTheStart() {
        assertEquals("p1", ReadingNextPoint.after(ids, "p4", setOf("p4")))
        assertEquals("p2", ReadingNextPoint.after(ids, "p4", setOf("p1", "p4")))
    }

    @Test fun unknownOrMissingCurrentPointGivesTheFirstRemainingOne() {
        assertEquals("p1", ReadingNextPoint.after(ids, "ghost", emptySet()))
        assertEquals("p1", ReadingNextPoint.after(ids, null, emptySet()))
        assertEquals("p3", ReadingNextPoint.after(ids, null, setOf("p1", "p2")))
    }

    @Test fun donePointsAreSkipped() {
        assertEquals("p4", ReadingNextPoint.after(ids, "p1", setOf("p1", "p2", "p3")))
        // Retour au début en sautant le courant : p1 est fait, p2 suit.
        assertEquals("p2", ReadingNextPoint.after(ids, "p3", setOf("p1", "p3", "p4")))
    }

    @Test fun currentPointIsNeverReturnedEvenIfTheCallerForgotToMarkItDone() {
        assertNull(ReadingNextPoint.after(listOf("p1"), "p1", emptySet()))
        assertEquals("p2", ReadingNextPoint.after(listOf("p1", "p2"), "p1", emptySet()))
        assertEquals("p1", ReadingNextPoint.after(listOf("p1", "p2"), "p2", emptySet()))
    }

    @Test fun nothingLeftMeansTheCampaignIsFinished() {
        assertNull(ReadingNextPoint.after(ids, "p2", ids.toSet()))
        assertNull(ReadingNextPoint.after(ids, "p2", setOf("p1", "p2", "p3", "p4", "autre")))
        assertNull(ReadingNextPoint.after(emptyList(), "p1", emptySet()))
        assertNull(ReadingNextPoint.after(emptyList(), null, emptySet()))
    }

    @Test fun orderIsTheDisplayedOneNotTheIdOrder() {
        // « Proches de moi » : la liste est triée par distance, pas par identifiant.
        val byDistance = listOf("p3", "p1", "p4", "p2")
        assertEquals("p1", ReadingNextPoint.after(byDistance, "p3", setOf("p3")))
        assertEquals("p4", ReadingNextPoint.after(byDistance, "p1", setOf("p1", "p3")))
        assertEquals("p3", ReadingNextPoint.after(byDistance, "p2", setOf("p2")))
    }

    @Test fun doneIdsOutsideTheDisplayedListHaveNoEffect() {
        assertEquals("p2", ReadingNextPoint.after(ids, "p1", setOf("p1", "autre-parcelle")))
    }
}
