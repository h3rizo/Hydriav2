package mg.hydria.desktop.screens

import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.storage.DesktopPrefs
import mg.hydria.shared.database.HydriaDesktopDatabase
import mg.hydria.shared.database.HydriaSharedDatabaseHolder
import mg.hydria.shared.database.HydriaSyncQueueGateway
import mg.hydria.shared.readings.ReadingDraftBook
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.file.Files
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Chantier L2-1, alignement Desktop : point suivant après un enregistrement et brouillons en mémoire
 * (un par point et par campagne), mêmes règles que l'app Android (ReadingNextPoint / ReadingDraftBook).
 */
class ReadingsControllerDraftTest {
    private lateinit var controller: ReadingsController
    private var now = 1_000_000L
    private lateinit var p1: JSONObject
    private lateinit var p2: JSONObject
    private lateinit var p3: JSONObject

    @BeforeTest
    fun setUp() {
        HydriaSharedDatabaseHolder.resetForTests()
        val dir = Files.createTempDirectory("hydria-readings-draft").toFile()
        HydriaDesktopDatabase.init(File(dir, "hydria.db"))
        controller = ReadingsController(DesktopSession(DesktopPrefs(File(dir, "prefs.json"))), clock = { now })
        p1 = point("p1", idxls = 1, name = "Alpha")
        p2 = point("p2", idxls = 2, name = "Beta")
        p3 = point("p3", idxls = 3, name = "Gamma")
        controller.ouvrages = listOf(ouvrage("o1", p1, p2, p3))
        controller.selectOuvrage("o1")
    }

    private fun point(id: String, idxls: Int, name: String, oldIndex: Double = 100.0, kiosque: Boolean = false, cards: List<String> = emptyList()) =
        JSONObject()
            .put("id", id).put("nom", name).put("idxls", idxls.toString())
            .put("type", if (kiosque) "Kiosque" else "BP")
            .put("dernier_releve", JSONObject().put("nouvel_index", oldIndex).put("date_releve", "2026-09-01"))
            .put("cartes_sociales", JSONArray().also { array ->
                cards.forEach { cardId ->
                    array.put(JSONObject().put("id", cardId).put("numero_carte", "N-$cardId").put("beneficiaire", "Benef $cardId"))
                }
            })

    private fun ouvrage(id: String, vararg points: JSONObject) = JSONObject()
        .put("id", id).put("nom", "Ouvrage $id")
        .put("points_eau", JSONArray().also { array -> points.forEach { array.put(it) } })

    private fun queued() = HydriaSyncQueueGateway.pending().length()

    private fun selectedId() = controller.selectedPoint?.optString("id")

    private fun saveReading(point: JSONObject, index: String) {
        controller.selectPoint(point)
        controller.newIndexInput = index
        assertTrue(controller.save(), "le releve de ${point.optString("id")} doit etre enregistre")
    }

    // ── Point suivant ────────────────────────────────────────────────────────────────────────────────────

    @Test
    fun saveOpensTheNextPointInTheDisplayedOrder() {
        controller.selectPoint(p1)
        controller.newIndexInput = "110"
        assertTrue(controller.save())
        assertEquals("p2", selectedId())
        // Le formulaire du point suivant est vierge et prêt à recevoir l'index.
        assertEquals("", controller.newIndexInput)
        assertEquals("", controller.remark)
        assertFalse(controller.draftRestored)
        assertTrue(controller.message.orEmpty().contains("1 en attente"))
        assertEquals(1, queued())
    }

    @Test
    fun nextPointSkipsPointsAlreadyInTheQueue() {
        saveReading(p2, "110") // ouvre p3
        controller.selectPoint(p1)
        controller.newIndexInput = "110"
        assertTrue(controller.save())
        // p2 a déjà un relevé en file : on saute directement à p3.
        assertEquals("p3", selectedId())
    }

    @Test
    fun theLastPointWrapsAroundToTheFirstRemainingOne() {
        controller.selectPoint(p3)
        controller.newIndexInput = "110"
        assertTrue(controller.save())
        assertEquals("p1", selectedId())
    }

    @Test
    fun noPointLeftClearsTheSelectionAndSaysSo() {
        saveReading(p1, "110")
        saveReading(p2, "110")
        controller.selectPoint(p3)
        controller.newIndexInput = "110"
        assertTrue(controller.save())
        assertNull(controller.selectedPoint)
        assertEquals("", controller.newIndexInput)
        assertTrue(controller.message.orEmpty().contains("Plus de point a relever"))
        assertEquals(3, queued())
    }

