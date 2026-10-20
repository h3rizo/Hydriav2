package mg.hydria.logistique.sync

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.serialization.json.Json
import mg.hydria.logistique.database.LogistiqueDao
import mg.hydria.logistique.database.SyncConflictEntity
import mg.hydria.logistique.model.OutboxEnvelope
import mg.hydria.logistique.model.OperationType
import mg.hydria.logistique.model.SyncStatus
import mg.hydria.logistique.network.MobileApi
import mg.hydria.logistique.network.OperationBatchRequest
import java.time.OffsetDateTime
import java.util.UUID

@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val dao: LogistiqueDao,
    private val api: MobileApi,
    private val json: Json,
) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val pending = dao.pendingOperations()
        if (pending.isEmpty()) return Result.success()

        pending.forEach { dao.updateOutboxStatus(it.id, SyncStatus.RUNNING.name, 0) }
        return try {
            val envelopes = pending.map {
                OutboxEnvelope(
                    clientOperationId = it.clientOperationId,
                    operationType = OperationType.valueOf(it.operationType),
                    localEntityId = it.localEntityId,
                    userId = it.userId,
                    deviceId = it.deviceId,
                    businessDateIso = it.businessDate,
                    createdAtIso = it.createdAt,
                    knownServerRevision = it.knownServerRevision,
                    payloadJson = it.payloadJson,
                    dependencyIds = json.decodeFromString(it.dependencyIdsJson),
                )
            }
            val response = api.submitOperations(OperationBatchRequest(envelopes))
            response.results.forEach { result ->
                val local = pending.first { it.clientOperationId == result.clientOperationId }
                when {
                    result.accepted -> dao.updateOutboxStatus(local.id, SyncStatus.SYNCED.name, 1)
                    result.conflict -> {
                        dao.updateOutboxStatus(local.id, SyncStatus.CONFLICT.name, 1, result.errorCode, result.errorMessage)
                        dao.upsertConflict(
                            SyncConflictEntity(
                                id = UUID.randomUUID().toString(), operationId = local.id,
                                code = result.errorCode ?: "CONFLICT", message = result.errorMessage ?: "Conflit métier",
                                serverStateJson = result.serverStateJson, localPayloadJson = local.payloadJson,
                                createdAt = OffsetDateTime.now().toString(), resolvedAt = null,
                            )
                        )
                    }
                    else -> dao.updateOutboxStatus(local.id, SyncStatus.REJECTED.name, 1, result.errorCode, result.errorMessage)
                }
            }
            Result.success()
        } catch (exception: Exception) {
            pending.forEach { dao.updateOutboxStatus(it.id, SyncStatus.PENDING.name, 1, "NETWORK", exception.message) }
            Result.retry()
        }
    }
}
