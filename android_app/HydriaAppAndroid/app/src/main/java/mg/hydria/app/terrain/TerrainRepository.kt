package mg.hydria.app.terrain

import mg.hydria.app.OfflineStore
import org.json.JSONArray
import org.json.JSONObject

/**
 * Repository d'ecriture locale (optimiste) pour le domaine Terrain/Releves :
 * applique un changement immediatement dans le snapshot local (store.snapshot)
 * avant meme la confirmation serveur, pour que l'UI reflete l'action sans
 * attendre la synchronisation. Extrait de MainActivity ; ne depend que
 * d'OfflineStore, pas d'Android (View/Context), ce qui le rend portable vers
 * un module commonMain une fois OfflineStore remplace par un repository
 * SQLDelight.
 *
 * Ces fonctions ne declenchent pas elles-memes de rafraichissement d'UI :
 * applyLocalTerrainCompletion renvoie un Boolean indiquant si un compteur de
 * completude a change (l'appelant, MainActivity, decide alors d'appeler
 * updateStatus()). Comportement strictement identique a l'ancien code de
 * MainActivity : seul l'endroit ou vit le code a change.
 */
object TerrainRepository {

    fun applyLocalFlowMeasurement(store: OfflineStore, workId: String, date: String, flow: Double) {
        val snapshot = store.snapshot ?: return
        val terrain = snapshot.optJSONObject("terrain") ?: return
        val works = terrain.optJSONArray("ouvrages") ?: return
        for (wi in 0 until works.length()) {
            val work = works.getJSONObject(wi)
            if (work.optString("id") != workId) continue
            val history = work.optJSONArray("debits_source_recents") ?: JSONArray().also { work.put("debits_source_recents", it) }
            val hadNoMeasure = history.length() == 0
            val updated = JSONArray().put(JSONObject().put("id", "local").put("date", date).put("debit_l_s", flow).put("remarque", ""))
            for (index in 0 until minOf(history.length(), 19)) updated.put(history.getJSONObject(index))
            work.put("debits_source_recents", updated)
                .put("last_flow_measurement_date", date)
                .put("flow_measurement_overdue", false)
            if (hadNoMeasure) {
                val workStats = work.optJSONObject("stats") ?: JSONObject()
                val globalStats = terrain.optJSONObject("stats") ?: JSONObject()
                workStats.put("captages_sans_mesure", (workStats.optInt("captages_sans_mesure") - 1).coerceAtLeast(0))
                globalStats.put("captages_sans_mesure", (globalStats.optInt("captages_sans_mesure") - 1).coerceAtLeast(0))
            }
            break
        }
        store.snapshot = snapshot
    }

    fun applyLocalHeadReading(
        store: OfflineStore,
        workId: String, meterId: String, date: String, previousIndex: Double, newIndex: Double,
        volumeHead: Double, volumeDownstream: Double, gap: Double,
    ) {
        val snapshot = store.snapshot ?: return
        val works = snapshot.optJSONObject("terrain")?.optJSONArray("ouvrages") ?: return
        for (wi in 0 until works.length()) {
            val work = works.getJSONObject(wi)
            if (work.optString("id") != workId) continue
            val meters = work.optJSONArray("compteurs_tete") ?: continue
            for (mi in 0 until meters.length()) {
                val meter = meters.getJSONObject(mi)
                if (meter.optString("id") != meterId) continue
                val history = meter.optJSONArray("historique_recent") ?: JSONArray()
                val updated = JSONArray().put(JSONObject()
                    .put("id", "local").put("date", date)
                    .put("ancien_index", previousIndex).put("nouvel_index", newIndex)
                    .put("volume_tete", volumeHead).put("volume_aval", volumeDownstream)
                    .put("ecart_volume", gap))
                for (index in 0 until minOf(history.length(), 19)) updated.put(history.getJSONObject(index))
                meter.put("historique_recent", updated)
                break
            }
            break
        }
        store.snapshot = snapshot
    }

