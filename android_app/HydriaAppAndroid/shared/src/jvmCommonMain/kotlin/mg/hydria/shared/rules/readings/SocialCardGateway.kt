package mg.hydria.shared.rules.readings

import mg.hydria.shared.readings.*
import org.json.JSONArray
import org.json.JSONObject

object SocialCardGateway {
    fun prepare(selected: List<JSONObject>, linkedIds: Set<String>): SocialCardPreparation =
        SocialCardSelection.prepare(selected.map {
            SocialCardQuantity(it.optString("id"), it.optInt("quantite_bidons", 0))
        }, linkedIds)

    fun payload(prepared: SocialCardPreparation): JSONArray {
        require(prepared.error == null) { "Cartes sociales invalides" }
        return JSONArray().apply {
            prepared.cards.forEach { card ->
                put(JSONObject().put("id", card.id).put("quantite_bidons", card.quantity).put("volume_total", card.volume))
            }
        }
    }
}
