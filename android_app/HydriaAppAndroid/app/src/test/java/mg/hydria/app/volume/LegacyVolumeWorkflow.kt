package mg.hydria.app.volume

import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal

/** Shared, testable rules for the three ouvrage/month screens. */
object LegacyVolumeWorkflow {
    enum class Stage(val title: String) { BILLING("Facturation"), COLLECTION("Encaissement"), POINTING("Pointage DiameX") }
    fun amount(row: JSONObject): BigDecimal = row.optString("montant").toBigDecimalOrNull() ?: BigDecimal.ZERO
    fun total(rows: List<JSONObject>) = rows.fold(BigDecimal.ZERO) { sum, row -> sum + amount(row) }
    fun calculable(row: JSONObject) = !row.isNull("montant") && row.optString("erreur_calcul").isBlank()
    fun unpointed(rows: List<JSONObject>) = rows.filterNot { it.optBoolean("pointee") }
    fun collectable(row: JSONObject, actions: Set<String>) = !row.optBoolean("pointee") && !row.optBoolean("encaissee") &&
        actions.none { it == "collect" || it == "point" } && (row.optBoolean("validee") || "validate" in actions)
    fun matches(rows: List<JSONObject>, entry: JSONObject?) = rows.isNotEmpty() && entry != null &&
        total(rows).compareTo(amount(entry)) == 0 && total(rows) > BigDecimal.ZERO && !entry.optBoolean("pointee")
    // Repris tel quel de l'ancien VolumeActivity.conflicted() / .state().
    fun conflicted(row: JSONObject, pending: List<JSONObject>) = pending.any { operation ->
        val payload = operation.getJSONObject("payload")
        val items = payload.getJSONArray("factures")
        payload.has("_sync_conflict") && (0 until items.length()).any { items.getJSONObject(it).optString("id") == row.optString("id") }
    }
    fun statusLabel(row: JSONObject, actions: Set<String>, conflicted: Boolean): String = when {
        conflicted -> "Conflit serveur · à vérifier dans l'historique"
        row.optBoolean("pointee") -> "Pointée DiameX ${row.optString("numero_diamex")}"
        "point" in actions -> "Pointage en attente de synchronisation"
        row.optBoolean("encaissee") -> "Déjà encaissée · non pointée"
        "collect" in actions -> "Encaissement local en attente"
        row.optBoolean("validee") -> "Validée · non pointée"
        "validate" in actions -> "Validation locale en attente"
        else -> "À facturer"
    }
    // Repris tel quel de l'ancien VolumeActivity.entries().
    fun reconciledEntries(diamex: JSONArray, pending: List<JSONObject>, invoices: List<JSONObject>): List<JSONObject> {
        val pendingIds = pending.map { it.getJSONObject("payload").optString("diamex_id") }.toSet()
        return (0 until diamex.length()).map { i ->
            JSONObject(diamex.getJSONObject(i).toString()).apply {
                if (optString("id") in pendingIds || invoices.any { r -> r.optBoolean("pointee") && r.optString("numero_diamex") == optString("numero") && r.optString("base_diamex") == optString("base") }) put("pointee", true)
            }
        }
    }
    fun recap(rows: List<JSONObject>, allRows: List<JSONObject>, date: String, journal: String): JSONObject {
        require(rows.isNotEmpty())
        require(rows.map { it.optString("ouvrage_id") to it.optString("mois") }.toSet().size == 1)
        return JSONObject().put("ouvrage", rows.first().optString("ouvrage"))
            .put("ouvrage_id", rows.first().getString("ouvrage_id")).put("mois", rows.first().getString("mois"))
            .put("date", date).put("journal", journal).put("total", total(rows).toPlainString())
            .put("etat", "en_attente").put("generated_at", "fixed-time")
            .put("factures", JSONArray().apply { rows.forEach { row ->
                put(JSONObject().apply { listOf("id", "numero", "idxls", "abonne", "mois", "type_pe", "montant").forEach { put(it, row.optString(it)) } })
            } }).put("idxls_pointes", JSONArray(allRows.filter { it.optBoolean("pointee") }.map { it.optString("idxls") }.distinct()))
    }
}
