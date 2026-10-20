package mg.hydria.shared.rules.terrain

import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import mg.hydria.shared.terrain.*

data class TerrainBatchTask(val item: JSONObject, val work: JSONObject, val category: String)

/** Adaptateur JSON et horloge locale pour les règles Terrain communes. */
object TerrainRules {
    private fun objects(array: JSONArray?): List<JSONObject> =
        if (array == null) emptyList() else (0 until array.length()).map { array.getJSONObject(it) }
    fun remainingTasks(stats: JSONObject): Int = TerrainTaskRules.remainingTasks(TerrainTaskRules.statisticKeys.map { stats.optInt(it) })
    fun ouvrageAgeYears(work: JSONObject): Int? = TerrainTaskRules.ageYears(
        if (work.has("age_annees") && !work.isNull("age_annees")) work.optInt("age_annees", -1) else null,
        listOf("annee_realisation", "annee_realisation_avant").mapNotNull { key ->
            if (!work.has(key) || work.isNull(key)) null else work.opt(key)?.toString()?.trim()?.toIntOrNull()
        }, LocalDate.now().year)
    fun ouvrageAgeLabel(work: JSONObject): String = TerrainTaskRules.ageLabel(ouvrageAgeYears(work))
    private fun point(item: JSONObject) = TerrainPoint(item, item.optBoolean("has_coordinates"), item.optBoolean("has_subscriber_name"), item.optBoolean("has_photo"))
    fun buildTourTasks(terrain: JSONObject): List<TerrainBatchTask> = TerrainTaskRules.buildTourTasks(
        objects(terrain.optJSONArray("ouvrages")).map { work ->
            TerrainWork(work, objects(work.optJSONArray("points_eau")).map(::point), objects(work.optJSONArray("equipements")).map(::point))
        }).map { TerrainBatchTask(it.item, it.work, it.category) }
    fun localDownstream(work: JSONObject, meterId: String, after: LocalDate?, until: LocalDate): Double =
        TerrainTaskRules.localDownstream(objects(work.optJSONArray("points_eau")).filter { it.optString("compteur_tete_id") == meterId }.map { point ->
            DownstreamPoint(point.optString("compteur_tete_id"), objects(point.optJSONArray("historique_recent")).map { reading ->
                DownstreamReading(reading.optString("date"), reading.optDouble("consommation"))
            })
        }, meterId, after?.toString(), until.toString())

    /**
     * Périmètre affiché du suivi terrain. Si `etendu`, renvoie le terrain complet
     * avec `stats_perimetre_etendu` promu en `stats` ; sinon ne garde que les ouvrages
     * `responsable_direct` (champ absent = direct, pour ne rien masquer avant une
     * synchronisation) et laisse `stats` (déjà calculé serveur sur ce sous-ensemble)
     * tel quel. Repris tel quel de MainActivity.terrainForPerimetre().
     */
    fun perimeter(terrain: JSONObject, etendu: Boolean): JSONObject {
        // Copie superficielle : seules les clés de premier niveau changent. Une copie
        // profonde (toString + reparse) de tout le terrain bloquait le fil principal
        // au démarrage sur les gros périmètres (ANR).
        fun shallowCopy() = JSONObject().also { copy -> terrain.keys().forEach { copy.put(it, terrain.opt(it)) } }
        if (etendu) {
            val out = shallowCopy()
            terrain.optJSONObject("stats_perimetre_etendu")?.let { out.put("stats", it) }
            return out
        }
        val all = terrain.optJSONArray("ouvrages") ?: JSONArray()
        val directs = JSONArray()
        for (i in 0 until all.length()) {
            val work = all.optJSONObject(i) ?: continue
            if (work.optBoolean("responsable_direct", true)) directs.put(work)
        }
        return shallowCopy().apply { put("ouvrages", directs) }
    }
}
