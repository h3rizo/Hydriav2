package mg.hydria.shared.volume

import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal

/** Shared, testable rules for the three ouvrage/month screens. */
object VolumeWorkflowGateway {
    fun amount(row: JSONObject): BigDecimal = row.optString("montant").toBigDecimalOrNull() ?: BigDecimal.ZERO
    fun total(rows: List<JSONObject>) = VolumeRules.total(rows, BigDecimal.ZERO, ::amount) { a, b -> a + b }
    fun calculable(row: JSONObject) = VolumeRules.calculable(!row.isNull("montant"), row.optString("erreur_calcul"))
    fun unpointed(rows: List<JSONObject>) = rows.filterNot { it.optBoolean("pointee") }
    fun collectable(row: JSONObject, actions: Set<String>) = VolumeRules.collectable(
        row.optBoolean("pointee"), row.optBoolean("encaissee"), row.optBoolean("validee"), actions)

    /** Une facture est en conflit serveur si une operation en file, marquee
     * `_sync_conflict`, contient son id dans `factures`. Comportement identique
     * a l'ancien VolumeActivity.conflicted() : seul l'endroit ou vit le code change. */
    fun conflicted(row: JSONObject, pending: List<JSONObject>): Boolean =
        pending.any { operation ->
            val payload = operation.getJSONObject("payload")
            if (!payload.has("_sync_conflict")) return@any false
            val items = payload.optJSONArray("factures") ?: return@any false
            (0 until items.length()).any { items.getJSONObject(it).optString("id") == row.optString("id") }
        }

    /** Libelle d'etat affiche sous chaque facture des trois ecrans ouvrage/mois.
     * Repris tel quel de VolumeActivity.state() ; l'ordre des cas est significatif
     * (conflit > pointage > encaissement > validation > a facturer). */
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

    /**
     * Lignes DiameX d'un pack fusionnées avec l'état `pointee` : une ligne est
     * pointée si une opération en file la cible (`payload.diamex_id`) ou si une
     * facture déjà pointée porte le même `numero_diamex`/`base_diamex`. Les objets
     * renvoyés sont des copies (l'original du pack n'est pas muté). Repris tel quel
     * de VolumeActivity.entries().
     */
    fun reconciledEntries(diamex: JSONArray, pending: List<JSONObject>, invoices: List<JSONObject>): List<JSONObject> {
        val pendingIds = pending.map { it.getJSONObject("payload").optString("diamex_id") }.toSet()
        return (0 until diamex.length()).map { i ->
            JSONObject(diamex.getJSONObject(i).toString()).apply {
                val pointed = optString("id") in pendingIds || invoices.any { r ->
                    r.optBoolean("pointee") &&
                        r.optString("numero_diamex") == optString("numero") &&
                        r.optString("base_diamex") == optString("base")
                }
                if (pointed) put("pointee", true)
            }
        }
    }

    fun matches(rows: List<JSONObject>, entry: JSONObject?): Boolean {
        if (rows.isEmpty() || entry == null) return false
        return VolumeRules.matches(rows.size, total(rows), amount(entry), BigDecimal.ZERO, entry.optBoolean("pointee"))
    }
    fun recap(rows: List<JSONObject>, allRows: List<JSONObject>, date: String, journal: String, now: () -> String = { java.time.Instant.now().toString() }): JSONObject {
        VolumeRules.requireSingleScope(rows.map { it.optString("ouvrage_id") to it.optString("mois") })
        return JSONObject().put("ouvrage", rows.first().optString("ouvrage"))
            .put("ouvrage_id", rows.first().getString("ouvrage_id")).put("mois", rows.first().getString("mois"))
            .put("date", date).put("journal", journal).put("total", total(rows).toPlainString())
            .put("etat", "en_attente").put("generated_at", now())
            .put("factures", JSONArray().apply { rows.forEach { row ->
                put(JSONObject().apply { listOf("id", "numero", "idxls", "abonne", "mois", "type_pe", "montant").forEach { put(it, row.optString(it)) } })
            } }).put("idxls_pointes", JSONArray(allRows.filter { it.optBoolean("pointee") }.map { it.optString("idxls") }.distinct()))
    }
}