    /** Retourne true si un compteur de completude a ete decremente (l'appelant doit alors rafraichir le statut). */
    fun applyLocalTerrainCompletion(store: OfflineStore, item: JSONObject, work: JSONObject, category: String): Boolean {
        if (category == "equipment_gps") return applyLocalEquipmentGps(store, item, work)
        val statKey = when (category) {
            "gps" -> "points_sans_coordonnees"
            "subscriber" -> "points_sans_nom_abonne"
            "point_photo" -> "points_sans_photo"
            "equipment_photo" -> "equipements_sans_photo"
            else -> return false
        }
        val snapshot = store.snapshot ?: return false
        val terrain = snapshot.optJSONObject("terrain") ?: return false
        val works = terrain.optJSONArray("ouvrages") ?: return false
        var storedWork: JSONObject? = null
        for (index in 0 until works.length()) {
            val candidate = works.getJSONObject(index)
            if (candidate.optString("id") == work.optString("id")) { storedWork = candidate; break }
        }
        val targetWork = storedWork ?: return false
        val arrayKey = if (category == "equipment_photo") "equipements" else "points_eau"
        val storedItems = targetWork.optJSONArray(arrayKey) ?: return false
        var storedItem: JSONObject? = null
        for (index in 0 until storedItems.length()) {
            val candidate = storedItems.getJSONObject(index)
            if (candidate.optString("id") == item.optString("id")) { storedItem = candidate; break }
        }
        val targetItem = storedItem ?: return false
        val wasMissing = when (category) {
            "gps" -> !targetItem.optBoolean("has_coordinates")
            "subscriber" -> !targetItem.optBoolean("has_subscriber_name")
            else -> !targetItem.optBoolean("has_photo")
        }
        when (category) {
            "gps" -> targetItem.put("has_coordinates", true)
                .put("latitude", item.optDouble("latitude"))
                .put("longitude", item.optDouble("longitude"))
                .put("coordinates_accuracy", item.optDouble("coordinates_accuracy"))
            "subscriber" -> targetItem.put("has_subscriber_name", true)
                .put("nom", item.optString("nom"))
                .put("telephone", item.optString("telephone"))
            else -> targetItem.put("has_photo", true)
        }
        if (!wasMissing) { store.snapshot = snapshot; return false }
        val globalStats = terrain.optJSONObject("stats") ?: JSONObject()
        val workStats = targetWork.optJSONObject("stats") ?: JSONObject()
        globalStats.put(statKey, (globalStats.optInt(statKey) - 1).coerceAtLeast(0))
        workStats.put(statKey, (workStats.optInt(statKey) - 1).coerceAtLeast(0))
        store.snapshot = snapshot
        return true
    }

    /**
     * Après un envoi réussi, le serveur a une nouvelle version de la fiche (`server_updated_at`).
     * On la reporte dans la tournée locale : sinon l'opération suivante sur la même fiche partirait
     * avec l'ancienne version et serait refusée en conflit tant que la tournée n'est pas rechargée.
     */
    fun applyServerVersion(store: OfflineStore, payload: JSONObject, body: JSONObject) {
        val version = body.optString("server_updated_at")
        if (version.isBlank()) return
        val (arrayKey, id) = when {
            payload.has("equipment_id") -> "equipements" to payload.optString("equipment_id")
            payload.has("point_id") -> "points_eau" to payload.optString("point_id")
            else -> return
        }
        val snapshot = store.snapshot ?: return
        val works = snapshot.optJSONObject("terrain")?.optJSONArray("ouvrages") ?: return
        for (wi in 0 until works.length()) {
            val items = works.getJSONObject(wi).optJSONArray(arrayKey) ?: continue
            for (ii in 0 until items.length()) {
                val item = items.getJSONObject(ii)
                if (item.optString("id") != id) continue
                item.put("updated_at", version)
                store.snapshot = snapshot
                return
            }
        }
    }

