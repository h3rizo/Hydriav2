package mg.hydria.shared.rules.readings

import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import mg.hydria.shared.readings.ReadingValidation

/**
 * Regles de calcul pures pour l'etape "releve" du workflow Facturation
 * (portees depuis mg.hydria.app.readings.ReadingsRules dans le cadre de la
 * Phase 0 de la migration KMP).
 */
object ReadingsRules {
    fun consumption(newIndex: Double, previousIndex: Double): Double = ReadingValidation.consumption(newIndex, previousIndex)

    fun socialCardVolume(bidonCount: Int): Double = ReadingValidation.socialCardVolume(bidonCount)

    fun socialCardsVolume(cards: List<JSONObject>): Double = ReadingValidation.socialCardsVolume(cards.map { it.optDouble("volume_total", 0.0) })

    fun billedVolume(consumption: Double, socialCardsVolume: Double, nonBillable: Double): Double =
        ReadingValidation.billedVolume(consumption, socialCardsVolume, nonBillable)

    /**
     * Progression des relevés du mois pour un ouvrage : `(points relevés, points actifs)`.
     * Un point actif (`a_relever` absent = actif) est compté comme relevé s'il porte
     * `releve_mois_courant` (côté serveur) ou si une opération `reading` en file le
     * cible avec une `date_releve` dans le mois [year]/[month]. Repris tel quel de
     * MainActivity.renderCampaignSetup.monthProgress().
     */
    fun monthProgress(ouvrage: JSONObject, pending: JSONArray, year: Int, month: Int): Pair<Int, Int> {
        val pointsArray = ouvrage.optJSONArray("points_eau") ?: JSONArray()
        val active = (0 until pointsArray.length())
            .mapNotNull { pointsArray.optJSONObject(it) }
            .filter { it.optBoolean("a_relever", true) }
        if (active.isEmpty()) return 0 to 0
        val activeIds = active.map { it.optString("id") }.toSet()
        val queuedThisMonth = mutableSetOf<String>()
        for (i in 0 until pending.length()) {
            val row = pending.optJSONObject(i) ?: continue
            if (row.optString("type") != "reading") continue
            val payload = row.optJSONObject("payload") ?: continue
            val pointId = payload.optString("point_eau_id")
            if (pointId !in activeIds) continue
            val date = runCatching { LocalDate.parse(payload.optString("date_releve")) }.getOrNull() ?: continue
            if (date.year == year && date.monthValue == month) queuedThisMonth.add(pointId)
        }
        val done = active.count { it.optBoolean("releve_mois_courant", false) || it.optString("id") in queuedThisMonth }
        return done to active.size
    }
}
