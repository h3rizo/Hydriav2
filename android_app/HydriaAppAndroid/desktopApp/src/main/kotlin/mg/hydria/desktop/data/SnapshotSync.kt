package mg.hydria.desktop.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mg.hydria.shared.database.HydriaSnapshotGateway
import mg.hydria.shared.network.HydriaOperationsGateway

/**
 * Rafraichit le snapshot de perimetre (GET /plannings/api/preparer-tournee/)
 * et le stocke dans SQLDelight. Source unique pour les ecrans Releves,
 * Reparations et Planning cote Desktop, qui lisent tous
 * `HydriaSnapshotGateway.snapshot()`.
 */
object SnapshotSync {
    sealed interface Outcome {
        data class Refreshed(val raw: Boolean) : Outcome   // raw=false => "not_modified"
        data class Failed(val message: String) : Outcome
    }

    suspend fun refresh(token: String): Outcome = withContext(Dispatchers.IO) {
        val result = runCatching { HydriaOperationsGateway.prepareTour(token, null) }
            .getOrElse { return@withContext Outcome.Failed("Synchronisation impossible : ${it.message ?: "reseau indisponible"}") }
        val body = result.body
        when {
            result.status !in 200..299 || !body.optBoolean("success", true) ->
                Outcome.Failed(body.optString("error", "Erreur HTTP ${result.status}"))
            body.optBoolean("not_modified", false) -> Outcome.Refreshed(raw = false)
            else -> {
                runCatching { HydriaSnapshotGateway.saveSnapshot(body) }
                    .getOrElse { return@withContext Outcome.Failed("Ecriture locale impossible : ${it.message}") }
                Outcome.Refreshed(raw = true)
            }
        }
    }
}
