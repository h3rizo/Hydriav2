package mg.hydria.compta.data.db.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import mg.hydria.compta.core.ConflictResolution
import mg.hydria.compta.core.MutationStatus
import mg.hydria.compta.core.MutationType
import java.time.Instant

/** Infrastructure de synchronisation. */

@Entity(
    tableName = "outbox_mutation",
    indices = [Index("status", "createdAt"), Index("aggregateLocalUuid")],
)
data class OutboxMutationEntity(
    @PrimaryKey val localUuid: String,
    val aggregateType: String,
    val aggregateLocalUuid: String,
    val operation: MutationType,
    val payloadJson: String,
    val baseRevision: Long,
    /** Ordonnancement : une mutation ne part pas avant celle dont elle dépend. */
    val dependsOnLocalUuid: String? = null,
    val attempts: Int = 0,
    val lastAttemptAt: Instant? = null,
    val lastError: String? = null,
    val status: MutationStatus = MutationStatus.QUEUED,
    val createdAt: Instant,
    val ackedAt: Instant? = null,
    val serverIdAssigned: String? = null,
)

@Entity(tableName = "sync_state")
data class SyncStateEntity(
    @PrimaryKey val key: String,
    val value: String,
)

object SyncStateKeys {
    const val CURSOR = "compta.cursor"
    const val LAST_FULL_SYNC = "compta.lastFullSync"
    const val LAST_PULL_OK = "compta.lastPullOk"
    const val SOLDES_JSON = "compta.soldes"
    const val VERIFICATION_SCANS_JSON = "compta.verificationScans"
}

@Entity(tableName = "conflict", indices = [Index("resolvedAt")])
data class ConflictEntity(
    @PrimaryKey val id: String,
    val aggregateType: String,
    val aggregateLocalUuid: String,
    val localSnapshotJson: String,
    val serverSnapshotJson: String,
    val detectedAt: Instant,
    val resolvedAt: Instant? = null,
    val resolution: ConflictResolution = ConflictResolution.NON_RESOLU,
    val resolvedBy: String? = null,
)

@Entity(tableName = "device_invoice_range")
data class DeviceInvoiceRangeEntity(
    @PrimaryKey val id: String,
    val prefix: String,
    val rangeStart: Long,
    val rangeEnd: Long,
    val nextNumber: Long,
    val allocatedAt: Instant,
    val exhausted: Boolean = false,
)

@Entity(tableName = "pending_document", indices = [Index("uploadStatus")])
data class PendingDocumentEntity(
    @PrimaryKey val localUuid: String,
    val aggregateType: String,
    val aggregateLocalUuid: String,
    val localUri: String,
    val mime: String,
    val uploadStatus: String = "pending", // pending | uploading | done | failed
    val serverUrl: String? = null,
)
