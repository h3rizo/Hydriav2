package mg.hydria.shared.volume

import org.json.JSONObject

object VolumeQrGateway {
    fun find(raw: String, invoices: List<JSONObject>): JSONObject? = VolumeQrRules.find(raw,
        invoices.map { VolumeQrInvoice(it,it.optString("id"),it.optString("mois"),it.optString("ouvrage_id"),it.optString("numero")) })
}
