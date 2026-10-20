package mg.hydria.shared.planning

import kotlin.test.*

class PlanningAgendaTest {
    @Test fun dateKeyKeepsLegacyTimestampAndMissingDateRules() {
        assertEquals("2026-09-07", PlanningAgenda.dateKey("2026-09-07T23:00:00Z"))
        assertEquals("9999-12-31", PlanningAgenda.dateKey(""))
        assertEquals("9999-12-31", PlanningAgenda.dateKey("07/09/2026"))
        assertEquals("2026-02-31", PlanningAgenda.dateKey("2026-02-31"))
    }

    @Test fun frenchLabelsAndInvalidDatesArePreserved() {
        assertEquals("LUNDI", PlanningAgenda.weekdayLabel("2026-09-07"))
        assertEquals("LUN", PlanningAgenda.shortWeekdayLabel("2026-09-07"))
        assertEquals("7", PlanningAgenda.dayNumberLabel("2026-09-07"))
        assertEquals("7 septembre 2026", PlanningAgenda.fullDateLabel("2026-09-07"))
        assertEquals("29 février 2024", PlanningAgenda.fullDateLabel("2024-02-29"))
        assertEquals("DATE À CONFIRMER", PlanningAgenda.weekdayLabel("2026-02-29"))
        assertEquals("Date non renseignée", PlanningAgenda.fullDateLabel("2026-02-31"))
        assertEquals("—", PlanningAgenda.dayNumberLabel("missing"))
    }

    @Test fun groupingSortsDatesButKeepsSameDayOrderAndDuplicates() {
        val state = PlanningAgenda.prepare(listOf(
            PlanningEntry("later", "2026-09-08"), PlanningEntry("same", "2026-09-07T10:00:00Z"),
            PlanningEntry("same", "2026-09-07"), PlanningEntry("missing", "")), "", "2026-09-07")
        assertEquals(listOf("2026-09-07", "2026-09-08", "9999-12-31"), state.days.map { it.dateKey })
        assertEquals(listOf("same", "same"), state.days[0].items)
        assertEquals("2026-09-07", state.selectedDate)
    }

    @Test fun existingSelectionWinsOverNearestDay() {
        val entries = listOf(PlanningEntry(1, "2026-09-07"), PlanningEntry(2, "2026-10-01"))
        assertEquals("2026-10-01", PlanningAgenda.prepare(entries, "2026-10-01", "2026-09-07").selectedDate)
    }

    @Test fun missingSelectionChoosesNearestDateWithEarlierDayOnTie() {
        val entries = listOf(PlanningEntry(1, "2026-09-08"), PlanningEntry(2, "2026-09-06"))
        assertEquals("2026-09-06", PlanningAgenda.prepare(entries, "removed", "2026-09-07").selectedDate)
        assertEquals("2026-09-08", PlanningAgenda.prepare(entries, "", "2026-09-09").selectedDate)
    }

    @Test fun leapDayDistanceIsCalendarBased() {
        val entries = listOf(PlanningEntry(1, "2024-02-28"), PlanningEntry(2, "2024-03-01"))
        assertEquals("2024-02-28", PlanningAgenda.prepare(entries, "", "2024-02-29").selectedDate)
    }

    @Test fun weekendsComeFromCalendarOrServerAndHolidaysOnlyFromServer() {
        assertTrue(PlanningAgenda.dayState("2026-09-05", false, false).isWeekend)
        assertTrue(PlanningAgenda.dayState("2026-09-06", false, false).isWeekend)
        assertFalse(PlanningAgenda.dayState("2026-09-07", false, false).isWeekend)
        assertTrue(PlanningAgenda.dayState("2026-09-07", true, false).isWeekend)
        assertFalse(PlanningAgenda.dayState("2026-01-01", false, false).isHoliday)
        val agenda = PlanningAgenda.prepare(listOf(PlanningEntry(1, "2026-09-07", true, false),
            PlanningEntry(2, "2026-09-07", false, true)), "", "2026-09-07")
        assertEquals("FÉRIÉ · WEEK-END", PlanningAgenda.dayIndicatorText(agenda.days.single().state))
    }

    @Test fun emptyAndInvalidCalendarsDoNotThrow() {
        val empty = PlanningAgenda.prepare(emptyList<PlanningEntry<String>>(), "old", "2026-09-07")
        assertEquals("", empty.selectedDate); assertTrue(empty.days.isEmpty())
        assertFalse(PlanningAgenda.dayState("2026-02-31", false, false).isWeekend)
        assertEquals("2026-02-31", PlanningAgenda.prepare(listOf(PlanningEntry(1, "2026-02-31")), "", "2026-09-07").selectedDate)
    }

    @Test fun activityClassificationPreservesPriorityAndAccents() {
        assertEquals(PlanningActivityKind.VALIDATED, PlanningAgenda.activityKind(true, "Urgence", ""))
        for (label in listOf("Réparation", "REPARATION", "Urgence", "Panne", "congé pour réparation")) {
            assertEquals(PlanningActivityKind.REPAIR, PlanningAgenda.activityKind(false, label, ""))
        }
        for (label in listOf("Congé", "CONGE", "Repos", "Jour férié")) {
            assertEquals(PlanningActivityKind.REST, PlanningAgenda.activityKind(false, "", label))
        }
        assertEquals(PlanningActivityKind.OTHER, PlanningAgenda.activityKind(false, "Visite", "Entretien"))
    }
}
