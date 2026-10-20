package mg.hydria.shared.volume

import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal

object VolumeOperationGateway {
    fun payload(action: String, invoices: List<JSONObject>, extra: JSONObject, id: String, account: String): JSONObject {
        val payload = JSONObject(extra.toString()).put("local_uuid", id).put("action", action)
            .put("account_key", account).put("factures", JSONArray().apply {
                invoices.forEach { put(JSONObject().put("id", it.getString("id")).put("version", it.getString("version"))
                    .put("montant", it.getString("montant"))) }
            })
        return payload
    }

    /**
     * « Ouvrage · mois · montant Ar » d'une opération en file, pour préfixer ses erreurs de
     * synchronisation (CALC_VOL-02). Le payload ne porte que des identifiants de factures : l'ouvrage
     * et le mois viennent de la première facture du cache local ([read] = `invoice:<id>`), le montant
     * est la somme des montants envoyés. Les éléments inconnus sont simplement omis.
     */
    fun describe(payload: JSONObject, read: (String) -> JSONObject?): String {
        val rows = payload.optJSONArray("factures") ?: JSONArray()
        var total = BigDecimal.ZERO
        for (i in 0 until rows.length()) {
            total += rows.optJSONObject(i)?.optString("montant")?.toBigDecimalOrNull() ?: BigDecimal.ZERO
        }
        val firstId = rows.optJSONObject(0)?.optString("id").orEmpty()
        val first = if (firstId.isBlank()) null else read("invoice:$firstId")
        return listOf(first?.optString("ouvrage").orEmpty(), first?.optString("mois").orEmpty(),
            "${total.stripTrailingZeros().toPlainString()} Ar")
            .filter { it.isNotBlank() }.joinToString(" · ")
    }

    fun localEntries(account: String, id: String, payload: JSONObject, recap: JSONObject?, now: () -> String):
        List<Triple<String, String, JSONObject>> {
        val entries = mutableListOf<Triple<String, String, JSONObject>>()
        entries += Triple(account, "audit:$id", JSONObject().put("payload", payload).put("etat", "en_attente")
            .put("created_at", now()))
        if (recap != null) {
            entries += Triple(account, "recap:$id", JSONObject(recap.toString()).put("local_uuid", id))
            entries += Triple(account, "last_recap:${recap.getString("ouvrage_id")}:${recap.getString("mois")}", JSONObject().put("id", id))
        }
        return entries
    }
}
