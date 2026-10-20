package mg.hydria.shared.rules.terrain

import org.json.JSONArray
import org.json.JSONObject

/**
 * Modifications de fiche Terrain faites depuis le téléphone (abonné, téléphone,
 * GPS, photo) d'un point d'eau (`point_id`) ou d'un équipement (`equipment_id`),
 * envoyées une par une à `/plannings/api/mobile/terrain/sync-item/`.
 */
object TerrainEditRules {
    private val TYPES = setOf("terrain_data", "terrain_photo")

    /** Opérations Terrain en file (en attente ou en erreur) visant cette fiche. */
    fun pendingFor(pending: JSONArray, kind: String, id: String): List<JSONObject> {
        val key = if (kind == "equipement") "equipment_id" else "point_id"
        return (0 until pending.length()).mapNotNull { pending.optJSONObject(it) }
            .filter { it.optString("type") in TYPES }
            .filter { it.optJSONObject("payload")?.optString(key) == id }
    }

    /**
     * Version de base envoyée pour détecter un conflit avec une modification web.
     * Si une autre modification de cette fiche attend déjà dans la file, c'est la
     * nôtre qui changera la version serveur : renvoyer l'ancienne version ferait
     * refuser la seconde opération en « conflit ». On n'envoie alors pas de version.
     */
    fun baseVersion(pending: JSONArray, kind: String, id: String, knownVersion: String): String =
        if (pendingFor(pending, kind, id).isEmpty() && !knownVersion.equals("null", ignoreCase = true)) knownVersion else ""

    /** Libellés courts des modifications en attente (« GPS », « photo », « téléphone », « abonné »). */
    fun pendingLabels(pending: JSONArray, kind: String, id: String): List<String> =
        pendingFor(pending, kind, id).flatMap { item ->
            val payload = item.optJSONObject("payload") ?: JSONObject()
            buildList {
                if (item.optString("type") == "terrain_photo") add("photo")
                if (payload.has("latitude")) add("GPS")
                if (payload.has("telephone")) add("téléphone")
                if (payload.has("subscriber_name")) add("abonné")
            }
        }.distinct()
}
