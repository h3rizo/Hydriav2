package mg.hydria.app

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/** Stockage local natif, leger et transactionnel du snapshot et de la file. */
class TerrainDatabase(context: Context) : SQLiteOpenHelper(context, "hydria_terrain.db", null, 10) {
    companion object {
        // Une ligne SQLite trop volumineuse ne tient pas dans le CursorWindow
        // de certains téléphones. Le snapshot est donc découpé en petits blocs.
        private const val SNAPSHOT_CHUNK_CHARS = 256 * 1024
        private const val MAX_MIGRATION_CHUNKS = 128
    }

    override fun onCreate(db: SQLiteDatabase) {
        createSnapshotChunksTable(db)
        db.execSQL(
            """CREATE TABLE sync_queue (
                local_uuid TEXT PRIMARY KEY,
                operation_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )""".trimIndent()
        )
        db.execSQL("CREATE INDEX idx_sync_queue_status_created ON sync_queue(status, created_at)")
        createNavigationTables(db)
        createSearchCacheTable(db)
        createCalculatorTables(db)
        createVolumeTables(db)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) {
            createSnapshotChunksTable(db)
            // Migration entièrement exécutée par SQLite : le gros TEXT n'est
            // jamais chargé dans un CursorWindow Java pendant la conversion.
            for (index in 0 until MAX_MIGRATION_CHUNKS) {
                val offset = index * SNAPSHOT_CHUNK_CHARS + 1
                db.execSQL(
                    """INSERT OR REPLACE INTO snapshot_chunks(chunk_index, payload, updated_at)
                       SELECT $index, substr(payload, $offset, $SNAPSHOT_CHUNK_CHARS), updated_at
                       FROM snapshot
                       WHERE id=1 AND length(payload) >= $offset""".trimIndent()
                )
            }
            db.execSQL("DROP TABLE IF EXISTS snapshot")
        }
        if (oldVersion < 3) createNavigationTables(db)
        if (oldVersion == 3) {
            db.execSQL("ALTER TABLE geo_entities ADD COLUMN is_field_marker INTEGER NOT NULL DEFAULT 0")
        }
        if (oldVersion < 5) createPlacementCandidatesTable(db)
        if (oldVersion == 5) {
            db.execSQL("ALTER TABLE geo_placement_candidates ADD COLUMN has_photo INTEGER NOT NULL DEFAULT 0")
            db.execSQL("ALTER TABLE geo_placement_candidates ADD COLUMN served_village_ids TEXT")
            db.execSQL("ALTER TABLE geo_placement_candidates ADD COLUMN ouvrage_id TEXT")
        }
        if (oldVersion == 6) {
            db.execSQL("ALTER TABLE geo_placement_candidates ADD COLUMN served_village_ids TEXT")
            db.execSQL("ALTER TABLE geo_placement_candidates ADD COLUMN ouvrage_id TEXT")
        }
        if (oldVersion < 8) createSearchCacheTable(db)
        if (oldVersion < 9) createCalculatorTables(db)
        if (oldVersion < 10) createVolumeTables(db)
    }

    private fun createVolumeTables(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE IF NOT EXISTS volume_cache (account TEXT NOT NULL, cache_key TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(account, cache_key))")
    }

    private fun createSnapshotChunksTable(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS snapshot_chunks (
                chunk_index INTEGER PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )""".trimIndent()
        )
    }

    private fun createNavigationTables(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS geo_entities (
                spatial_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                type_label TEXT,
                code TEXT,
                ouvrage_id TEXT,
                organisation_id TEXT,
                village_id TEXT,
                latitude REAL,
                longitude REAL,
                altitude REAL,
                accuracy_m REAL,
                capture_method TEXT,
                captured_at TEXT,
                server_updated_at TEXT,
                local_updated_at INTEGER NOT NULL,
                sync_state TEXT NOT NULL DEFAULT 'synced',
                is_archived INTEGER NOT NULL DEFAULT 0,
                is_field_marker INTEGER NOT NULL DEFAULT 0,
                UNIQUE(category, entity_id)
            )""".trimIndent()
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_geo_entities_category ON geo_entities(category, is_archived)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_geo_entities_work ON geo_entities(ouvrage_id, category)")
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS geo_landmark_types (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                icon_key TEXT NOT NULL,
                color_hex TEXT NOT NULL,
                display_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                server_updated_at TEXT
            )""".trimIndent()
        )
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS geo_position_history (
                local_uuid TEXT PRIMARY KEY,
                entity_kind TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                old_latitude REAL,
                old_longitude REAL,
                new_latitude REAL NOT NULL,
                new_longitude REAL NOT NULL,
                altitude REAL,
                accuracy_m REAL,
                capture_method TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                sync_state TEXT NOT NULL DEFAULT 'pending',
                created_at INTEGER NOT NULL
            )""".trimIndent()
        )
        // Certains constructeurs Android livrent SQLite sans le module RTree.
        // Deux index B-tree gardent les recherches par rectangle rapides tout en
        // garantissant que la migration fonctionne sur tous les appareils.
        db.execSQL("DROP TRIGGER IF EXISTS geo_entities_rtree_insert")
        db.execSQL("DROP TRIGGER IF EXISTS geo_entities_rtree_update")
        db.execSQL("DROP TRIGGER IF EXISTS geo_entities_rtree_delete")
        db.execSQL("DROP TABLE IF EXISTS geo_entity_rtree")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_geo_entities_latitude ON geo_entities(latitude)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_geo_entities_longitude ON geo_entities(longitude)")
        createPlacementCandidatesTable(db)
        val landmarkTypes = listOf(
            "pont" to "Pont", "sentier" to "Sentier", "intersection" to "Intersection",
            "rond_point" to "Rond-point", "batiment" to "Bâtiment", "ecole" to "École",
            "sante" to "Centre de santé", "riviere" to "Rivière",
            "passage_difficile" to "Passage difficile", "depart" to "Point de départ", "autre" to "Autre",
        )
        landmarkTypes.forEachIndexed { index, (id, name) ->
            db.execSQL(
                "INSERT OR IGNORE INTO geo_landmark_types(id,name,icon_key,color_hex,display_order) VALUES(?,?,?,?,?)",
                arrayOf<Any>(id, name, id, "#58D594", index),
            )
        }
    }

    private fun createPlacementCandidatesTable(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS geo_placement_candidates (
                entity_id TEXT NOT NULL,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                code TEXT,
                village_name TEXT,
                reference_latitude REAL,
                reference_longitude REAL,
                has_photo INTEGER NOT NULL DEFAULT 0,
                served_village_ids TEXT,
                ouvrage_id TEXT,
                server_updated_at TEXT,
                PRIMARY KEY(category, entity_id)
            )""".trimIndent()
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_geo_candidates_category ON geo_placement_candidates(category)")
    }

    private fun createSearchCacheTable(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS search_cache (
                cache_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )""".trimIndent()
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_search_cache_updated ON search_cache(updated_at)")
    }

    private fun createCalculatorTables(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS calculator_state (
                account_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )""".trimIndent()
        )
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS salary_calculation_config (
                account_key TEXT NOT NULL,
                organisation_key TEXT NOT NULL,
                formula_version INTEGER NOT NULL,
                config_version TEXT NOT NULL,
                checksum TEXT NOT NULL,
                payload TEXT NOT NULL,
                effective_from TEXT,
                effective_to TEXT,
                server_updated_at TEXT NOT NULL,
                synced_at INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(account_key, organisation_key, config_version)
            )""".trimIndent()
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_salary_config_active ON salary_calculation_config(account_key, organisation_key, is_active)")
    }

    fun saveCalculatorState(accountKey: String, payload: JSONObject) {
        require(accountKey.isNotBlank())
        writableDatabase.insertWithOnConflict(
            "calculator_state", null,
            ContentValues().apply {
                put("account_key", accountKey)
                put("payload", payload.toString())
                put("updated_at", System.currentTimeMillis())
            },
            SQLiteDatabase.CONFLICT_REPLACE,
        )
    }

    fun calculatorState(accountKey: String): JSONObject? {
        if (accountKey.isBlank()) return null
        return readableDatabase.rawQuery(
            "SELECT payload FROM calculator_state WHERE account_key=?",
            arrayOf(accountKey),
        ).use { cursor ->
            if (!cursor.moveToFirst()) null
            else runCatching { JSONObject(cursor.getString(0)) }.getOrNull()
        }
    }

    fun clearCalculatorMemory(accountKey: String) {
        if (accountKey.isNotBlank()) writableDatabase.delete("calculator_state", "account_key=?", arrayOf(accountKey))
    }

    fun activeSalaryConfig(accountKey: String, organisationKey: String = "global"): JSONObject? {
        if (accountKey.isBlank()) return null
        return readableDatabase.rawQuery(
            """SELECT payload, synced_at FROM salary_calculation_config
               WHERE account_key=? AND organisation_key=? AND is_active=1
               ORDER BY server_updated_at DESC LIMIT 1""".trimIndent(),
            arrayOf(accountKey, organisationKey),
        ).use { cursor ->
            if (!cursor.moveToFirst()) null else runCatching {
                JSONObject(cursor.getString(0)).put("local_synced_at", cursor.getLong(1))
            }.getOrNull()
        }
    }

    fun salaryConfigChecksum(accountKey: String, organisationKey: String = "global"): String =
        activeSalaryConfig(accountKey, organisationKey)?.optString("checksum").orEmpty()

    fun replaceActiveSalaryConfig(accountKey: String, configuration: JSONObject) {
        require(accountKey.isNotBlank())
        val organisation = configuration.getString("organisation")
        val database = writableDatabase
        database.beginTransaction()
        try {
            database.update(
                "salary_calculation_config",
                ContentValues().apply { put("is_active", 0) },
                "account_key=? AND organisation_key=?",
                arrayOf(accountKey, organisation),
            )
            database.insertOrThrow(
                "salary_calculation_config", null,
                ContentValues().apply {
                    put("account_key", accountKey)
                    put("organisation_key", organisation)
                    put("formula_version", configuration.getInt("formula_version"))
                    put("config_version", configuration.getString("version"))
                    put("checksum", configuration.getString("checksum"))
                    put("payload", configuration.toString())
                    put("effective_from", configuration.optString("effective_from"))
                    put("effective_to", configuration.optString("effective_until").takeIf { it.isNotBlank() })
                    put("server_updated_at", configuration.getString("server_updated_at"))
                    put("synced_at", System.currentTimeMillis())
                    put("is_active", 1)
                },
            )
            database.setTransactionSuccessful()
        } finally {
            database.endTransaction()
        }
    }

    fun saveSearchCache(key: String, payload: JSONObject) {
        writableDatabase.insertWithOnConflict(
            "search_cache", null,
            ContentValues().apply {
                put("cache_key", key)
                put("payload", payload.toString())
                put("updated_at", System.currentTimeMillis())
            },
            SQLiteDatabase.CONFLICT_REPLACE,
        )
    }

    fun searchCache(key: String): JSONObject? = readableDatabase.rawQuery(
        "SELECT payload FROM search_cache WHERE cache_key=?", arrayOf(key),
    ).use { cursor ->
        if (!cursor.moveToFirst()) null
        else runCatching { JSONObject(cursor.getString(0)) }.getOrNull()
    }

    fun searchCacheUpdatedAt(key: String): Long? = readableDatabase.rawQuery(
        "SELECT updated_at FROM search_cache WHERE cache_key=?", arrayOf(key),
    ).use { cursor -> if (cursor.moveToFirst()) cursor.getLong(0) else null }

    /**
     * Cache cle-valeur generique par compte (volume_cache), utilise par
     * VolumeRepository.kt pour les packs de factures, recapitulatifs et
     * historique d'audit ("audit:*"). Extrait ici (au lieu de rester en SQL
     * brut dans VolumeRepository) pour permettre la bascule vers
     * HydriaVolumeCacheGateway (shared/), cf. OfflineStore.volumeRead/
     * volumeWrite/volumeWriteBatch/volumeHistory.
     */
    fun volumeRead(account: String, key: String): JSONObject? = readableDatabase.rawQuery(
        "SELECT payload FROM volume_cache WHERE account=? AND cache_key=?", arrayOf(account, key),
    ).use { cursor -> if (cursor.moveToFirst()) runCatching { JSONObject(cursor.getString(0)) }.getOrNull() else null }

    fun volumeWrite(account: String, key: String, payload: JSONObject) {
        writableDatabase.insertWithOnConflict(
            "volume_cache", null,
            ContentValues().apply { put("account", account); put("cache_key", key); put("payload", payload.toString()) },
            SQLiteDatabase.CONFLICT_REPLACE,
        )
    }

    fun volumeWriteBatch(entries: List<Triple<String, String, JSONObject>>) {
        writableDatabase.beginTransaction()
        try {
            entries.forEach { (account, key, payload) -> volumeWrite(account, key, payload) }
            writableDatabase.setTransactionSuccessful()
        } finally {
            writableDatabase.endTransaction()
        }
    }

    fun volumeHistory(account: String): List<JSONObject> = readableDatabase.rawQuery(
        "SELECT payload FROM volume_cache WHERE account=? AND cache_key LIKE 'audit:%' ORDER BY rowid DESC LIMIT 200",
        arrayOf(account),
    ).use { cursor -> buildList { while (cursor.moveToNext()) add(JSONObject(cursor.getString(0))) } }

    fun snapshot(): JSONObject? {
        val payload = StringBuilder()
        readableDatabase.rawQuery(
            "SELECT payload FROM snapshot_chunks ORDER BY chunk_index", null
        ).use { cursor ->
            while (cursor.moveToNext()) payload.append(cursor.getString(0))
        }
        return if (payload.isEmpty()) null else runCatching { JSONObject(payload.toString()) }.getOrNull()
    }

    fun saveSnapshot(value: JSONObject?) {
        writableDatabase.beginTransaction()
        try {
            writableDatabase.delete("snapshot_chunks", null, null)
            if (value != null) {
                val raw = value.toString()
                val now = System.currentTimeMillis()
                var offset = 0
                var index = 0
                while (offset < raw.length) {
                    val end = (offset + SNAPSHOT_CHUNK_CHARS).coerceAtMost(raw.length)
                    writableDatabase.insertOrThrow(
                        "snapshot_chunks", null,
                        ContentValues().apply {
                            put("chunk_index", index++)
                            put("payload", raw.substring(offset, end))
                            put("updated_at", now)
                        }
                    )
                    offset = end
                }
            }
            writableDatabase.setTransactionSuccessful()
        } finally {
            writableDatabase.endTransaction()
        }
    }

    fun enqueue(type: String, payload: JSONObject, localUuid: String = UUID.randomUUID().toString()) {
        val now = System.currentTimeMillis()
        val body = JSONObject(payload.toString()).put("local_uuid", localUuid)
        writableDatabase.insertOrThrow("sync_queue", null, ContentValues().apply {
            put("local_uuid", localUuid)
            put("operation_type", type)
            put("payload", body.toString())
            put("status", "pending")
            put("retry_count", 0)
            put("created_at", now)
            put("updated_at", now)
        })
    }

    fun pending(): JSONArray {
        val result = JSONArray()
        readableDatabase.rawQuery(
            """SELECT local_uuid, operation_type, payload, status, retry_count, last_error
               FROM sync_queue WHERE status IN ('pending','error')
               ORDER BY CASE WHEN operation_type LIKE '%photo%' THEN 1 ELSE 0 END, created_at""".trimIndent(), null
        ).use { cursor ->
            while (cursor.moveToNext()) {
                result.put(JSONObject()
                    .put("local_uuid", cursor.getString(0))
                    .put("type", cursor.getString(1))
                    .put("payload", JSONObject(cursor.getString(2)))
                    .put("status", cursor.getString(3))
                    .put("retry_count", cursor.getInt(4))
                    .put("last_error", cursor.getString(5) ?: ""))
            }
        }
        return result
    }

    fun pendingCount(): Int = readableDatabase.rawQuery(
        "SELECT COUNT(*) FROM sync_queue WHERE status IN ('pending','error')", null
    ).use { cursor -> if (cursor.moveToFirst()) cursor.getInt(0) else 0 }

    fun markSynchronizing(localUuid: String) {
        updateStatus(localUuid, "syncing", null, incrementRetry = false)
    }

    fun recoverInterrupted() {
        writableDatabase.execSQL(
            "UPDATE sync_queue SET status='error', last_error='Synchronisation interrompue' WHERE status='syncing'"
        )
    }

    fun markFailed(localUuid: String, error: String) {
        updateStatus(localUuid, "error", error.take(1000), incrementRetry = true)
    }

    fun updatePayload(localUuid: String, payload: JSONObject) {
        writableDatabase.update(
            "sync_queue",
            ContentValues().apply {
                put("payload", payload.toString())
                put("updated_at", System.currentTimeMillis())
            },
            "local_uuid=?",
            arrayOf(localUuid),
        )
    }

    private fun updateStatus(localUuid: String, status: String, error: String?, incrementRetry: Boolean) {
        val values = ContentValues().apply {
            put("status", status); put("last_error", error); put("updated_at", System.currentTimeMillis())
        }
        writableDatabase.update("sync_queue", values, "local_uuid=?", arrayOf(localUuid))
        if (incrementRetry) writableDatabase.execSQL(
            "UPDATE sync_queue SET retry_count=retry_count+1 WHERE local_uuid=?", arrayOf(localUuid)
        )
    }

    fun remove(localUuid: String) {
        writableDatabase.delete("sync_queue", "local_uuid=?", arrayOf(localUuid))
    }

    fun clearSnapshot() = writableDatabase.delete("snapshot_chunks", null, null)

    // ── Navigation / GPS (geo_entities, geo_landmark_types, geo_position_history,
    // geo_placement_candidates) : primitives extraites de GeoRepository.kt pour
    // permettre la bascule vers HydriaGeoGateway (shared/), cf. OfflineStore.geoXxx.
    // Les JSON produits ici utilisent exactement les memes cles que
    // HydriaGeoGateway (entity_id, category, name, type_label, code, ouvrage_id,
    // latitude, longitude, altitude, accuracy_m, sync_state, server_updated_at,
    // is_field_marker / entity_id, name, code, village_name, reference_latitude,
    // reference_longitude, has_photo, served_village_ids, ouvrage_id, server_updated_at).

    private fun geoEntityJson(
        entityId: String, category: String, name: String, typeLabel: String?, code: String?,
        ouvrageId: String?, latitude: Double?, longitude: Double?, altitude: Double?,
        accuracyM: Double?, syncState: String, serverUpdatedAt: String?, isFieldMarker: Boolean,
    ): JSONObject = JSONObject()
        .put("entity_id", entityId).put("category", category).put("name", name)
        .put("type_label", typeLabel ?: "").put("code", code ?: "").put("ouvrage_id", ouvrageId ?: "")
        .put("latitude", latitude).put("longitude", longitude)
        .put("altitude", altitude).put("accuracy_m", accuracyM)
        .put("sync_state", syncState).put("server_updated_at", serverUpdatedAt ?: "")
        .put("is_field_marker", isFieldMarker)

    private fun geoCandidateJson(
        entityId: String, name: String, code: String?, villageName: String?,
        referenceLatitude: Double?, referenceLongitude: Double?, hasPhoto: Boolean,
        servedVillageIds: String?, ouvrageId: String?, serverUpdatedAt: String?,
    ): JSONObject = JSONObject()
        .put("entity_id", entityId).put("name", name).put("code", code ?: "")
        .put("village_name", villageName ?: "")
        .put("reference_latitude", referenceLatitude).put("reference_longitude", referenceLongitude)
        .put("has_photo", hasPhoto)
        .put("served_village_ids", servedVillageIds ?: "")
        .put("ouvrage_id", ouvrageId ?: "").put("server_updated_at", serverUpdatedAt ?: "")

    private fun geoReadEntities(cursor: android.database.Cursor): List<JSONObject> = buildList {
        while (cursor.moveToNext()) add(
            geoEntityJson(
                entityId = cursor.getString(0), category = cursor.getString(1), name = cursor.getString(2),
                typeLabel = cursor.getString(3), code = cursor.getString(4), ouvrageId = cursor.getString(5),
                latitude = if (cursor.isNull(6)) null else cursor.getDouble(6),
                longitude = if (cursor.isNull(7)) null else cursor.getDouble(7),
                altitude = if (cursor.isNull(8)) null else cursor.getDouble(8),
                accuracyM = if (cursor.isNull(9)) null else cursor.getDouble(9),
                syncState = cursor.getString(10) ?: "synced", serverUpdatedAt = cursor.getString(11),
                isFieldMarker = cursor.getInt(12) == 1,
            )
        )
    }

    fun geoRunImportTransaction(block: () -> Unit) {
        writableDatabase.beginTransaction()
        try {
            block()
            writableDatabase.setTransactionSuccessful()
        } finally {
            writableDatabase.endTransaction()
        }
    }

    fun geoUpsertServerEntity(
        entityId: String, category: String, name: String, typeLabel: String?, code: String?,
        ouvrageId: String?, latitude: Double, longitude: Double, altitude: Double?,
        accuracyM: Double?, serverUpdatedAt: String?, isFieldMarker: Boolean,
    ) {
        val existing = readableDatabase.rawQuery(
            "SELECT spatial_id,sync_state FROM geo_entities WHERE category=? AND entity_id=?",
            arrayOf(category, entityId),
        ).use { cursor -> if (cursor.moveToFirst()) cursor.getLong(0) to cursor.getString(1) else null }
        if (existing?.second in setOf("pending", "error", "conflict")) return
        val values = ContentValues().apply {
            put("entity_id", entityId); put("category", category); put("name", name)
            put("type_label", typeLabel); put("code", code); put("ouvrage_id", ouvrageId)
            put("latitude", latitude); put("longitude", longitude); put("altitude", altitude)
            put("accuracy_m", accuracyM); put("server_updated_at", serverUpdatedAt)
            put("local_updated_at", System.currentTimeMillis()); put("sync_state", "synced"); put("is_archived", 0)
            put("is_field_marker", if (isFieldMarker) 1 else 0)
        }
        if (existing == null) writableDatabase.insertOrThrow("geo_entities", null, values)
        else writableDatabase.update("geo_entities", values, "spatial_id=?", arrayOf(existing.first.toString()))
    }

    fun geoUpsertPlacementCandidate(
        entityId: String, category: String, name: String, code: String?, villageName: String?,
        referenceLatitude: Double?, referenceLongitude: Double?, hasPhoto: Boolean,
        servedVillageIds: String?, ouvrageId: String?, serverUpdatedAt: String?,
    ) {
        val localState = readableDatabase.rawQuery(
            "SELECT has_photo,served_village_ids FROM geo_placement_candidates WHERE category=? AND entity_id=? LIMIT 1",
            arrayOf(category, entityId),
        ).use { cursor ->
            if (cursor.moveToFirst()) (cursor.getInt(0) != 0) to (cursor.getString(1) ?: "") else false to ""
        }
        writableDatabase.insertWithOnConflict(
            "geo_placement_candidates", null,
            ContentValues().apply {
                put("entity_id", entityId); put("category", category); put("name", name); put("code", code)
                put("village_name", villageName)
                put("reference_latitude", referenceLatitude); put("reference_longitude", referenceLongitude)
                put("has_photo", if (hasPhoto || localState.first) 1 else 0)
                put("served_village_ids", servedVillageIds ?: localState.second)
                put("ouvrage_id", ouvrageId); put("server_updated_at", serverUpdatedAt)
            },
            SQLiteDatabase.CONFLICT_REPLACE,
        )
    }

    fun geoUpsertServerLandmarkType(
        serverId: String, name: String, description: String?, iconKey: String,
        colorHex: String, displayOrder: Int, isActive: Boolean, serverUpdatedAt: String?,
    ) {
        writableDatabase.delete("geo_landmark_types", "icon_key=? AND id<>?", arrayOf(iconKey, serverId))
        writableDatabase.insertWithOnConflict(
            "geo_landmark_types", null,
            ContentValues().apply {
                put("id", serverId); put("name", name); put("description", description); put("icon_key", iconKey)
                put("color_hex", colorHex); put("display_order", displayOrder)
                put("is_active", if (isActive) 1 else 0); put("server_updated_at", serverUpdatedAt)
            },
            SQLiteDatabase.CONFLICT_REPLACE,
        )
    }

    fun geoArchiveEntityIfSynced(category: String, entityId: String) {
        writableDatabase.execSQL(
            "UPDATE geo_entities SET is_archived=1 WHERE category=? AND entity_id=? AND sync_state='synced'",
            arrayOf(category, entityId),
        )
    }

    fun geoMarkEntitySynced(category: String, entityId: String) {
        writableDatabase.execSQL("UPDATE geo_entities SET sync_state='synced' WHERE category=? AND entity_id=?", arrayOf(category, entityId))
    }

    fun geoMarkEntitySyncedAndArchived(category: String, entityId: String) {
        writableDatabase.execSQL(
            "UPDATE geo_entities SET sync_state='synced',is_archived=1 WHERE category=? AND entity_id=?",
            arrayOf(category, entityId),
        )
    }

    fun geoMarkEntityConflict(category: String, entityId: String) {
        writableDatabase.execSQL("UPDATE geo_entities SET sync_state='conflict' WHERE category=? AND entity_id=?", arrayOf(category, entityId))
    }

    fun geoMarkPositionHistorySynced(localUuid: String) {
        writableDatabase.execSQL("UPDATE geo_position_history SET sync_state='synced' WHERE local_uuid=?", arrayOf(localUuid))
    }

    fun geoAllEntities(categories: Set<String>, limit: Int? = null): List<JSONObject> {
        if (categories.isEmpty()) return emptyList()
        val placeholders = categories.joinToString(",") { "?" }
        val limitClause = limit?.coerceAtLeast(1)?.let { " LIMIT $it" }.orEmpty()
        return readableDatabase.rawQuery(
            """SELECT entity_id,category,name,type_label,code,ouvrage_id,latitude,longitude,
                      altitude,accuracy_m,sync_state,server_updated_at,is_field_marker
               FROM geo_entities
               WHERE is_archived=0 AND latitude IS NOT NULL AND longitude IS NOT NULL
                 AND category IN ($placeholders)
               ORDER BY name COLLATE NOCASE$limitClause""".trimIndent(),
            categories.toTypedArray(),
        ).use(::geoReadEntities)
    }

    fun geoNearby(latitude: Double, longitude: Double, radiusMeters: Double, limit: Int = 300): List<JSONObject> {
        val latDelta = radiusMeters / 111_320.0
        val lonDelta = radiusMeters / (111_320.0 * kotlin.math.cos(Math.toRadians(latitude)).coerceAtLeast(0.1))
        val candidates = readableDatabase.rawQuery(
            """SELECT entity_id,category,name,type_label,code,ouvrage_id,latitude,longitude,
                      altitude,accuracy_m,sync_state,server_updated_at,is_field_marker
               FROM geo_entities
               WHERE latitude>=? AND latitude<=? AND longitude>=? AND longitude<=? AND is_archived=0
               LIMIT ?""".trimIndent(),
            arrayOf(
                (latitude - latDelta).toString(), (latitude + latDelta).toString(),
                (longitude - lonDelta).toString(), (longitude + lonDelta).toString(), limit.toString(),
            ),
        ).use(::geoReadEntities)
        fun dist(lat: Double, lon: Double) = kotlin.run {
            val phi1 = Math.toRadians(latitude); val phi2 = Math.toRadians(lat)
            val dPhi = Math.toRadians(lat - latitude); val dLambda = Math.toRadians(lon - longitude)
            val a = kotlin.math.sin(dPhi / 2).let { it * it } + kotlin.math.cos(phi1) * kotlin.math.cos(phi2) * kotlin.math.sin(dLambda / 2).let { it * it }
            6_371_008.8 * 2 * kotlin.math.atan2(kotlin.math.sqrt(a), kotlin.math.sqrt(1 - a))
        }
        return candidates.filter { dist(it.optDouble("latitude"), it.optDouble("longitude")) <= radiusMeters }
            .sortedBy { dist(it.optDouble("latitude"), it.optDouble("longitude")) }
    }

    fun geoWithinBounds(
        north: Double, south: Double, east: Double, west: Double,
        centerLatitude: Double, centerLongitude: Double, limit: Int = 600,
    ): List<JSONObject> = readableDatabase.rawQuery(
        """SELECT entity_id,category,name,type_label,code,ouvrage_id,latitude,longitude,
                  altitude,accuracy_m,sync_state,server_updated_at,is_field_marker
           FROM geo_entities
           WHERE latitude>=? AND latitude<=? AND longitude>=? AND longitude<=? AND is_archived=0
           ORDER BY ((latitude-?)*(latitude-?))+((longitude-?)*(longitude-?)) ASC
           LIMIT ?""".trimIndent(),
        arrayOf(
            south.toString(), north.toString(), west.toString(), east.toString(),
            centerLatitude.toString(), centerLatitude.toString(),
            centerLongitude.toString(), centerLongitude.toString(),
            limit.coerceAtLeast(1).toString(),
        ),
    ).use(::geoReadEntities)

    fun geoLandmarkTypes(): List<Pair<String, String>> = readableDatabase.rawQuery(
        "SELECT id,name FROM geo_landmark_types WHERE is_active=1 ORDER BY display_order,name", null
    ).use { cursor -> buildList { while (cursor.moveToNext()) add(cursor.getString(0) to cursor.getString(1)) } }

    fun geoPlacementCandidates(category: String): List<JSONObject> = readableDatabase.rawQuery(
        """SELECT entity_id,name,code,village_name,reference_latitude,reference_longitude,has_photo,served_village_ids,ouvrage_id,server_updated_at
           FROM geo_placement_candidates WHERE category=? ORDER BY name COLLATE NOCASE""".trimIndent(),
        arrayOf(category),
    ).use { cursor ->
        buildList {
            while (cursor.moveToNext()) add(
                geoCandidateJson(
                    entityId = cursor.getString(0), name = cursor.getString(1), code = cursor.getString(2),
                    villageName = cursor.getString(3),
                    referenceLatitude = if (cursor.isNull(4)) null else cursor.getDouble(4),
                    referenceLongitude = if (cursor.isNull(5)) null else cursor.getDouble(5),
                    hasPhoto = cursor.getInt(6) != 0, servedVillageIds = cursor.getString(7),
                    ouvrageId = cursor.getString(8), serverUpdatedAt = cursor.getString(9),
                )
            )
        }
    }

    fun geoPlacementCandidate(category: String, entityId: String): JSONObject? =
        geoPlacementCandidates(category).firstOrNull { it.optString("entity_id") == entityId }

    fun geoMarkCandidatePhotoQueued(category: String, entityId: String) {
        writableDatabase.execSQL(
            "UPDATE geo_placement_candidates SET has_photo=1 WHERE category=? AND entity_id=?",
            arrayOf(category, entityId),
        )
    }

    fun geoNearbyVillageIds(latitude: Double, longitude: Double, radiusMeters: Double = 25_000.0): Set<String> {
        val latitudeDelta = radiusMeters / 111_320.0
        val longitudeScale = kotlin.math.cos(Math.toRadians(latitude)).let { kotlin.math.abs(it).coerceAtLeast(0.1) }
        val longitudeDelta = radiusMeters / (111_320.0 * longitudeScale)
        return readableDatabase.rawQuery(
            """SELECT entity_id,latitude,longitude FROM geo_entities
               WHERE category=? AND is_archived=0
                 AND latitude>=? AND latitude<=? AND longitude>=? AND longitude<=?""".trimIndent(),
            arrayOf(
                "village",
                (latitude - latitudeDelta).toString(), (latitude + latitudeDelta).toString(),
                (longitude - longitudeDelta).toString(), (longitude + longitudeDelta).toString(),
            ),
        ).use { cursor ->
            buildSet {
                while (cursor.moveToNext()) {
                    val dLat = Math.toRadians(cursor.getDouble(1) - latitude); val dLon = Math.toRadians(cursor.getDouble(2) - longitude)
                    val a = kotlin.math.sin(dLat / 2).let { it * it } +
                        kotlin.math.cos(Math.toRadians(latitude)) * kotlin.math.cos(Math.toRadians(cursor.getDouble(1))) * kotlin.math.sin(dLon / 2).let { it * it }
                    val d = 6_371_008.8 * 2 * kotlin.math.atan2(kotlin.math.sqrt(a), kotlin.math.sqrt(1 - a))
                    if (d <= radiusMeters) add(cursor.getString(0))
                }
            }
        }
    }

    fun geoCandidateIdsServingNearbyVillages(
        category: String, latitude: Double, longitude: Double, radiusMeters: Double = 25_000.0,
    ): Set<String> {
        val latitudeDelta = radiusMeters / 111_320.0
        val longitudeScale = kotlin.math.cos(Math.toRadians(latitude)).let { kotlin.math.abs(it).coerceAtLeast(0.1) }
        val longitudeDelta = radiusMeters / (111_320.0 * longitudeScale)
        val nearbyVillages = readableDatabase.rawQuery(
            """SELECT entity_id,name,latitude,longitude FROM geo_entities
               WHERE category=? AND is_archived=0
                 AND latitude>=? AND latitude<=? AND longitude>=? AND longitude<=?""".trimIndent(),
            arrayOf(
                "village",
                (latitude - latitudeDelta).toString(), (latitude + latitudeDelta).toString(),
                (longitude - longitudeDelta).toString(), (longitude + longitudeDelta).toString(),
            ),
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) {
                    val dLat = Math.toRadians(cursor.getDouble(2) - latitude); val dLon = Math.toRadians(cursor.getDouble(3) - longitude)
                    val a = kotlin.math.sin(dLat / 2).let { it * it } +
                        kotlin.math.cos(Math.toRadians(latitude)) * kotlin.math.cos(Math.toRadians(cursor.getDouble(2))) * kotlin.math.sin(dLon / 2).let { it * it }
                    val d = 6_371_008.8 * 2 * kotlin.math.atan2(kotlin.math.sqrt(a), kotlin.math.sqrt(1 - a))
                    if (d <= radiusMeters) add(cursor.getString(0) to cursor.getString(1).trim().lowercase())
                }
            }
        }
        val nearbyIds = nearbyVillages.mapTo(mutableSetOf()) { it.first }
        val nearbyNames = nearbyVillages.mapTo(mutableSetOf()) { it.second }
        if (nearbyIds.isEmpty() && nearbyNames.isEmpty()) return emptySet()

        val villageNamesByOuvrage = mutableMapOf<String, MutableSet<String>>()
        readableDatabase.rawQuery(
            """SELECT ouvrage_id,village_name FROM geo_placement_candidates
               WHERE category=? AND ouvrage_id IS NOT NULL AND TRIM(ouvrage_id)<>''
                 AND village_name IS NOT NULL AND TRIM(village_name)<>''""".trimIndent(),
            arrayOf("water_point"),
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val names = villageNamesByOuvrage.getOrPut(cursor.getString(0)) { mutableSetOf() }
                cursor.getString(1).split(',').map { it.trim().lowercase() }.filterTo(names) { it.isNotBlank() }
            }
        }

        return geoPlacementCandidates(category).filterTo(mutableSetOf()) { candidate ->
            val servedIds = candidate.optString("served_village_ids").split(',').filter { it.isNotBlank() }.toSet()
            val ouvrageId = candidate.optString("ouvrage_id")
            servedIds.any { it in nearbyIds } || villageNamesByOuvrage[ouvrageId].orEmpty().any { it in nearbyNames }
        }.mapTo(mutableSetOf()) { it.optString("entity_id") }
    }

    fun geoPlaceCandidate(
        entityId: String, category: String, name: String, code: String?,
        latitude: Double, longitude: Double, altitude: Double?, accuracyM: Double?,
        captureMethod: String, capturedAt: String, serverUpdatedAt: String?,
    ): Pair<JSONObject, String> {
        val existing = readableDatabase.rawQuery(
            """SELECT entity_id,category,name,type_label,code,ouvrage_id,latitude,longitude,
                      altitude,accuracy_m,sync_state,server_updated_at,is_field_marker
               FROM geo_entities WHERE category=? AND entity_id=? LIMIT 1""".trimIndent(),
            arrayOf(category, entityId),
        ).use { geoReadEntities(it).firstOrNull() }
        if (existing != null) {
            val localUuid = geoUpdatePosition(category, entityId, latitude, longitude, altitude, accuracyM, captureMethod, capturedAt)
            val updated = geoEntityJson(
                entityId, category, existing.optString("name"), existing.optString("type_label"), existing.optString("code"),
                existing.optString("ouvrage_id"), latitude, longitude, altitude, accuracyM, "pending",
                existing.optString("server_updated_at"), existing.optBoolean("is_field_marker"),
            )
            return updated to localUuid
        }
        val localUuid = UUID.randomUUID().toString()
        val now = System.currentTimeMillis()
        writableDatabase.beginTransaction()
        try {
            writableDatabase.insertOrThrow("geo_entities", null, ContentValues().apply {
                put("entity_id", entityId); put("category", category); put("name", name); put("type_label", null as String?)
                put("code", code); put("ouvrage_id", null as String?)
                put("latitude", latitude); put("longitude", longitude); put("altitude", altitude)
                put("accuracy_m", accuracyM); put("server_updated_at", serverUpdatedAt)
                put("local_updated_at", now); put("sync_state", "pending"); put("is_archived", 0); put("is_field_marker", 0)
                put("capture_method", captureMethod); put("captured_at", capturedAt)
            })
            writableDatabase.insertOrThrow("geo_position_history", null, ContentValues().apply {
                put("local_uuid", localUuid); put("entity_kind", category); put("entity_id", entityId)
                put("new_latitude", latitude); put("new_longitude", longitude)
                put("altitude", altitude); put("accuracy_m", accuracyM)
                put("capture_method", captureMethod); put("captured_at", capturedAt)
                put("sync_state", "pending"); put("created_at", now)
            })
            writableDatabase.setTransactionSuccessful()
        } finally {
            writableDatabase.endTransaction()
        }
        val entity = geoEntityJson(entityId, category, name, null, code, null, latitude, longitude, altitude, accuracyM, "pending", serverUpdatedAt, false)
        return entity to localUuid
    }

    fun geoCreateLandmark(
        name: String, typeId: String, latitude: Double, longitude: Double,
        altitude: Double?, accuracyM: Double?, captureMethod: String, capturedAt: String,
        category: String = "landmark",
    ): JSONObject {
        val entityId = UUID.randomUUID().toString()
        val typeLabel = geoLandmarkTypes().firstOrNull { it.first == typeId }?.second ?: "Repère"
        writableDatabase.insertOrThrow("geo_entities", null, ContentValues().apply {
            put("entity_id", entityId); put("category", category); put("name", name)
            put("type_label", typeLabel); put("code", typeId); put("ouvrage_id", null as String?)
            put("latitude", latitude); put("longitude", longitude); put("altitude", altitude)
            put("accuracy_m", accuracyM); put("server_updated_at", null as String?)
            put("local_updated_at", System.currentTimeMillis()); put("sync_state", "pending")
            put("is_archived", 0); put("is_field_marker", 1)
            put("capture_method", captureMethod); put("captured_at", capturedAt)
        })
        return geoEntityJson(entityId, category, name, typeLabel, typeId, null, latitude, longitude, altitude, accuracyM, "pending", null, true)
    }

    fun geoUpdatePosition(
        category: String, entityId: String, latitude: Double, longitude: Double,
        altitude: Double?, accuracyM: Double?, captureMethod: String, capturedAt: String,
    ): String {
        val localUuid = UUID.randomUUID().toString()
        val now = System.currentTimeMillis()
        val existing = readableDatabase.rawQuery(
            "SELECT latitude,longitude FROM geo_entities WHERE category=? AND entity_id=? LIMIT 1",
            arrayOf(category, entityId),
        ).use { cursor -> if (cursor.moveToFirst()) cursor.getDouble(0) to cursor.getDouble(1) else null }
        writableDatabase.beginTransaction()
        try {
            writableDatabase.update(
                "geo_entities",
                ContentValues().apply {
                    put("latitude", latitude); put("longitude", longitude); put("altitude", altitude)
                    put("accuracy_m", accuracyM); put("capture_method", captureMethod); put("captured_at", capturedAt)
                    put("local_updated_at", now); put("sync_state", "pending")
                },
                "category=? AND entity_id=?", arrayOf(category, entityId),
            )
            writableDatabase.insertOrThrow(
                "geo_position_history", null,
                ContentValues().apply {
                    put("local_uuid", localUuid); put("entity_kind", category); put("entity_id", entityId)
                    put("old_latitude", existing?.first); put("old_longitude", existing?.second)
                    put("new_latitude", latitude); put("new_longitude", longitude); put("altitude", altitude)
                    put("accuracy_m", accuracyM); put("capture_method", captureMethod); put("captured_at", capturedAt)
                    put("sync_state", "pending"); put("created_at", now)
                },
            )
            writableDatabase.setTransactionSuccessful()
        } finally {
            writableDatabase.endTransaction()
        }
        return localUuid
    }

    fun geoArchiveLandmark(category: String, entityId: String): String {
        writableDatabase.execSQL(
            "UPDATE geo_entities SET is_archived=1,sync_state='pending',local_updated_at=? WHERE category=? AND entity_id=?",
            arrayOf<Any>(System.currentTimeMillis(), category, entityId),
        )
        return UUID.randomUUID().toString()
    }
}
