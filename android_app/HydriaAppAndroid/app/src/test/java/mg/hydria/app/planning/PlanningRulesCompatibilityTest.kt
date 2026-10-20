package mg.hydria.app.planning

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Comparaison avec les libelles java.time utilises avant le deplacement commonMain. */
class PlanningRulesCompatibilityTest {
    @Test fun sharedCalendarMatchesLegacyFrenchCalendarAcrossLeapYears() {
        val start = LocalDate.of(2023, 1, 1)
        repeat(1461) { offset ->
            val date = start.plusDays(offset.toLong())
            val key = date.toString()
            assertEquals(date.format(DateTimeFormatter.ofPattern("EEEE", Locale.FRANCE)).uppercase(Locale.FRANCE), PlanningRules.weekdayLabel(key))
            assertEquals(date.format(DateTimeFormatter.ofPattern("EEE", Locale.FRANCE)).replace(".", "").uppercase(Locale.FRANCE), PlanningRules.shortWeekdayLabel(key))
            assertEquals(date.format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale.FRANCE)), PlanningRules.fullDateLabel(key))
            assertEquals(date.dayOfMonth.toString(), PlanningRules.dayNumberLabel(key))
            assertEquals(date.dayOfWeek.value >= 6, PlanningRules.dayState(key, emptyList()).isWeekend)
        }
    }

    @Test fun jsonAdapterKeepsOriginalObjectsAndBooleanCoercion() {
        val first = JSONObject().put("id", "7").put("date", "2026-09-07").put("weekend", "true").put("custom", "retained")
        val second = JSONObject().put("id", "8").put("date", "2026-09-07T10:00:00").put("jour_ferie", true)
        val agenda = PlanningRules.agenda(listOf(first, second), "", "2026-09-07")
        assertSame(first, agenda.days.single().items[0])
        assertSame(second, agenda.days.single().items[1])
        assertTrue(agenda.days.single().state.isWeekend)
        assertTrue(agenda.days.single().state.isHoliday)
        assertEquals("retained", agenda.days.single().items[0].getString("custom"))
    }

    @Test fun legacySentinelAndInvalidDateLabelsRemainUnchanged() {
        assertEquals("9999-12-31", PlanningRules.dateKey(JSONObject()))
        for (key in listOf("9999-12-31", "0001-01-01", "0000-01-01")) {
            assertEquals(LocalDate.parse(key).format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale.FRANCE)), PlanningRules.fullDateLabel(key))
        }
        assertEquals("Date non renseignée", PlanningRules.fullDateLabel("2026-02-31"))
    }
}
