package mg.hydria.shared.network

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Conversion JsonObject -> formulaire x-www-form-urlencoded, utilisee par
 * plusieurs clients Ktor (Navigation, Terrain) pour reproduire a l'identique
 * HydriaApi.jsonForm() : chaque cle non prefixee par "_sync_" (metadonnees
 * de file d'attente locale, jamais envoyees au serveur) et non nulle est
 * transmise telle quelle en chaine.
 */
fun JsonObject.toSyncForm(): Map<String, String> = buildMap {
    this@toSyncForm.entries.forEach { (key, value) ->
        if (key.startsWith("_sync_")) return@forEach
        if (value is JsonNull) return@forEach
        val content = (value as? JsonPrimitive)?.contentOrNull ?: value.toString()
        put(key, content)
    }
}
