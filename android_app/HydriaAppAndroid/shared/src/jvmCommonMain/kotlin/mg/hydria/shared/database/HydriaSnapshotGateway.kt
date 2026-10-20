package mg.hydria.shared.database

import org.json.JSONObject

/**
 * Facade Android pour le snapshot decoupe en chunks (table snapshotChunks,
 * cf. Snapshot.sq). Miroir de TerrainDatabase.snapshot()/saveSnapshot()/
 * clearSnapshot() (app/) : le decoupage en chunks de 256 Ko evite les
 * limites de CursorWindow SQLite sur certains appareils pour un payload
 * JSON volumineux (le snapshot complet de prechargement offline).
 *
 * BRANCHEE SUR L'APP : OfflineStore.kt (app/) copie une fois le snapshot
 * existant au demarrage (flag "snapshot_migrated_v2") puis route get/set ici,
 * avec le meme filet de secours que HydriaSyncQueueGateway (repli total sur
 * TerrainDatabase pour toute la session si la migration echoue).
 */
object HydriaSnapshotGateway {
    private const val CHUNK_CHARS = 256 * 1024


    private fun db() = HydriaSharedDatabaseHolder.database

    fun snapshot(): JSONObject? {
        val builder = StringBuilder()
        db().snapshotQueries.selectAllOrdered().executeAsList().forEach { builder.append(it) }
        if (builder.isEmpty()) return null
        return runCatching { JSONObject(builder.toString()) }.getOrNull()
    }

    fun saveSnapshot(value: JSONObject?, now: Long = System.currentTimeMillis()) {
        val database = db()
        database.transaction {
            database.snapshotQueries.deleteAll()
            if (value != null) {
                val raw = value.toString()
                var offset = 0
                var index = 0L
                while (offset < raw.length) {
                    val end = (offset + CHUNK_CHARS).coerceAtMost(raw.length)
                    database.snapshotQueries.insertChunk(index, raw.substring(offset, end), now)
                    offset = end
                    index++
                }
            }
        }
    }

    fun clearSnapshot() {
        db().snapshotQueries.deleteAll()
    }
}
