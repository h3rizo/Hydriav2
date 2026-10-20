package mg.hydria.app.volume

import mg.hydria.shared.volume.VolumeWorkflowGateway
import org.json.JSONObject
import java.math.BigDecimal

object VolumeWorkflow {
    enum class Stage(val title: String) { BILLING("Facturation"), COLLECTION("Encaissement"), POINTING("Pointage DiameX") }
    fun amount(row: JSONObject): BigDecimal = VolumeWorkflowGateway.amount(row)
    fun total(rows: List<JSONObject>) = VolumeWorkflowGateway.total(rows)
    fun calculable(row: JSONObject) = VolumeWorkflowGateway.calculable(row)
    fun unpointed(rows: List<JSONObject>) = VolumeWorkflowGateway.unpointed(rows)
    fun collectable(row: JSONObject, actions: Set<String>) = VolumeWorkflowGateway.collectable(row, actions)
    fun conflicted(row: JSONObject, pending: List<JSONObject>) = VolumeWorkflowGateway.conflicted(row, pending)
    fun statusLabel(row: JSONObject, actions: Set<String>, conflicted: Boolean) =
        VolumeWorkflowGateway.statusLabel(row, actions, conflicted)
    fun matches(rows: List<JSONObject>, entry: JSONObject?) = VolumeWorkflowGateway.matches(rows, entry)
    fun recap(rows: List<JSONObject>, allRows: List<JSONObject>, date: String, journal: String) =
        VolumeWorkflowGateway.recap(rows, allRows, date, journal)
}
