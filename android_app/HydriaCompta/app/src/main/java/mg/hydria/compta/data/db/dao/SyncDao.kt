package mg.hydria.compta.data.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import mg.hydria.compta.core.MutationStatus
import mg.hydria.compta.data.db.entity.ConflictEntity
import mg.hydria.compta.data.db.entity.DeviceInvoiceRangeEntity
import mg.hydria.compta.data.db.entity.OutboxMutationEntity
import mg.hydria.compta.data.db.entity.PendingDocumentEntity
import mg.hydria.compta.data.db.entity.SyncStateEntity
import java.time.Instant

@Dao
interface OutboxDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun insert(mutation: OutboxMutationEntity)

    /**
     * Prochaines mutations envoyables : statut QUEUED et, si une dépendance
     * existe, elle doit déjà être ACKED.
     */
    @Query(
        """
        SELECT m.* FROM outbox_mutation m
        WHERE m.status = 'QUEUED'
          AND (
            m.dependsOnLocalUuid IS NULL
            OR EXISTS (
              SELECT 1 FROM outbox_mutation d
              WHERE d.localUuid = m.dependsOnLocalUuid AND d.status = 'ACKED'
            )
          )
        ORDER BY m.createdAt
        LIMIT :limit
        """
    )
    suspend fun prochaines(limit: Int): List<OutboxMutationEntity>

    @Query("SELECT * FROM outbox_mutation WHERE status = 'IN_FLIGHT'")
    suspend fun enVol(): List<OutboxMutationEntity>

    @Query("UPDATE outbox_mutation SET status = :status, attempts = attempts + 1, lastAttemptAt = :now, lastError = :error WHERE localUuid = :localUuid")
    suspend fun marquer(localUuid: String, status: MutationStatus, now: Instant, error: String?)

    @Query("UPDATE outbox_mutation SET status = 'ACKED', ackedAt = :now, serverIdAssigned = :serverId WHERE localUuid = :localUuid")
    suspend fun marquerAcked(localUuid: String, now: Instant, serverId: String?)

    @Query("SELECT COUNT(*) FROM outbox_mutation WHERE status = :status")
    fun observeCount(status: MutationStatus): Flow<Int>

    @Query("SELECT COUNT(*) FROM outbox_mutation WHERE status IN ('QUEUED','IN_FLIGHT')")
    fun observeEnAttente(): Flow<Int>

    @Query("SELECT COUNT(*) FROM outbox_mutation WHERE status IN ('FAILED','CONFLICT')")
    fun observeAProbleme(): Flow<Int>
}

@Dao
interface SyncStateDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(state: SyncStateEntity)
    @Query("SELECT value FROM sync_state WHERE key = :key") suspend fun get(key: String): String?
    @Query("SELECT value FROM sync_state WHERE key = :key") fun observe(key: String): Flow<String?>
}

@Dao
interface ConflictDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun insert(conflict: ConflictEntity)
    @Query("SELECT * FROM conflict WHERE resolvedAt IS NULL ORDER BY detectedAt")
    fun observeOuverts(): Flow<List<ConflictEntity>>

    @Query("SELECT COUNT(*) FROM conflict WHERE resolvedAt IS NULL")
    fun observeCountOuverts(): Flow<Int>
    @Query("SELECT * FROM conflict WHERE id = :id") suspend fun byId(id: String): ConflictEntity?
    @Query("UPDATE conflict SET resolvedAt = :now, resolution = :resolution, resolvedBy = :by WHERE id = :id")
    suspend fun resoudre(id: String, now: Instant, resolution: String, by: String?)
}

@Dao
interface InvoiceRangeDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(range: DeviceInvoiceRangeEntity)
    @Query("SELECT * FROM device_invoice_range WHERE exhausted = 0 ORDER BY allocatedAt DESC LIMIT 1")
    suspend fun rangeActive(): DeviceInvoiceRangeEntity?
    @Query("UPDATE device_invoice_range SET nextNumber = :next, exhausted = :exhausted WHERE id = :id")
    suspend fun avancer(id: String, next: Long, exhausted: Boolean)
}

@Dao
interface PendingDocumentDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun insert(doc: PendingDocumentEntity)
    @Query("SELECT * FROM pending_document WHERE uploadStatus IN ('pending','failed')")
    suspend fun aEnvoyer(): List<PendingDocumentEntity>
    @Query("UPDATE pending_document SET uploadStatus = :status, serverUrl = :url WHERE localUuid = :localUuid")
    suspend fun marquer(localUuid: String, status: String, url: String?)
}
