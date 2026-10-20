package mg.hydria.shared.database

import org.json.JSONObject

/**
 * Facade Android pour le cache cle-valeur volumetrique (table volumeCache,
 * cf. Volume.sq). Miroir des primitives read()/write()/history() de
 * VolumeRepository.kt (app/) - l'orchestration metier (savePack,
 * reconciliation d'audit) reste dans VolumeRepository, qui compose ces
 * primitives.
 *
 * BRANCHEE SUR L'APP : cf. OfflineStore.kt (useNewVolumeCache) et
 * HydriaSyncQueueGateway pour le detail de la strategie generale de bascule
 * (migration unique au demarrage de toutes les entrees existantes, filet de
 * secours par runCatching).
 */
object HydriaVolumeCacheGateway {

    private fun db() = HydriaSharedDatabaseHolder.database

    fun write(account: String, key: String, payload: JSONObject) {
        db().volumeQueries.upsert(account, key, payload.toString())
    }

    /**
     * Ecriture groupee dans une seule transaction SQLDelight - utilisee par
     * VolumeRepository pour les operations qui ecrivent plusieurs entrees a
     * la fois (ex: un pack de factures), afin de conserver l'atomicite que
     * l'ancien code obtenait via une transaction SQLite brute.
     */
    fun writeBatch(entries: List<Triple<String, String, JSONObject>>) {
        val database = db()
        database.transaction {
            entries.forEach { (account, key, payload) -> database.volumeQueries.upsert(account, key, payload.toString()) }
        }
    }

    fun read(account: String, key: String): JSONObject? =
        db().volumeQueries.selectPayload(account, key).executeAsOneOrNull()?.let {
            runCatching { JSONObject(it) }.getOrNull()
        }

    fun history(account: String): List<JSONObject> =
        db().volumeQueries.selectAuditHistory(account).executeAsList().mapNotNull {
            runCatching { JSONObject(it) }.getOrNull()
        }
}