    @Test
    fun aSearchUsedToFindThePointIsClearedAndTheNextPointComesFromTheFullList() {
        controller.pointSearch = "Beta"
        assertEquals(listOf("p2"), controller.visiblePoints.map { it.optString("id") })
        controller.selectPoint(p2)
        controller.newIndexInput = "110"
        assertTrue(controller.save())
        assertEquals("", controller.pointSearch)
        assertEquals("p3", selectedId())
        assertEquals(3, controller.visiblePoints.size)
    }

    @Test
    fun correctingAQueuedReadingAlsoMovesOn() {
        saveReading(p1, "110") // ouvre p2
        controller.selectPoint(p1)
        assertTrue(controller.correcting)
        assertEquals("110", controller.newIndexInput)
        controller.newIndexInput = "115"
        assertTrue(controller.save())
        assertEquals(1, queued())
        assertEquals("p2", selectedId())
        assertTrue(controller.message.orEmpty().startsWith("Releve corrige"))
    }

    // ── Brouillons ───────────────────────────────────────────────────────────────────────────────────────

    @Test
    fun leavingAPointKeepsItsInputAsADraftWithoutAskingAnything() {
        controller.selectPoint(p1)
        controller.newIndexInput = "112,5"
        controller.remark = "compteur sale"
        controller.selectPoint(p2)
        assertEquals("Saisie gardee en brouillon.", controller.message)
        assertTrue(controller.hasDraft(p1))
        assertFalse(controller.hasDraft(p2))
        // Un brouillon n'est PAS un relevé : rien dans la file, rien envoyé.
        assertEquals(0, queued())

        controller.selectPoint(p1)
        // Les textes reviennent tels que saisis (virgule comprise).
        assertEquals("112,5", controller.newIndexInput)
        assertEquals("compteur sale", controller.remark)
        assertTrue(controller.draftRestored)
        assertNull(controller.message)
    }

    @Test
    fun anUntouchedFormLeavesNoDraft() {
        controller.selectPoint(p1)
        controller.selectPoint(p2)
        assertFalse(controller.hasDraft(p1))
        assertNull(controller.message)
    }

    @Test
    fun anInputBackToItsInitialStateDropsTheDraft() {
        controller.selectPoint(p1)
        controller.newIndexInput = "5"
        controller.selectPoint(p2)
        assertTrue(controller.hasDraft(p1))
        controller.selectPoint(p1)
        controller.newIndexInput = ""
        controller.nonBilledInput = "0,00" // « 0,00 » vaut « vide » pour la signature
        controller.selectPoint(p2)
        assertFalse(controller.hasDraft(p1))
        assertNull(controller.message)
    }

    @Test
    fun savingRemovesTheDraftAndTheNextPointComesWithItsOwnDraft() {
        controller.selectPoint(p2)
        controller.newIndexInput = "120"
        controller.selectPoint(p1)
        controller.newIndexInput = "110"
        assertTrue(controller.hasDraft(p2))
        assertTrue(controller.save())
        // p1 est enregistré : plus de brouillon pour lui ; p2 s'ouvre avec le sien.
        assertFalse(controller.hasDraft(p1))
        assertEquals("p2", selectedId())
        assertEquals("120", controller.newIndexInput)
        assertTrue(controller.draftRestored)
        assertEquals(1, queued())
    }

    @Test
    fun selectingTheSamePointAgainKeepsTheInput() {
        controller.selectPoint(p1)
        controller.newIndexInput = "110"
        controller.selectPoint(p1)
        assertEquals("110", controller.newIndexInput)
        assertFalse(controller.draftRestored)
        assertFalse(controller.hasDraft(p1))
    }

    @Test
    fun draftsBelongToACampaign() {
        val firstDate = controller.campaignDate
        controller.selectPoint(p1)
        controller.newIndexInput = "110"
        controller.changeCampaignDate("2026-01-05")
        // Autre campagne : le point reste ouvert mais vierge ; la saisie est restée dans la première.
        assertEquals("p1", selectedId())
        assertEquals("", controller.newIndexInput)
        assertFalse(controller.hasDraft(p1))
        assertEquals("Saisie gardee en brouillon.", controller.message)

        controller.changeCampaignDate(firstDate)
        assertEquals("110", controller.newIndexInput)
        assertTrue(controller.draftRestored)
    }

