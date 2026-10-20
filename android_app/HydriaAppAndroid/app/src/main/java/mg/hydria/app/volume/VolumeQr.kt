package mg.hydria.app.volume

import org.json.JSONObject

object VolumeQr {
    fun find(raw: String, invoices: List<JSONObject>): JSONObject? =
        mg.hydria.shared.volume.VolumeQrGateway.find(raw, invoices)
}
