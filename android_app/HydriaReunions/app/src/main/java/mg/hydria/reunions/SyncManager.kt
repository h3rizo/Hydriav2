package mg.hydria.reunions

import org.json.JSONArray
import org.json.JSONObject

/**
 * Applique les réponses bootstrap/changes de l'API (voir HydriaReunionsApi)
 * sur la base locale (ReunionsDatabase). Un seul point d'entrée par famille
 * d'endpoints pour ne jamais désynchroniser le mapping JSON -> tables.
 */
class SyncManager(private val db: ReunionsDatabase) {

    fun applyReunionsBootstrap(payload: JSONObject) {
        db.clearAll()
        storeArray(payload.optJSONArray("representants"), "representantes")
        storeArray(payload.optJSONArray("avis"), "avis", parentKey = "representant_id")

        val reunions = payload.optJSONArray("reunions")
        if (reunions != null) {
            for (i in 0 until reunions.length()) {
                val reunion = reunions.getJSONObject(i)
                val reunionId = reunion.getString("id")
                db.upsert("reunions", reunionId, null, reunion, reunion.optString("updated_at"))
                reunion.optJSONArray("participants")?.let { storeNested(it, "participants", reunionId) }
                reunion.optJSONArray("decisions")?.let { storeNested(it, "decisions", reunionId) }
                reunion.optJSONArray("pieces_jointes")?.let { storeNested(it, "pieces_jointes", reunionId) }
            }
        }
        db.setMeta("reunions_last_cursor", payload.optString("cursor", ""))
    }

    fun applyReunionsChanges(changes: JSONObject, cursor: String) {
        storeArray(changes.optJSONArray("representants"), "representantes")
        storeArray(changes.optJSONArray("avis"), "avis", parentKey = "representant_id")
        storeArray(changes.optJSONArray("reunions"), "reunions")
        storeArray(changes.optJSONArray("decisions"), "decisions", parentKey = "reunion_id")
        storeArray(changes.optJSONArray("participants"), "participants", parentKey = "reunion_id")
        storeArray(changes.optJSONArray("pieces_jointes"), "pieces_jointes", parentKey = "reunion_id")
        db.setMeta("reunions_last_cursor", cursor)
    }

    fun applyMessagingBootstrap(payload: JSONObject) {
        storeArray(payload.optJSONArray("conversations"), "conversations")
        val messagesMap = payload.optJSONObject("messages")
        messagesMap?.keys()?.forEach { convId ->
            storeNested(messagesMap.getJSONArray(convId), "messages", convId)
        }
        val employeId = payload.optString("employe_id")
        if (employeId.isNotBlank()) db.setMeta("messaging_employe_id", employeId)
        payload.optJSONArray("employes_annuaire")?.let { db.setMeta("messaging_employes_annuaire", it.toString()) }
        db.setMeta("messaging_last_cursor", payload.optString("cursor", ""))
    }

    fun applyMessagingChanges(changes: JSONObject, cursor: String) {
        storeArray(changes.optJSONArray("conversations"), "conversations")
        changes.optJSONArray("messages")?.let { arr ->
            for (i in 0 until arr.length()) {
                val message = arr.getJSONObject(i)
                db.upsert("messages", message.getString("id"), message.getString("conversation_id"), message, message.optString("date_envoi"))
            }
        }
        db.setMeta("messaging_last_cursor", cursor)
    }

    fun lastReunionsCursor(): String = db.getMeta("reunions_last_cursor") ?: ""
    fun lastMessagingCursor(): String = db.getMeta("messaging_last_cursor") ?: ""

    /** Identifiant (string) de l'employe connecte, tel que renvoye par messaging/bootstrap —
     * doublon de SessionManager.employeId (deja rempli au login), garde ici en repli. */
    fun currentEmployeId(): String? = db.getMeta("messaging_employe_id")

    /** Annuaire du personnel (id + nom), pour demarrer une nouvelle conversation directe. */
    fun employesAnnuaire(): List<JSONObject> {
        val raw = db.getMeta("messaging_employes_annuaire") ?: return emptyList()
        val array = try { JSONArray(raw) } catch (_: Exception) { return emptyList() }
        return (0 until array.length()).map { array.getJSONObject(it) }
    }

    private fun storeArray(array: JSONArray?, table: String, parentKey: String? = null) {
        array ?: return
        for (i in 0 until array.length()) {
            val obj = array.getJSONObject(i)
            val parentId = parentKey?.let { obj.optString(it, null) }
            db.upsert(table, obj.getString("id"), parentId, obj, obj.optString("updated_at", obj.optString("created_at", null)))
        }
    }

    private fun storeNested(array: JSONArray, table: String, parentId: String) {
        for (i in 0 until array.length()) {
            val obj = array.getJSONObject(i)
            db.upsert(table, obj.getString("id"), parentId, obj, obj.optString("updated_at", obj.optString("created_at", null)))
        }
    }
}
