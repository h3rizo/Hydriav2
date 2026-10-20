package mg.hydria.shared.database

import org.json.JSONArray
import org.json.JSONObject

/**
 * Facade Android pour la table `syncQueue` SQLDelight (Phase 2 de la
 * migration KMP, cf. shared/src/commonMain/sqldelight/.../SyncQueue.sq).
 *
 * Miroir fonctionnel de la partie "file de synchronisation" de
 * TerrainDatabase.kt (app/) : les autres tables (snapshot, geo/navigation,
 * recherche, calculatrice, volume) restent gerees par TerrainDatabase pour
 * l'instant - migration table par table, incrementale (cf. HydriaSnapshotGateway,
 * HydriaSearchCacheGateway, HydriaCalculatorGateway pour la suite).
 *
 * BRANCHEE SUR L'APP : OfflineStore.kt (app/) migre une fois au demarrage
 * (flag "sync_queue_migrated_v2") puis route toutes les operations ici, avec
 * filet de secours - si la migration echoue, on reste sur TerrainDatabase
 * pour toute la session (meme principe que la bascule deja faite pour le
 * login).
 *
 * Objet plutot que typealias : un objet Kotlin natif ne se relaie pas via
 * typealias (regle etablie ailleurs dans le projet). N'expose que des types
 * deja visibles cote app (String, Int, org.json.JSONObject/JSONArray) pour
 * eviter toute nouvelle dependance Gradle sur app/build.gradle.kts (les
 * dependances de shared sont en `implementation`, donc invisibles a app).
 */
object HydriaSyncQueueGateway {

    private fun db() = HydriaSharedDatabaseHolder.database

    fun enqueue(localUuid: String, operationType: String, payload: JSONObject, now: Long = System.currentTimeMillis()) {
        db().syncQueueQueries.insertPending(
            localUuid = localUuid,
            operationType = operationType,
            payload = payload.toString(),
            createdAt = now,
            updatedAt = now,
        )
    }

    /**
     * Variante idempotente de [enqueue] (INSERT OR IGNORE), reservee a la
     * migration unique depuis l'ancienne base (TerrainDatabase.sync_queue) :
     * peut etre retentee sans risque de doublon si une tentative precedente
     * s'est arretee en cours de route (cf. OfflineStore.migrateSyncQueueIfNeeded).
     */
    fun enqueueIfAbsent(localUuid: String, operationType: String, payload: JSONObject, now: Long = System.currentTimeMillis()) {
        db().syncQueueQueries.insertPendingIfAbsent(
            localUuid = localUuid,
            operationType = operationType,
            payload = payload.toString(),
            createdAt = now,
            updatedAt = now,
        )
    }

    fun pending(): JSONArray {
        val result = JSONArray()
        db().syncQueueQueries.selectPendingOrError().executeAsList().forEach { row ->
            result.put(
                JSONObject()
                    .put("local_uuid", row.localUuid)
                    .put("type", row.operationType)
                    .put("payload", JSONObject(row.payload))
                    .put("status", row.status)
                    .put("retry_count", row.retryCount)
                    .put("last_error", row.lastError ?: "")
            )
        }
        return result
    }

    fun pendingCount(): Int =
        db().syncQueueQueries.countPendingOrError().executeAsOne().toInt()

    fun markSynchronizing(localUuid: String) {
        db().syncQueueQueries.markSyncing(localUuid)
    }

    fun markFailed(localUuid: String, error: String) {
        val database = db()
        database.syncQueueQueries.markStatus(status = "error", lastError = error.take(1000), localUuid = localUuid)
        database.syncQueueQueries.incrementRetry(localUuid)
    }

    fun updatePayload(localUuid: String, payload: JSONObject, now: Long = System.currentTimeMillis()) {
        db().syncQueueQueries.updatePayload(payload = payload.toString(), updatedAt = now, localUuid = localUuid)
    }

    fun remove(localUuid: String) {
        db().syncQueueQueries.deleteByUuid(localUuid)
    }

    fun recoverInterrupted() {
        db().syncQueueQueries.resetStuckSyncing()
    }
}
