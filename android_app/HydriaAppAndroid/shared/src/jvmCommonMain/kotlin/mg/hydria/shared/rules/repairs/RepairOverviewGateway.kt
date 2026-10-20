package mg.hydria.shared.rules.repairs

import mg.hydria.shared.repairs.RepairEntry
import mg.hydria.shared.repairs.RepairOverview
import org.json.JSONObject
import java.util.Locale

object RepairOverviewGateway {
    private fun entry(item: JSONObject) = RepairEntry(item, item.optString("id"), RepairRules.workKey(item),
        item.optString("ouvrage_nom").lowercase(Locale.FRANCE), RepairRules.activityLabel(item).lowercase(Locale.FRANCE),
        RepairRules.dateKey(item), RepairRules.criticality(item), RepairRules.isCompleted(item), item.optBoolean("hors_perimetre"))
    fun visible(items: List<JSONObject>, pendingIds: Set<String>, showCompleted: Boolean, showOutside: Boolean) =
        RepairOverview.visible(items.map(::entry), pendingIds, showCompleted, showOutside)
    fun prepare(items: List<JSONObject>, pendingIds: Set<String>) = RepairOverview.prepare(items.map(::entry), pendingIds)
}
