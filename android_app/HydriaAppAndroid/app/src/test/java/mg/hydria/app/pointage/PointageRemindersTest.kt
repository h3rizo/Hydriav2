package mg.hydria.app.pointage

import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate
import java.time.ZonedDateTime

class PointageRemindersTest {
    private fun ms(date: String, hour: Int, minute: Int) =
        ZonedDateTime.of(LocalDate.parse(date), java.time.LocalTime.of(hour, minute), PointageRules.ZONE).toInstant().toEpochMilli()

    private val calendrier = JSONArray(
        """[{"date":"2026-09-21","matin":true,"aprem":false,"nuit":true},
            {"date":"2026-09-22","matin":false,"aprem":true,"nuit":false}]"""
    )

    @Test fun rappelDixMinutesAvantOuvertureDesCreneauxPrevus() {
        val triggers = PointageReminders.triggers(calendrier, ms("2026-09-21", 6, 0))
        assertEquals(listOf("matin", "nuit", "aprem"), triggers.map { it.creneau.type })
        assertEquals(ms("2026-09-21", 9, 50), triggers[0].atMs)
        assertEquals(ms("2026-09-21", 18, 50), triggers[1].atMs)
        assertEquals(ms("2026-09-22", 14, 50), triggers[2].atMs)
    }

    @Test fun ignoreLesRappelsDejaPasses() {
        val triggers = PointageReminders.triggers(calendrier, ms("2026-09-21", 12, 0))
        assertEquals(listOf("nuit", "aprem"), triggers.map { it.creneau.type })
    }

    @Test fun ignoreLesCreneauxNonPrevus() {
        val triggers = PointageReminders.triggers(
            JSONArray("""[{"date":"2026-09-21","matin":false,"aprem":false,"nuit":false}]"""), 0L)
        assertTrue(triggers.isEmpty())
    }

    @Test fun ignoreUneDateInvalide() {
        assertTrue(PointageReminders.triggers(JSONArray("""[{"date":"n'importe quoi","matin":true}]"""), 0L).isEmpty())
    }
}
