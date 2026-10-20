package mg.hydria.reunions

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * File d'attente des mutations créées hors ligne (nouvel avis, réunion,
 * décision, participant...) : chaque écran de saisie appelle enqueue() pour
 * écrire immédiatement en local (l'utilisateur voit son avis tout de suite,
 * même sans réseau), puis flush() tente de pousser vers le serveur — sans
 * jamais bloquer l'écriture locale si le réseau est absent.
 */
class OutboxSyncer(private val db: ReunionsDatabase, private val session: SessionManager) {

    /** Crée un UUID côté client, l'ajoute au payload sous 'id' (les modèles usagers
     * sont en UUID côté serveur — idempotence garantie si la mutation est rejouée). */
    fun enqueue(operationType: String, payload: JSONObject): String {
        val clientId = payload.optString("id").ifBlank { UUID.randomUUID().toString() }
        payload.put("id", clientId)
        db.enqueueMutation(localUuid = clientId, operationType = operationType, payload = payload)
        return clientId
    }

    /** Tente de pousser toutes les mutations en attente. Retourne le nombre de
     * mutations effectivement acceptées par le serveur (0 si hors ligne). */
    fun flush(): Int {
        val token = session.token ?: return 0
        val pending = db.pendingMutations()
        if (pending.isEmpty()) return 0

        val batch = JSONArray()
        pending.forEach { (localUuid, type, payload) ->
            batch.put(JSONObject().put("local_uuid", localUuid).put("type", type).put("payload", payload))
        }

        val result = HydriaReunionsApi.mutations(token, batch)
        if (!result.successful) return 0

        var acceptedCount = 0
        val results = result.body.optJSONArray("results") ?: JSONArray()
        for (i in 0 until results.length()) {
            val item = results.getJSONObject(i)
            val localUuid = item.optString("local_uuid")
            when (item.optString("status")) {
                "accepted" -> {
                    db.markMutationSynced(localUuid)
                    acceptedCount++
                }
                "rejected" -> db.markMutationFailed(localUuid, item.optString("errors", "Rejeté par le serveur"))
            }
        }
        return acceptedCount
    }
}
