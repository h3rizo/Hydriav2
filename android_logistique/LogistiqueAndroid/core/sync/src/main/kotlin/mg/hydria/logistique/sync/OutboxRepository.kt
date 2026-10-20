package mg.hydria.logistique.sync

import mg.hydria.logistique.database.LogistiqueDao
import mg.hydria.logistique.database.OutboxOperationEntity
import mg.hydria.logistique.model.OutboxEnvelope
import mg.hydria.logistique.model.SyncStatus
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import javax.inject.Inject

class OutboxRepository @Inject constructor(
    private val dao: LogistiqueDao,
    private val json: Json,
) {
    suspend fun enqueue(envelope: OutboxEnvelope) {
        dao.enqueue(
            OutboxOperationEntity(
                id = envelope.clientOperationId,
                clientOperationId = envelope.clientOperationId,
                operationType = envelope.operationType.name,
                localEntityId = envelope.localEntityId,
                userId = envelope.userId,
                deviceId = envelope.deviceId,
                businessDate = envelope.businessDateIso,
                createdAt = envelope.createdAtIso,
                knownServerRevision = envelope.knownServerRevision,
                payloadJson = envelope.payloadJson,
                dependencyIdsJson = json.encodeToString(envelope.dependencyIds),
                attemptCount = 0,
                status = SyncStatus.PENDING.name,
                lastErrorCode = null,
                lastErrorMessage = null,
            )
        )
    }
}
