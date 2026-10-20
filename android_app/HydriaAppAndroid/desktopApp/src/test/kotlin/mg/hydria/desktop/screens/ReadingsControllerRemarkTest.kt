package mg.hydria.desktop.screens

import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.storage.DesktopPrefs
import mg.hydria.shared.database.HydriaDesktopDatabase
import mg.hydria.shared.database.HydriaSharedDatabaseHolder
import mg.hydria.shared.database.HydriaSyncQueueGateway
import org.json.JSONObject
import java.io.File
import java.nio.file.Files
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Remarque obligatoire (COEUR-02) appliquée à l'écran Relevés du Desktop : même règle que l'app Android. */
class ReadingsControllerRemarkTest {
    private lateinit var controller: ReadingsController

    @BeforeTest
    fun setUp() {
        HydriaSharedDatabaseHolder.resetForTests()
        val dir = Files.createTempDirectory("hydria-readings").toFile()
        HydriaDesktopDatabase.init(File(dir, "hydria.db"))
        controller = ReadingsController(DesktopSession(DesktopPrefs(File(dir, "prefs.json"))))
    }

    private fun point(id: String = "p1", oldIndex: Double = 100.0) = JSONObject()
        .put("id", id).put("nom", "Point $id")
        .put("dernier_releve", JSONObject().put("nouvel_index", oldIndex).put("date_releve", "2026-09-01"))

    private fun queued() = HydriaSyncQueueGateway.pending().length()

    @Test
    fun remarkStaysOptionalForARegularReading() {
        controller.selectPoint(point())
        controller.newIndexInput = "112.5"
        assertFalse(controller.remarkRequired)
        assertNull(controller.remarkError)
        assertTrue(controller.save())
        assertEquals(1, queued())
    }

    @Test
    fun zeroConsumptionRequiresARemarkAndRefusesToSave() {
        controller.selectPoint(point())
        controller.newIndexInput = "100"
        assertTrue(controller.remarkRequired)
        // L'erreur n'apparaît qu'après un refus : pas de rouge dès la frappe.
        assertNull(controller.remarkErrorText)

        assertFalse(controller.save())
        assertEquals("Remarque obligatoire : consommation nulle", controller.remarkErrorText)
        assertEquals(0, queued())

        controller.remark = "Kiosque non utilise"
        assertNull(controller.remarkErrorText)
        assertTrue(controller.save())
        assertEquals(1, queued())
    }

    @Test
    fun nonBilledVolumeRequiresARemark() {
        controller.selectPoint(point())
        controller.newIndexInput = "110"
        controller.nonBilledInput = "2"
        assertTrue(controller.remarkRequired)
        assertFalse(controller.save())
        assertEquals("Remarque obligatoire : volume non facture renseigne", controller.remarkErrorText)
        assertEquals(0, queued())

        controller.remark = "Fuite constatee"
        assertTrue(controller.save())
    }

    @Test
    fun blankRemarkCountsAsEmpty() {
        controller.selectPoint(point())
        controller.newIndexInput = "100"
        controller.remark = "   "
        assertFalse(controller.save())
        assertEquals(0, queued())
    }

    @Test
    fun errorDisappearsWhenTheRuleStopsApplying() {
        controller.selectPoint(point())
        controller.newIndexInput = "100"
        assertFalse(controller.save())
        assertEquals("Remarque obligatoire : consommation nulle", controller.remarkErrorText)
        controller.newIndexInput = "105"
        assertFalse(controller.remarkRequired)
        assertNull(controller.remarkErrorText)
    }

    @Test
    fun selectingAnotherPointClearsAPreviousRefusal() {
        controller.selectPoint(point("p1"))
        controller.newIndexInput = "100"
        assertFalse(controller.save())
        controller.selectPoint(point("p2"))
        controller.newIndexInput = "100"
        assertTrue(controller.remarkRequired)
        assertNull(controller.remarkErrorText)
    }

    @Test
    fun otherValidationErrorsKeepComingFirst() {
        controller.selectPoint(point())
        controller.newIndexInput = "90"
        assertFalse(controller.save())
        assertEquals("L'index doit etre >= 100.0.", controller.message)
        assertNull(controller.remarkErrorText)
    }

    @Test
    fun campaignDateStartsOnTodayInMadagascar() {
        assertEquals(todayMadagascar().toString(), controller.campaignDate)
    }
}
