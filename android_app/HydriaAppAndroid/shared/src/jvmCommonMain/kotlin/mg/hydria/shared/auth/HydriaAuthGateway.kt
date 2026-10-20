package mg.hydria.shared.auth

import kotlinx.coroutines.runBlocking
import mg.hydria.shared.network.HydriaHttpClient
import org.json.JSONObject

/**
 * Facade synchrone pour l'app Android/Desktop (Phase 1, premiere bascule
 * reelle du login). Expose HydriaAuthClient (Ktor, suspend, commonMain)
 * sous forme d'un appel bloquant qui retourne un org.json.JSONObject :
 * ainsi le module `app` n'a besoin d'aucune dependance Ktor/coroutines
 * supplementaire, il ne voit qu'un type deja utilise partout dans
 * HydriaApi.Result. A appeler depuis un thread d'arriere-plan, jamais le
 * thread principal (meme contrainte que HydriaApi.login() actuel).
 */
object HydriaAuthGateway {
    data class Result(val status: Int, val body: JSONObject) {
        val successful: Boolean get() = status in 200..299 && body.optBoolean("success", true)
        val error: String get() = body.optString("error", "Erreur HTTP $status")
    }

    fun loginBlocking(username: String, password: String, deviceLabel: String): Result {
        val client = HydriaHttpClient.create()
        return try {
            runBlocking {
                val ktorResult = HydriaAuthClient.login(client, username, password, deviceLabel)
                Result(ktorResult.status, JSONObject(ktorResult.body.toString()))
            }
        } finally {
            client.close()
        }
    }
}