    /** Coordonnées d'un équipement saisies hors ligne : pas de compteur de complétude, juste la fiche locale. */
    private fun applyLocalEquipmentGps(store: OfflineStore, item: JSONObject, work: JSONObject): Boolean {
        val snapshot = store.snapshot ?: return false
        val works = snapshot.optJSONObject("terrain")?.optJSONArray("ouvrages") ?: return false
        for (wi in 0 until works.length()) {
            val candidate = works.getJSONObject(wi)
            if (candidate.optString("id") != work.optString("id")) continue
            val equipments = candidate.optJSONArray("equipements") ?: return false
            for (ei in 0 until equipments.length()) {
                val equipment = equipments.getJSONObject(ei)
                if (equipment.optString("id") != item.optString("id")) continue
                equipment.put("has_coordinates", true)
                    .put("latitude", item.optDouble("latitude"))
                    .put("longitude", item.optDouble("longitude"))
                    .put("coordinates_accuracy", item.optDouble("coordinates_accuracy"))
                store.snapshot = snapshot
                return false
            }
        }
        return false
    }

    fun findTerrainPoint(store: OfflineStore, pointId: String): JSONObject? {
        val works = store.snapshot?.optJSONObject("terrain")?.optJSONArray("ouvrages") ?: return null
        for (workIndex in 0 until works.length()) {
            val points = works.getJSONObject(workIndex).optJSONArray("points_eau") ?: continue
            for (pointIndex in 0 until points.length()) {
                val point = points.getJSONObject(pointIndex)
                if (point.optString("id") == pointId) return point
            }
        }
        return null
    }

    fun applyLocalReadingPointEnrichment(
        store: OfflineStore,
        pointId: String,
        latitude: Double? = null,
        longitude: Double? = null,
        accuracy: Double? = null,
        photoCaptured: Boolean = false,
        telephone: String? = null,
    ) {
        val snapshot = store.snapshot ?: return

        fun updatePoint(point: JSONObject) {
            if (latitude != null && longitude != null) {
                point.put("has_coordinates", true)
                    .put("latitude", latitude)
                    .put("longitude", longitude)
                    .put("coordinates_accuracy", accuracy)
            }
            if (photoCaptured) point.put("has_photo", true)
            if (!telephone.isNullOrBlank()) point.put("telephone", telephone)
        }

        // Jeu compact utilise par la page Releve.
        val readingWorks = snapshot.optJSONArray("ouvrages") ?: JSONArray()
        for (workIndex in 0 until readingWorks.length()) {
            val points = readingWorks.getJSONObject(workIndex).optJSONArray("points_eau") ?: continue
            for (pointIndex in 0 until points.length()) {
                val point = points.getJSONObject(pointIndex)
                if (point.optString("id") == pointId) updatePoint(point)
            }
        }

        // Jeu Terrain et compteurs de completude.
        val terrain = snapshot.optJSONObject("terrain")
        val terrainWorks = terrain?.optJSONArray("ouvrages") ?: JSONArray()
        for (workIndex in 0 until terrainWorks.length()) {
            val work = terrainWorks.getJSONObject(workIndex)
            val points = work.optJSONArray("points_eau") ?: continue
            for (pointIndex in 0 until points.length()) {
                val point = points.getJSONObject(pointIndex)
                if (point.optString("id") != pointId) continue
                val gpsWasMissing = !point.optBoolean("has_coordinates")
                val photoWasMissing = !point.optBoolean("has_photo")
                updatePoint(point)
                val workStats = work.optJSONObject("stats") ?: JSONObject()
                val globalStats = terrain?.optJSONObject("stats") ?: JSONObject()
                if (gpsWasMissing && latitude != null && longitude != null) {
                    workStats.put("points_sans_coordonnees", (workStats.optInt("points_sans_coordonnees") - 1).coerceAtLeast(0))
                    globalStats.put("points_sans_coordonnees", (globalStats.optInt("points_sans_coordonnees") - 1).coerceAtLeast(0))
                }
                if (photoWasMissing && photoCaptured) {
                    workStats.put("points_sans_photo", (workStats.optInt("points_sans_photo") - 1).coerceAtLeast(0))
                    globalStats.put("points_sans_photo", (globalStats.optInt("points_sans_photo") - 1).coerceAtLeast(0))
                }
            }
        }
        store.snapshot = snapshot
    }
}
