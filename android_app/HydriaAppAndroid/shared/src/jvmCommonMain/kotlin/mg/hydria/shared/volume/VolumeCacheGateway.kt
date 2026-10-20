package mg.hydria.shared.volume

import org.json.JSONArray
import org.json.JSONObject

object VolumeCacheGateway {
    fun packEntries(account: String, pack: JSONObject): List<Triple<String, String, JSONObject>> {
        val invoices = pack.getJSONArray("factures")
        val entries = mutableListOf<Triple<String, String, JSONObject>>()
        for (i in 0 until invoices.length()) {
            val invoice = invoices.getJSONObject(i)
            entries += Triple(account, "invoice:${invoice.getString("id")}", invoice)
        }
        // Keep each invoice in its own row to stay below CursorWindow limits.
        val metadata = JSONObject(pack.toString()).put("factures", JSONArray().apply {
            for (i in 0 until invoices.length()) put(JSONObject().put("id", invoices.getJSONObject(i).getString("id")))
        })
        entries += Triple(account, "pack:${pack.getString("ouvrage_id")}:${pack.getString("mois")}", metadata)
        return entries
    }

    fun invoices(pack: JSONObject, read: (String) -> JSONObject?): List<JSONObject> {
        val rows = pack.getJSONArray("factures")
        return (0 until rows.length()).map { index ->
            val original = rows.getJSONObject(index)
            read("invoice:${original.getString("id")}") ?: original
        }.sortedWith(compareBy<JSONObject> { it.optString("idxls").toLongOrNull() ?: Long.MAX_VALUE }.thenBy { it.optString("abonne") })
    }

    /**
     * Ordre d'impression des factures : numerique par IDXLS, independamment
     * de la parcelle - plus simple pour les agents qui distribuent. Factures
     * sans IDXLS en dernier, abonne en departage.
     * Meme regle que getRelevesOrdreImpression() de workflow_facturation.html.
     */
    fun printOrder(invoices: List<JSONObject>): List<JSONObject> {
        val collator = java.text.Collator.getInstance(java.util.Locale.FRENCH).apply { strength = java.text.Collator.PRIMARY }
        return invoices.sortedWith(
            compareBy<JSONObject> { it.optString("idxls").trim().toLongOrNull() ?: Long.MAX_VALUE }
                .thenBy(collator) { it.optString("abonne").trim() }
        )
    }

    fun pending(rows: JSONArray, account: String): List<JSONObject> {
        return (0 until rows.length()).map { rows.getJSONObject(it) }.filter {
            it.optString("type") == "volume" && it.getJSONObject("payload").optString("account_key") == account
        }
    }

    fun actions(invoiceId: String, pending: List<JSONObject>): Set<String> = pending.filter { item ->
        val rows = item.getJSONObject("payload").getJSONArray("factures")
        (0 until rows.length()).any { rows.getJSONObject(it).getString("id") == invoiceId }
    }.map { it.getJSONObject("payload").getString("action") }.toSet()

}