    @Test
    fun switchingOuvrageKeepsTheDraftOfTheCampaignThatWasLeft() {
        val other = point("q1", idxls = 1, name = "Delta")
        controller.ouvrages = controller.ouvrages + ouvrage("o2", other)
        controller.selectPoint(p1)
        controller.newIndexInput = "110"

        controller.selectOuvrage("o2")
        assertNull(controller.selectedPoint)
        assertEquals("Saisie gardee en brouillon.", controller.message)
        assertEquals("", controller.newIndexInput)

        controller.selectOuvrage("o1")
        controller.selectPoint(p1)
        assertEquals("110", controller.newIndexInput)
        assertTrue(controller.draftRestored)
    }

    @Test
    fun aDraftOlderThanThreeDaysIsDroppedWhenThePointOpens() {
        controller.selectPoint(p1)
        controller.newIndexInput = "110"
        controller.selectPoint(p2)
        assertTrue(controller.hasDraft(p1))

        now += ReadingDraftBook.MAX_AGE.inWholeMilliseconds + 1
        controller.selectPoint(p1)
        assertEquals("", controller.newIndexInput)
        assertFalse(controller.draftRestored)
        assertFalse(controller.hasDraft(p1))
    }

    @Test
    fun aDraftYoungerThanThreeDaysSurvives() {
        controller.selectPoint(p1)
        controller.newIndexInput = "110"
        controller.selectPoint(p2)
        now += ReadingDraftBook.MAX_AGE.inWholeMilliseconds - 1
        controller.selectPoint(p1)
        assertEquals("110", controller.newIndexInput)
    }

    @Test
    fun theDraftOfAPointRemovedFromTheCampaignIsPurged() {
        controller.selectPoint(p1)
        controller.newIndexInput = "110"
        controller.selectPoint(p2)
        assertTrue(controller.hasDraft(p1))

        // Le périmètre est resynchronisé : p1 n'est plus dans l'ouvrage.
        controller.ouvrages = listOf(ouvrage("o1", p2, p3))
        controller.selectPoint(p3)
        assertFalse(controller.hasDraft(p1))
    }

    @Test
    fun socialCardsAreKeptInTheDraftAndRemovedCardsAreIgnored() {
        val kiosk = point("k1", idxls = 4, name = "Kiosque", kiosque = true, cards = listOf("c1", "c2"))
        controller.ouvrages = listOf(ouvrage("o1", p1, p2, p3, kiosk))
        controller.selectPoint(kiosk)
        controller.addSocialCard(kiosk.getJSONArray("cartes_sociales").getJSONObject(0))
        controller.setSocialBidons("c1", 3)
        controller.selectPoint(p1)
        assertTrue(controller.hasDraft(kiosk))

        controller.selectPoint(kiosk)
        val card = assertNotNull(controller.socialCards.singleOrNull())
        assertEquals("c1", card.id)
        assertEquals(3, card.bidons)
        assertEquals("N-c1", card.numero)
        assertEquals("Benef c1", card.beneficiaire)

        // La carte c1 est retirée du point entre-temps : le brouillon ne la remet pas.
        controller.selectPoint(p1)
        kiosk.put("cartes_sociales", JSONArray().put(JSONObject().put("id", "c2").put("numero_carte", "N-c2").put("beneficiaire", "Benef c2")))
        controller.selectPoint(kiosk)
        assertTrue(controller.socialCards.isEmpty())
    }

    @Test
    fun theBaselineOfACorrectionIsTheQueuedReading() {
        saveReading(p1, "110") // ouvre p2
        controller.selectPoint(p1)
        assertTrue(controller.correcting)
        // Aucune modification : pas de brouillon, la valeur de la file reste la référence.
        controller.selectPoint(p2)
        assertFalse(controller.hasDraft(p1))

        controller.selectPoint(p1)
        controller.newIndexInput = "115"
        controller.selectPoint(p2)
        assertTrue(controller.hasDraft(p1))
        assertTrue(controller.hasPendingReading(p1))

        controller.selectPoint(p1)
        assertEquals("115", controller.newIndexInput)
        assertTrue(controller.draftRestored)
        assertTrue(controller.correcting)
        // La file n'a pas bougé tant que l'agent n'a pas enregistré.
        assertEquals(1, queued())
    }
}
