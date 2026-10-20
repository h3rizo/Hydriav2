package mg.hydria.desktop.volume

import mg.hydria.shared.database.HydriaSyncQueueGateway
import mg.hydria.shared.database.HydriaVolumeCacheGateway
import mg.hydria.shared.network.HydriaOperationsGateway
import mg.hydria.shared.volume.VolumeCacheGateway
import mg.hydria.shared.volume.VolumeConfirmationRules
import mg.hydria.shared.volume.VolumeOperationGateway
import mg.hydria.shared.volume.VolumeResultGateway
import mg.hydria.shared.volume.VolumeRules
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

/** Resultat reseau au meme contrat que HydriaApi.Result (Android). */
data class VolumeResult(val status: Int, val body: JSONObject) {
    val successful: Boolean get() = status in 200..299 && body.optBoolean("success", true)
    val error: String get() = body.optString("error", "Erreur HTTP $status")
}

/**
 * Miroir Desktop de `app/volume/VolumeRepository.kt` : memes cles de cache
 * (`ouvrages`, `pack:…`, `invoice:…`, `audit:…`, `recap:…`, `last_recap:…`),
 * meme type de file (`volume`), memes regles :shared. Seule difference : les
 * facades SQLDelight sont appelees directement (pas d'OfflineStore/legacy).
 */
class DesktopVolumeRepository(private val accountProvider: () -> String) {
    private companion object { val syncLock = Any() }
    private val account get() = accountProvider()

    fun read(key: String): JSONObject? = HydriaVolumeCacheGateway.read(account, key)
    fun write(key: String, value: JSONObject) = HydriaVolumeCacheGateway.write(account, key, value)

    fun savePack(pack: JSONObject) = HydriaVolumeCacheGateway.writeBatch(VolumeCacheGateway.packEntries(account, pack))

    fun invoices(pack: JSONObject): List<JSONObject> = VolumeCacheGateway.invoices(pack, ::read)

    fun pending(): List<JSONObject> = VolumeCacheGateway.pending(HydriaSyncQueueGateway.pending(), account)

    fun actions(invoiceId: String): Set<String> = VolumeCacheGateway.actions(invoiceId, pending())

    fun enqueue(action: String, invoices: List<JSONObject>, extra: JSONObject = JSONObject(), recap: JSONObject? = null): String {
        VolumeRules.requireCanEnqueue(invoices.isNotEmpty(), account) {
            invoices.any { action in actions(it.getString("id")) }
        }
        val id = UUID.randomUUID().toString()
        val payload = VolumeOperationGateway.payload(action, invoices, extra, id, account)
        HydriaSyncQueueGateway.enqueue(id, "volume", payload)
        HydriaVolumeCacheGateway.writeBatch(VolumeOperationGateway.localEntries(account, id, payload, recap, ::now))
        return id
    }

    fun bootstrap(token: String, ouvrageId: String = "", month: String = ""): VolumeResult =
        HydriaOperationsGateway.volumeBootstrap(token, ouvrageId, month).let { VolumeResult(it.status, it.body) }

    fun syncOne(token: String, payload: JSONObject): VolumeResult = synchronized(syncLock) {
        val id = payload.getString("local_uuid")
        VolumeConfirmationRules.requireAccount(payload.getString("account_key"), account)
        if (pending().none { it.optString("local_uuid") == id }) {
            return@synchronized VolumeResult(200, JSONObject().put("success", true))
        }
        val response = HydriaOperationsGateway.volumeOperation(token, payload).let { VolumeResult(it.status, it.body) }
        if (response.successful) accept(payload, response.body)
        else VolumeResultGateway.recordFailure(
            id, payload, response.status, response.body, response.error,
            { uuid, p -> HydriaSyncQueueGateway.updatePayload(uuid, p) },
            { uuid, e -> HydriaSyncQueueGateway.markFailed(uuid, e) },
            ::read, ::write,
        )
        response
    }

    private fun accept(payload: JSONObject, response: JSONObject) {
        HydriaVolumeCacheGateway.writeBatch(VolumeResultGateway.acceptedEntries(account, payload, response, ::read, ::now))
        HydriaSyncQueueGateway.remove(payload.getString("local_uuid"))
    }

    fun reviewConflict(id: String, note: String) = synchronized(syncLock) {
        val reviewNote = VolumeConfirmationRules.reviewNote(note)
        val payload = pending().single { it.getString("local_uuid") == id }.getJSONObject("payload")
        HydriaVolumeCacheGateway.writeBatch(VolumeResultGateway.reviewedEntries(account, id, reviewNote, payload, ::read, ::now))
        HydriaSyncQueueGateway.remove(id)
    }

    fun history(): List<JSONObject> = HydriaVolumeCacheGateway.history(account)

    private fun now() = Instant.now().toString()
}
