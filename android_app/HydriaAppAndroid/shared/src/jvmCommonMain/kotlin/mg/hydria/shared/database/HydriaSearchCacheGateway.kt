package mg.hydria.shared.database

import org.json.JSONObject

/**
 * Facade Android pour le cache de recherche (table searchCache, cf.
 * SearchCache.sq). Miroir de TerrainDatabase.saveSearchCache()/
 * searchCache()/searchCacheUpdatedAt() (app/).
 *
 * BRANCHEE SUR L'APP : simple cache jetable (aucune migration de donnees
 * necessaire - un cache vide au premier demarrage est un etat normal, la
 * valeur est reconstruite au prochain appel reseau). Cf. OfflineStore.kt
 * (useNewSearchCache) et HydriaSyncQueueGateway pour le detail de la
 * strategie generale de bascule (filet de secours par runCatching).
 */
object HydriaSearchCacheGateway {

    private fun db() = HydriaSharedDatabaseHolder.database

    fun save(key: String, payload: JSONObject, now: Long = System.currentTimeMillis()) {
        db().searchCacheQueries.upsert(key, payload.toString(), now)
    }

    fun payload(key: String): JSONObject? =
        db().searchCacheQueries.selectPayload(key).executeAsOneOrNull()?.let {
            runCatching { JSONObject(it) }.getOrNull()
        }

    fun updatedAt(key: String): Long? =
        db().searchCacheQueries.selectUpdatedAt(key).executeAsOneOrNull()
}
