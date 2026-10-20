package mg.hydria.app.pointage

import mg.hydria.app.HydriaApi
import mg.hydria.app.sync.SyncDispatch
import org.json.JSONObject

/**
 * Opérations de synchro du pointage auprès du moteur générique (SyncDispatch).
 *
 * Un refus métier du serveur (HTTP 422 : trop loin, hors créneau…) est DÉFINITIF : le
 * moteur de file rejouerait indéfiniment une opération « échouée », donc on la
 * présente comme terminée à la file et on mémorise le refus dans PointageStore pour
 * l'afficher à l'employé.
 */
object PointageSync {
    fun register() {
        SyncDispatch.register("pointage") { token, payload -> send(token, payload) }
        SyncDispatch.register("pointage_prevu") { token, payload -> HydriaApi.pointageDeclarer(token, payload) }
    }

    fun send(token: String, payload: JSONObject): HydriaApi.Result {
        val result = HydriaApi.pointagePointer(token, payload)
        val uuid = payload.optString("local_uuid")
        val account = payload.optString("_sync_account")
        return when {
            result.status == 422 -> {
                PointageStore.resolve(uuid, PointageStore.REFUSE, result.body.optString("message", result.error),
                    result.body.optString("type").ifBlank { null }, account)
                HydriaApi.Result(200, JSONObject(result.body.toString()).put("success", true).put("refused", true))
            }
            result.successful -> {
                PointageStore.resolve(uuid, PointageStore.OK, result.body.optString("message"),
                    result.body.optString("type").ifBlank { null }, account)
                result
            }
            else -> result
        }
    }
}
