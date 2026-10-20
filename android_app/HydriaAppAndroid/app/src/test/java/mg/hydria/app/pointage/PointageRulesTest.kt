package mg.hydria.app.pointage

import mg.hydria.app.pointage.PointageRules.Verdict
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalTime
import java.time.ZonedDateTime

class PointageRulesTest {
    private fun at(hour: Int, minute: Int = 0) =
        ZonedDateTime.of(2026, 9, 21, hour, minute, 0, 0, PointageRules.ZONE)

    private val village = PointageRules.Village("Ambato", -18.9, 47.5)

    @Test fun fenetresHorairesIdentiquesAuServeur() {
        assertEquals("matin", PointageRules.creneauPour(LocalTime.of(10, 0))?.type)
        assertEquals("matin", PointageRules.creneauPour(LocalTime.of(12, 0))?.type)
        assertEquals("aprem", PointageRules.creneauPour(LocalTime.of(15, 30))?.type)
        assertEquals("nuit", PointageRules.creneauPour(LocalTime.of(21, 0))?.type)
        listOf(LocalTime.of(9, 59), LocalTime.of(12, 1), LocalTime.of(14, 59), LocalTime.of(18, 59), LocalTime.of(21, 1))
            .forEach { assertNull(it.toString(), PointageRules.creneauPour(it)) }
    }

    @Test fun haversineUnDegreDeLatitude() {
        assertEquals(111_200.0, PointageRules.haversineM(-18.0, 47.5, -19.0, 47.5), 300.0)
    }

    @Test fun refuseHorsCreneau() {
        val v = PointageRules.verdict(-18.9, 47.5, listOf(village), at(13, 0))
        assertTrue(v is Verdict.Refuse)
    }

    @Test fun refuseAuDela3Km() {
        val v = PointageRules.verdict(-18.9 - 0.03, 47.5, listOf(village), at(11, 0))
        assertTrue(v is Verdict.Refuse)
        assertTrue((v as Verdict.Refuse).message.contains("Ambato"))
    }

    @Test fun accepteDansLes3Km() {
        val v = PointageRules.verdict(-18.9 - 0.02, 47.5, listOf(village), at(16, 0))
        assertTrue(v is Verdict.Ok)
        assertEquals("aprem", (v as Verdict.Ok).creneau.type)
    }

    @Test fun indetermineSansVillageEnCache() {
        assertTrue(PointageRules.verdict(-18.9, 47.5, emptyList(), at(11, 0)) is Verdict.Indetermine)
    }

    @Test fun villagesDuJourIgnoreLesVillagesSansGps() {
        val today = JSONObject(
            """{"plannings":[{"villages":[{"id":"a","nom":"A","lat":-18.9,"lng":47.5},{"id":"b","nom":"B","lat":null,"lng":null}]}]}"""
        )
        assertEquals(listOf(PointageRules.Village("A", -18.9, 47.5)), PointageRules.villagesDuJour(today))
    }

    @Test fun formatDistance() {
        assertEquals("850 m", PointageRules.formatDistance(850.0))
        assertEquals("4,2 km", PointageRules.formatDistance(4200.0))
    }

    @Test fun echecActualisationDistingueReseauEtServeur() {
        assertTrue(PointageRules.refreshFailureNote(null, null, "timeout", online = false).startsWith("Hors ligne"))
        assertTrue(PointageRules.refreshFailureNote(null, null, "timeout", online = true).startsWith("Serveur injoignable"))
        assertTrue(PointageRules.refreshFailureNote(401, "Token invalide", null, true).contains("reconnectez"))
        assertTrue(PointageRules.refreshFailureNote(403, "Aucun employé lié à ce compte.", null, true).contains("Aucun employé"))
        val panne = PointageRules.refreshFailureNote(500, "Service indisponible", null, true)
        assertTrue(panne.contains("HTTP 500") && !panne.startsWith("Hors ligne"))
    }

    @Test fun boutonGriseAuDelaDe3Km() {
        // ~0,01 degre de latitude = ~1,1 km ; 0,05 = ~5,6 km
        assertNull(PointageRules.tropLoin(-18.91, 47.5, 20.0, listOf(village)))
        val loin = PointageRules.tropLoin(-18.95, 47.5, 20.0, listOf(village))
        assertEquals("Ambato", loin?.first?.nom)
        assertTrue(loin!!.second > PointageRules.DISTANCE_MAX_M)
        // Village le plus proche retenu : un seul village dans la zone suffit
        assertNull(PointageRules.tropLoin(-18.95, 47.5, 20.0, listOf(village, PointageRules.Village("Proche", -18.951, 47.5))))
        // Pas de conclusion sans village geolocalise ni avec un signal imprecis
        assertNull(PointageRules.tropLoin(-18.95, 47.5, 20.0, emptyList()))
        assertNull(PointageRules.tropLoin(-18.95, 47.5, 500.0, listOf(village)))
        assertNull(PointageRules.tropLoin(-18.95, 47.5, null, listOf(village)))
    }

    @Test fun seulLeCreneauDeLHeureActuelleEstAffiche() {
        assertEquals("matin", PointageRules.creneauActuel(at(11, 0))?.type)
        assertEquals("aprem", PointageRules.creneauActuel(at(15, 0))?.type)
        assertEquals("nuit", PointageRules.creneauActuel(at(21, 0))?.type)
        assertNull(PointageRules.creneauActuel(at(13, 0)))
        assertEquals("aprem", PointageRules.prochainCreneau(at(13, 0))?.type)
        assertEquals("matin", PointageRules.prochainCreneau(at(7, 0))?.type)
        assertNull(PointageRules.prochainCreneau(at(21, 30)))
    }

    private fun planning(id: String, lat: Double, prevuMatin: Boolean) = JSONObject()
        .put("planning_id", id)
        .put("villages", org.json.JSONArray().put(JSONObject().put("id", id).put("nom", id).put("lat", lat).put("lng", 47.5)))
        .put("creneaux", org.json.JSONArray().put(JSONObject().put("type", "matin").put("prevu", prevuMatin)))

    @Test fun planningChoisiAutomatiquementCommeLeServeur() {
        val today = JSONObject().put("plannings", org.json.JSONArray()
            .put(planning("proche", -18.901, false))      // ~110 m
            .put(planning("prevu", -18.92, true))         // ~2,2 km, créneau déclaré
            .put(planning("loin", -19.2, true)))          // ~33 km : hors zone
        // Le créneau déclaré l'emporte sur la distance, tant qu'on est à moins de 3 km
        assertEquals("prevu", PointageRules.planningPourPointage(today, -18.9, 47.5, "matin"))
        // Sans planning déclaré dans la zone : le plus proche
        val sansPrevu = JSONObject().put("plannings", org.json.JSONArray()
            .put(planning("a", -18.91, false)).put(planning("b", -18.901, false)))
        assertEquals("b", PointageRules.planningPourPointage(sansPrevu, -18.9, 47.5, "matin"))
        // Rien à moins de 3 km : c'est le serveur qui tranche
        assertNull(PointageRules.planningPourPointage(today, -18.0, 47.5, "matin"))
    }
}
