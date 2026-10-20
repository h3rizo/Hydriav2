package mg.hydria.app.repairs

import mg.hydria.shared.repairs.RepairDetails
import mg.hydria.shared.rules.repairs.RepairRules
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate
import java.time.temporal.ChronoUnit

class RepairDetailsCompatibilityTest {
    @Test fun overdueMatchesJavaAcrossFourCalendarYears() {
        val today = LocalDate.of(2026, 9, 7)
        val first = LocalDate.of(2023, 1, 1)
        repeat(1461) { offset ->
            val date = first.plusDays(offset.toLong())
            assertEquals(ChronoUnit.DAYS.between(date, today).toInt(), RepairDetails.overdueDays(date.toString(), today.toString()))
        }
    }
    @Test fun jsonFallbacksKeepMissingAndExplicitEmptyStatusDistinct() {
        assertTrue(RepairRules.isCompleted(JSONObject("""{"statut":"Terminée"}""")))
        assertFalse(RepairRules.isCompleted(JSONObject("""{"statut":"Terminée","statut_code":""}""")))
        assertTrue(RepairRules.isCompleted(JSONObject("""{"terminee":true,"statut_code":""}""")))
        assertEquals("sans ouvrage", RepairRules.workKey(JSONObject()))
        assertEquals("", RepairRules.workKey(JSONObject("""{"ouvrage_nom":""}""")))
        assertEquals(2, RepairRules.criticality(JSONObject()))
    }
    @Test fun malformedQueueEntriesAreIgnored() {
        val pending = JSONArray("""[null,"bad",{}, {"type":"finish_repair"}, {"type":"finish_repair","payload":{"planning_id":7}}, {"type":"finish_repair","payload":{"planning_id":"7"}}, {"type":"save_repair","payload":{"planning_id":8}}]""")
        assertEquals(setOf("7"), RepairRules.pendingCompletionIds(pending))
    }
}
