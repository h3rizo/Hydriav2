package mg.hydria.compta.data.repository

import androidx.room.withTransaction
import mg.hydria.compta.core.MutationStatus
import mg.hydria.compta.core.MutationType
import mg.hydria.compta.data.db.ComptaDatabase
import mg.hydria.compta.data.db.entity.OutboxMutationEntity
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

/**
 * Point d'entrée unique pour créer une mutation hors ligne : l'agrégat et sa
 * ligne d'outbox sont écrits dans la MÊME transaction, puis le worker de push
 * est déclenché par l'appelant.
 */
class OutboxRepository(private val db: ComptaDatabase) {

    private val outbox = db.outboxDao()

    /**
     * @param persistAggregate écrit l'agrégat (pièce, facture, mouvement…) via ses DAOs.
     */
    suspend fun enqueue(
        aggregateType: String,
        aggregateLocalUuid: String,
        operation: MutationType,
        payload: JSONObject,
        baseRevision: Long,
        dependsOnLocalUuid: String? = null,
        persistAggregate: suspend () -> Unit,
    ): String {
        val mutationId = UUID.randomUUID().toString()
        db.withTransaction {
            persistAggregate()
            outbox.insert(
                OutboxMutationEntity(
                    localUuid = mutationId,
                    aggregateType = aggregateType,
                    aggregateLocalUuid = aggregateLocalUuid,
                    operation = operation,
                    payloadJson = payload.toString(),
                    baseRevision = baseRevision,
                    dependsOnLocalUuid = dependsOnLocalUuid,
                    status = MutationStatus.QUEUED,
                    createdAt = Instant.now(),
                )
            )
        }
        return mutationId
    }

    suspend fun prochaines(limit: Int = 25) = outbox.prochaines(limit)
    suspend fun enVol() = outbox.enVol()

    suspend fun marquerEnVol(localUuid: String) =
        outbox.marquer(localUuid, MutationStatus.IN_FLIGHT, Instant.now(), null)

    suspend fun marquerAcked(localUuid: String, serverId: String?) =
        outbox.marquerAcked(localUuid, Instant.now(), serverId)

    suspend fun marquerEchec(localUuid: String, statut: MutationStatus, erreur: String?) =
        outbox.marquer(localUuid, statut, Instant.now(), erreur)

    /** Remet en file une mutation après résolution de conflit (nouvelle baseRevision). */
    suspend fun rejouer(localUuid: String) =
        outbox.marquer(localUuid, MutationStatus.QUEUED, Instant.now(), null)
}
