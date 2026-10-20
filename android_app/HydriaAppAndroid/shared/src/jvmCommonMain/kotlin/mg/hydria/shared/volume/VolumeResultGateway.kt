package mg.hydria.shared.volume

import org.json.JSONObject

object VolumeResultGateway {
    fun acceptedEntries(
        account: String, payload: JSONObject, response: JSONObject,
        read: (String) -> JSONObject?, now: () -> String,
    ): List<Triple<String, String, JSONObject>> {
        VolumeConfirmationRules.requireAccount(payload.getString("account_key"), account)
        VolumeConfirmationRules.requireUuid(response.optString("local_uuid"), payload.getString("local_uuid"))
        val id = payload.getString("local_uuid")
        val invoices = response.getJSONArray("factures")
        val entries = mutableListOf<Triple<String, String, JSONObject>>()
        for (i in 0 until invoices.length()) {
            val invoice = invoices.getJSONObject(i)
            entries += Triple(account, "invoice:${invoice.getString("id")}", invoice)
        }
        read("recap:$id")?.let {
            entries += Triple(account, "recap:$id", it.put("etat", "synchronisee")
                .put("diamex_temporaire_id", response.optString("diamex_temporaire_id")))
        }
        entries += Triple(account, "receipt:$id", JSONObject(response.toString()).put("factures", payload.getJSONArray("factures")))
        val audit = read("audit:$id") ?: JSONObject().put("payload", payload)
        entries += Triple(account, "audit:$id", audit.put("etat", "synchronisee").put("updated_at", now()))
        return entries
    }

    fun reviewedEntries(
        account: String, id: String, note: String, payload: JSONObject,
        read: (String) -> JSONObject?, now: () -> String,
    ): List<Triple<String, String, JSONObject>> {
        VolumeConfirmationRules.requireConflict(payload.has("_sync_conflict"))
        val audit = read("audit:$id") ?: JSONObject().put("payload", payload)
        val entries = mutableListOf<Triple<String, String, JSONObject>>()
        entries += Triple(account, "audit:$id", audit.put("etat", "verification_manuelle").put("note", note.trim())
            .put("updated_at", now()))
        read("recap:$id")?.let { entries += Triple(account, "recap:$id", it.put("etat", "verification_manuelle").put("note", note.trim())) }
        return entries
    }

    fun recordFailure(
        id: String, payload: JSONObject, status: Int, body: JSONObject, error: String,
        updatePayload: (String, JSONObject) -> Unit,
        markFailed: (String, String) -> Unit,
        read: (String) -> JSONObject?,
        write: (String, JSONObject) -> Unit,
    ) {
        if (status == 409) {
            payload.put("_sync_conflict", body)
            updatePayload(id, payload)
        }
        markFailed(id, error)
        read("recap:$id")?.let { write("recap:$id", it.put("etat", VolumeConfirmationRules.failedRecapState(status)).put("erreur", error)) }
        val audit = read("audit:$id") ?: JSONObject().put("payload", payload)
        write("audit:$id", audit.put("etat", "refusee").put("erreur", error))
    }
}
