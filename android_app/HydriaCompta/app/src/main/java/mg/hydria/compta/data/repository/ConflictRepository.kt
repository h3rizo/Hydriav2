package mg.hydria.compta.data.repository

import kotlinx.coroutines.flow.Flow
import mg.hydria.compta.core.ConflictResolution
import mg.hydria.compta.data.db.ComptaDatabase
import mg.hydria.compta.data.db.entity.ConflictEntity
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

/** File de revue manuelle des conflits (jamais « dernier écrit gagne »). */
class ConflictRepository(
    private val db: ComptaDatabase,
    private val outbox: OutboxRepository,
) {

    fun observeOuverts(): Flow<List<ConflictEntity>> = db.conflictDao().observeOuverts()

    suspend fun enregistrer(
        aggregateType: String,
        aggregateLocalUuid: String,
        localSnapshot: JSONObject,
        serverSnapshot: JSONObject,
    ) {
        db.conflictDao().insert(
            ConflictEntity(
                id = UUID.randomUUID().toString(),
                aggregateType = aggregateType,
                aggregateLocalUuid = aggregateLocalUuid,
                localSnapshotJson = localSnapshot.toString(),
                serverSnapshotJson = serverSnapshot.toString(),
                detectedAt = Instant.now(),
            )
        )
    }

    /**
     * @param nouvelleBaseRevision révision serveur à jour à réappliquer si l'on garde la version locale.
     * @param mutationLocalUuid mutation d'origine à rejouer le cas échéant.
     */
    suspend fun resoudre(
        conflictId: String,
        resolution: ConflictResolution,
        resolvedBy: String?,
        mutationLocalUuid: String?,
    ) {
        db.conflictDao().resoudre(conflictId, Instant.now(), resolution.name, resolvedBy)
        if (resolution == ConflictResolution.GARDER_LOCAL && mutationLocalUuid != null) {
            outbox.rejouer(mutationLocalUuid)
        }
        // GARDER_SERVEUR / FUSION : la valeur serveur est déjà appliquée par le
        // prochain `changes` ; l'agrégat local repasse SYNCED côté repository métier.
    }
}
