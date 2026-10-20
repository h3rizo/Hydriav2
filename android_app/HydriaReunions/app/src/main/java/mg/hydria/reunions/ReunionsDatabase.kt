package mg.hydria.reunions

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONObject

/**
 * Stockage local natif (offline-first), meme approche que TerrainDatabase
 * (app terrain) : une table par type d'entite, chaque ligne porte le JSON
 * complet renvoye par l'API (simple a synchroniser en upsert par id), plus
 * une table sync_queue pour les mutations creees hors ligne.
 */
class ReunionsDatabase(context: Context) : SQLiteOpenHelper(context, "hydria_reunions.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase) {
        entityTables().forEach { table -> createEntityTable(db, table) }
        db.execSQL(
            """CREATE TABLE sync_queue (
                local_uuid TEXT PRIMARY KEY,
                operation_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at INTEGER NOT NULL
            )""".trimIndent()
        )
        db.execSQL("CREATE INDEX idx_sync_queue_status ON sync_queue(status, created_at)")
        db.execSQL("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // V1 — pas de migration a gerer pour l'instant.
    }

    private fun entityTables(): List<String> = listOf(
        "representantes", "avis", "reunions", "decisions", "participants",
        "pieces_jointes", "conversations", "messages",
    )

    private fun createEntityTable(db: SQLiteDatabase, table: String) {
        db.execSQL(
            """CREATE TABLE $table (
                id TEXT PRIMARY KEY,
                parent_id TEXT,
                json TEXT NOT NULL,
                updated_at TEXT
            )""".trimIndent()
        )
        db.execSQL("CREATE INDEX idx_${table}_parent ON $table(parent_id)")
    }

    fun upsert(table: String, id: String, parentId: String?, json: JSONObject, updatedAt: String?) {
        val values = ContentValues().apply {
            put("id", id)
            put("parent_id", parentId)
            put("json", json.toString())
            put("updated_at", updatedAt)
        }
        writableDatabase.insertWithOnConflict(table, null, values, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun all(table: String, parentId: String? = null): List<JSONObject> {
        val (selection, args) = if (parentId != null) "parent_id = ?" to arrayOf(parentId) else null to null
        val results = mutableListOf<JSONObject>()
        readableDatabase.query(table, arrayOf("json"), selection, args, null, null, null).use { cursor ->
            while (cursor.moveToNext()) {
                results.add(JSONObject(cursor.getString(0)))
            }
        }
        return results
    }

    fun clearAll() {
        val db = writableDatabase
        entityTables().forEach { table -> db.delete(table, null, null) }
    }

    fun setMeta(key: String, value: String) {
        val values = ContentValues().apply { put("key", key); put("value", value) }
        writableDatabase.insertWithOnConflict("meta", null, values, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun getMeta(key: String): String? {
        readableDatabase.query("meta", arrayOf("value"), "key = ?", arrayOf(key), null, null, null).use { cursor ->
            return if (cursor.moveToFirst()) cursor.getString(0) else null
        }
    }

    fun enqueueMutation(localUuid: String, operationType: String, payload: JSONObject) {
        val values = ContentValues().apply {
            put("local_uuid", localUuid)
            put("operation_type", operationType)
            put("payload", payload.toString())
            put("status", "pending")
            put("created_at", System.currentTimeMillis())
        }
        writableDatabase.insertWithOnConflict("sync_queue", null, values, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun pendingMutations(): List<Triple<String, String, JSONObject>> {
        val results = mutableListOf<Triple<String, String, JSONObject>>()
        readableDatabase.query(
            "sync_queue", arrayOf("local_uuid", "operation_type", "payload"),
            "status = ?", arrayOf("pending"), null, null, "created_at ASC",
        ).use { cursor ->
            while (cursor.moveToNext()) {
                results.add(Triple(cursor.getString(0), cursor.getString(1), JSONObject(cursor.getString(2))))
            }
        }
        return results
    }

    fun markMutationSynced(localUuid: String) {
        writableDatabase.delete("sync_queue", "local_uuid = ?", arrayOf(localUuid))
    }

    fun markMutationFailed(localUuid: String, error: String) {
        val values = ContentValues().apply {
            put("status", "error")
            put("last_error", error)
        }
        writableDatabase.update("sync_queue", values, "local_uuid = ?", arrayOf(localUuid))
    }
}
