package mg.hydria.desktop.screens

import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.storage.DesktopPrefs
import mg.hydria.shared.repairs.OverdueLabel
import org.json.JSONObject
import java.io.File
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull

/** Le retard d'une réparation s'affiche avec le libellé partagé (REP_PLAN-11), comme sur Android. */
class RepairsControllerOverdueTest {
    private val controller = RepairsController(
        DesktopSession(DesktopPrefs(File(Files.createTempDirectory("hydria-repairs").toFile(), "prefs.json"))),
    )

    private fun due(daysFromToday: Long) =
        JSONObject().put("date_prevue", todayMadagascar().plusDays(daysFromToday).toString())

    @Test
    fun lateRepairShowsDaysAndTheRetardCaptionWithoutANegativeSign() {
        assertEquals(OverdueLabel("224 j", "RETARD", true), controller.overdueLabel(due(-224)))
        assertFalse(controller.overdueLabel(due(-224))!!.value.contains("-"))
    }

    @Test
    fun dueTodayShowsAujAndNothingElse() {
        assertEquals(OverdueLabel("AUJ.", "", false), controller.overdueLabel(due(0)))
    }

    @Test
    fun upcomingRepairShowsDansNJours() {
        assertEquals(OverdueLabel("dans 5 j", "", false), controller.overdueLabel(due(5)))
    }

    @Test
    fun unknownDateHasNoLabel() {
        assertNull(controller.overdueLabel(JSONObject()))
        assertNull(controller.overdueLabel(JSONObject().put("date_prevue", "bientot")))
    }
}
