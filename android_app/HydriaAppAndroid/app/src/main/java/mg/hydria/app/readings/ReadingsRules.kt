package mg.hydria.app.readings

import org.json.JSONArray
import org.json.JSONObject

/**
 * Relais fin vers le module partage `shared` (Phase 0 de la migration
 * KMP). Le code metier reel a demenage vers
 * shared/src/jvmCommonMain/kotlin/mg/hydria/shared/rules/readings/ReadingsRules.kt ;
 * ce fichier ne fait plus que le pointer.
 */
object ReadingsRules {
    fun consumption(newIndex: Double, previousIndex: Double): Double =
        mg.hydria.shared.rules.readings.ReadingsRules.consumption(newIndex, previousIndex)

    fun socialCardVolume(bidonCount: Int): Double =
        mg.hydria.shared.rules.readings.ReadingsRules.socialCardVolume(bidonCount)

    fun socialCardsVolume(cards: List<JSONObject>): Double =
        mg.hydria.shared.rules.readings.ReadingsRules.socialCardsVolume(cards)

    fun billedVolume(consumption: Double, socialCardsVolume: Double, nonBillable: Double): Double =
        mg.hydria.shared.rules.readings.ReadingsRules.billedVolume(consumption, socialCardsVolume, nonBillable)

    fun monthProgress(ouvrage: JSONObject, pending: JSONArray, year: Int, month: Int): Pair<Int, Int> =
        mg.hydria.shared.rules.readings.ReadingsRules.monthProgress(ouvrage, pending, year, month)
}
