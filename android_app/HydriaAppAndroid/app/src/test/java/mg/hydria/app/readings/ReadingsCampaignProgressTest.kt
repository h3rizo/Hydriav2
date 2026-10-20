package mg.hydria.app.readings

import mg.hydria.shared.rules.readings.ReadingsRules
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Caractérisation de MainActivity.renderCampaignSetup.monthProgress() extraite dans `shared`. */
class ReadingsCampaignProgressTest {
    private fun point(id: String, aRelever: Boolean? = null, releveMois: Boolean = false) =
        JSONObject().put("id", id).apply {
            if (aRelever != null) put("a_relever", aRelever)
            if (releveMois) put("releve_mois_courant", true)
        }

    private fun reading(pointId: String, date: String) = JSONObject()
        .put("type", "reading")
        .put("payload", JSONObject().put("point_eau_id", pointId).put("date_releve", date))

    @Test fun countsServerDoneAndQueuedThisMonthOverActivePoints() {
        val ouvrage = JSONObject().put("points_eau", JSONArray()
            .put(point("p1", releveMois = true))               // relevé serveur
            .put(point("p2"))                                  // a_relever absent -> actif
            .put(point("p3", aRelever = true))                 // en file ce mois
            .put(point("p4", aRelever = true))                 // en file mois précédent -> non compté
            .put(point("p5", aRelever = false)))               // inactif -> exclu du total
        val pending = JSONArray()
            .put(reading("p3", "2026-09-04"))
            .put(reading("p4", "2026-08-30"))
            .put(reading("inconnu", "2026-09-04"))
            .put(JSONObject().put("type", "save_repair").put("payload", JSONObject().put("point_eau_id", "p2").put("date_releve", "2026-09-01")))

        assertEquals(2 to 4, ReadingsRules.monthProgress(ouvrage, pending, 2026, 9))
    }

    @Test fun returnsZeroWhenNoActivePoint() {
        val ouvrage = JSONObject().put("points_eau", JSONArray().put(point("p1", aRelever = false)))
        assertEquals(0 to 0, ReadingsRules.monthProgress(ouvrage, JSONArray(), 2026, 9))
        assertEquals(0 to 0, ReadingsRules.monthProgress(JSONObject(), JSONArray(), 2026, 9))
    }

    @Test fun ignoresUnparseableQueueDates() {
        val ouvrage = JSONObject().put("points_eau", JSONArray().put(point("p1", aRelever = true)))
        val pending = JSONArray().put(reading("p1", "pas-une-date"))
        assertEquals(0 to 1, ReadingsRules.monthProgress(ouvrage, pending, 2026, 9))
    }
}
