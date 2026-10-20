package mg.hydria.shared.sync

import org.json.JSONArray
import org.json.JSONObject

object QueueOverviewGateway {
    fun isConflict(item: JSONObject): Boolean =
        QueueOverviewRules.isConflict(item.optJSONObject("payload")?.has("_sync_conflict") == true,
            item.optString("last_error"))

    /** Relevé que le serveur a refusé (HTTP 400, hors conflit) : le centre de synchronisation propose « Corriger ». */
    fun isServerRefusal(item: JSONObject): Boolean =
        QueueOverviewRules.isServerRefusal(item.optString("type"),
            item.optJSONObject("payload")?.has(QueueOverviewRules.REFUSED_KEY) == true,
            item.optJSONObject("payload")?.has("_sync_conflict") == true, item.optString("last_error"))

    fun summarize(pending: JSONArray): QueueOverview<JSONObject> =
        QueueOverviewRules.summarize((0 until pending.length()).mapNotNull { index ->
            pending.optJSONObject(index)?.let { item ->
                QueueItem(item,item.optString("type"),item.optString("last_error"),
                    item.optJSONObject("payload")?.has("_sync_conflict") == true)
            }
        })
}
