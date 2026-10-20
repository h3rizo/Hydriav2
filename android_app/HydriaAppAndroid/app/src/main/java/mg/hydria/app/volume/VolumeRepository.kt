package mg.hydria.app.volume

import mg.hydria.app.OfflineStore
import mg.hydria.app.HydriaApi
import mg.hydria.app.HydriaNetwork
import org.json.JSONObject
import java.util.UUID

class VolumeRepository(private val store: OfflineStore) {
    companion object { private val syncLock = Any() }
    private val account get() = store.accountKey

    fun read(key: String): JSONObject? = store.volumeRead(account, key)

    fun write(key: String, value: JSONObject) = store.volumeWrite(account, key, value)

    fun savePack(pack: JSONObject) {
        store.volumeWriteBatch(mg.hydria.shared.volume.VolumeCacheGateway.packEntries(account, pack))
    }

    fun invoices(pack: JSONObject): List<JSONObject> =
        mg.hydria.shared.volume.VolumeCacheGateway.invoices(pack, ::read)

    fun pending(): List<JSONObject> =
        mg.hydria.shared.volume.VolumeCacheGateway.pending(store.pending(), account)

    fun actions(invoiceId: String): Set<String> =
        mg.hydria.shared.volume.VolumeCacheGateway.actions(invoiceId, pending())

    /**
     * Note d'architecture : l'enqueue de synchronisation et les ecritures
     * locales (audit/recap) ne sont plus garanties atomiques l'une avec
     * l'autre (elles peuvent vivre sur des connexions differentes depuis la
     * bascule SQLDelight - cf. OfflineStore.migrateVolumeCacheIfNeeded).
     * Les ecritures locales entre elles restent groupees via
     * [OfflineStore.volumeWriteBatch].
     */
    fun enqueue(action: String, invoices: List<JSONObject>, extra: JSONObject = JSONObject(), recap: JSONObject? = null): String {
        mg.hydria.shared.volume.VolumeRules.requireCanEnqueue(invoices.isNotEmpty(), account) {
            invoices.any { action in actions(it.getString("id")) }
        }
        val id = UUID.randomUUID().toString()
        val payload = mg.hydria.shared.volume.VolumeOperationGateway.payload(action, invoices, extra, id, account)
        store.enqueue("volume", payload)
        val entries = mg.hydria.shared.volume.VolumeOperationGateway.localEntries(
            account, id, payload, recap, { java.time.Instant.now().toString() })
        store.volumeWriteBatch(entries)
        return id
    }

    fun syncOne(token: String, payload: JSONObject): HydriaApi.Result = synchronized(syncLock) {
        val id = payload.getString("local_uuid")
        mg.hydria.shared.volume.VolumeConfirmationRules.requireAccount(payload.getString("account_key"), account)
        if (pending().none { it.optString("local_uuid") == id }) {
            return@synchronized HydriaApi.Result(200, JSONObject().put("success", true))
        }
        val response = HydriaNetwork.volumeOperation(token, payload)
        if (response.successful) accept(payload, response.body)
        else {
            mg.hydria.shared.volume.VolumeResultGateway.recordFailure(
                id, payload, response.status, response.body, response.error,
                store::updatePayload, store::markFailed, ::read, ::write,
            )
        }
        response
    }

    fun accept(payload: JSONObject, response: JSONObject) {
        val entries = mg.hydria.shared.volume.VolumeResultGateway.acceptedEntries(
            account, payload, response, ::read, { java.time.Instant.now().toString() })
        store.volumeWriteBatch(entries)
        store.remove(payload.getString("local_uuid"))
    }

    /** « Ouvrage · mois · montant Ar » de l'opération, pour préfixer ses erreurs de synchronisation. */
    fun describe(payload: JSONObject): String =
        mg.hydria.shared.volume.VolumeOperationGateway.describe(payload, ::read)

    fun reviewConflict(id: String, note: String) = synchronized(syncLock) {
        val reviewNote = mg.hydria.shared.volume.VolumeConfirmationRules.reviewNote(note)
        val item = pending().single { it.getString("local_uuid") == id }
        val payload = item.getJSONObject("payload")
        val entries = mg.hydria.shared.volume.VolumeResultGateway.reviewedEntries(
            account, id, reviewNote, payload, ::read, { java.time.Instant.now().toString() })
        store.volumeWriteBatch(entries)
        store.remove(id)
    }

    fun history(): List<JSONObject> = store.volumeHistory(account)
}
