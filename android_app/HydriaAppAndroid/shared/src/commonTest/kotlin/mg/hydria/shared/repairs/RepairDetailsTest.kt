package mg.hydria.shared.repairs

import kotlin.test.*

class RepairDetailsTest {
    @Test fun completedStatusesAndExplicitFlag() {
        for (status in listOf("TERMINEE", " Terminée ", "terminé", "cloturee", "clôturée", "DONE", "completed"))
            assertTrue(RepairDetails.isCompleted(false, status), status)
        assertFalse(RepairDetails.isCompleted(false, "en_cours"))
        assertFalse(RepairDetails.isCompleted(false, ""))
        assertTrue(RepairDetails.isCompleted(true, "en_cours"))
    }
    @Test fun priorityUsesKeywordPrecedenceAndDefault() {
        assertEquals(5, RepairDetails.criticality("urgente", "Critique"))
        assertEquals(4, RepairDetails.criticality("urgente", "Haute"))
        for (label in listOf("Haute", "Élevée", "Elevee")) assertEquals(3, RepairDetails.criticality("", label))
        assertEquals(2, RepairDetails.criticality("", ""))
        assertEquals(2, RepairDetails.criticality("", "Moyenne"))
        assertEquals(1, RepairDetails.criticality("", "Basse"))
    }
    @Test fun labelsKeepLegacyWhitespaceAndFallbacks() {
        assertEquals(" 42 ", RepairDetails.workKey(" 42 ", "ignored"))
        assertEquals("puits", RepairDetails.workKey("", " PUITS "))
        assertEquals(" Title ", RepairDetails.activityLabel(" Title ", "Job", "Activity"))
        assertEquals("Job", RepairDetails.activityLabel(" ", "Job", "Activity"))
        assertEquals("Réparation", RepairDetails.activityLabel("", "", ""))
        assertEquals("Normale", RepairDetails.priorityLabel(" "))
    }
    @Test fun overdueHandlesFutureTodayLeapDayAndTimestamp() {
        assertEquals(2, RepairDetails.overdueDays("2024-02-28T12:00:00Z", "2024-03-01"))
        assertEquals(0, RepairDetails.overdueDays("2026-09-07", "2026-09-07"))
        assertEquals(-2, RepairDetails.overdueDays("2026-09-09", "2026-09-07"))
        assertEquals(1, RepairDetails.overdueDays("2025-12-31", "2026-01-01"))
    }
    @Test fun overdueLabelSaysLateInDaysTodayAndUpcoming() {
        assertEquals(OverdueLabel("224 j", "RETARD", true), RepairDetails.overdueLabel(224))
        assertEquals(OverdueLabel("1 j", "RETARD", true), RepairDetails.overdueLabel(1))
        assertEquals(OverdueLabel("AUJ.", "", false), RepairDetails.overdueLabel(0))
        assertEquals(OverdueLabel("dans 5 j", "", false), RepairDetails.overdueLabel(-5))
        assertEquals(OverdueLabel("dans 1 j", "", false), RepairDetails.overdueLabel(-1))
        assertNull(RepairDetails.overdueLabel(null))
    }
    @Test fun overdueLabelNeverShowsANegativeSign() {
        for (days in -400..400) {
            val label = RepairDetails.overdueLabel(days)!!
            assertFalse('-' in label.value, "jours=$days -> ${label.value}")
            assertEquals(days > 0, label.late, "jours=$days")
            assertEquals(days > 0, label.caption == "RETARD", "jours=$days")
        }
    }
    @Test fun overdueLabelFollowsOverdueDays() {
        assertEquals("2 j", RepairDetails.overdueLabel(RepairDetails.overdueDays("2024-02-28T12:00:00Z", "2024-03-01"))?.value)
        assertEquals("AUJ.", RepairDetails.overdueLabel(RepairDetails.overdueDays("2026-09-07", "2026-09-07"))?.value)
        assertEquals("dans 2 j", RepairDetails.overdueLabel(RepairDetails.overdueDays("2026-09-09", "2026-09-07"))?.value)
        assertNull(RepairDetails.overdueLabel(RepairDetails.overdueDays("bad", "2026-09-07")))
    }
    @Test fun tabBadgeCountsOnlyOverdueOpenRepairsInPerimeter() {
        assertTrue(RepairDetails.countsOnTabBadge(completed = false, outsidePerimeter = false, overdueDays = 1))
        assertTrue(RepairDetails.countsOnTabBadge(completed = false, outsidePerimeter = false, overdueDays = 224))
        assertFalse(RepairDetails.countsOnTabBadge(completed = false, outsidePerimeter = false, overdueDays = 0))
        assertFalse(RepairDetails.countsOnTabBadge(completed = false, outsidePerimeter = false, overdueDays = -3))
        assertFalse(RepairDetails.countsOnTabBadge(completed = false, outsidePerimeter = false, overdueDays = null))
        assertFalse(RepairDetails.countsOnTabBadge(completed = true, outsidePerimeter = false, overdueDays = 10))
        assertFalse(RepairDetails.countsOnTabBadge(completed = false, outsidePerimeter = true, overdueDays = 10))
    }
    @Test fun malformedDatesAreUnknownButKeepLegacySortKey() {
        for (value in listOf("", "bad", "2026-02-29", "2026-13-01")) assertNull(RepairDetails.overdueDays(value, "2026-09-07"))
        assertEquals("2026-02-29", RepairDetails.dateKey("2026-02-29"))
        assertEquals("9999-12-31", RepairDetails.dateKey("bad"))
    }
    @Test fun pendingActionsIgnoreOtherTypesAndBlankIds() {
        val actions = listOf(RepairPendingAction("finish_repair", "1"), RepairPendingAction("finish_repair", "1"),
            RepairPendingAction("save_repair", "2"), RepairPendingAction("finish_repair", " "), RepairPendingAction("finish_repair", " 3 "))
        assertEquals(setOf("1", " 3 "), RepairDetails.pendingCompletionIds(actions))
    }
}
