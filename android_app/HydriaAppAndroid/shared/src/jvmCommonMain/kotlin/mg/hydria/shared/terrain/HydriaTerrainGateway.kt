package mg.hydria.shared.terrain

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.jsonObject
import mg.hydria.shared.network.HydriaHttpClient
import org.json.JSONObject

/**
 * Facade synchrone du domaine Terrain pour l'app Android/Desktop, meme role
 * que HydriaAuthGateway pour le login : expose HydriaTerrainClient (Ktor,
 * suspend, commonMain) sous forme d'appels bloquants renvoyant un
 * org.json.JSONObject, pour que le module `app` n'ait besoin d'aucune
 * dependance Ktor/coroutines. A appeler depuis un thread d'arriere-plan,
 * jamais le thread principal (meme contrainte que HydriaApi).
 *
 * Discipline de repli (cf. OfflineStore.useNewTerrainNetwork) : [probe] est
 * lancee UNE fois au demarrage ; si l'appelant attrape une exception Ktor
 * ensuite, il eteint le flag et TOUS les appels Terrain repassent par
 * HydriaApi (HttpURLConnection) pour le reste de la session - jamais de
 * melange en cours de route.
 */
object HydriaTerrainGateway {
    data class Result(val status: Int, val body: JSONObject) {
        val successful: Boolean get() = status in 200..299 && body.optBoolean("success", true)
        val error: String get() = body.optString("error", "Erreur HTTP $status")
    }

    /**
     * Sonde d'initialisation : cree puis ferme immediatement un client Ktor.
     * Jette si le moteur HTTP de la plateforme est indisponible - l'appelant
     * desactive alors le transport Ktor pour toute la session.
     */
    fun probe() {
        HydriaHttpClient.create().close()
    }

    fun prepareTourBlocking(token: String, snapshotVersion: String?): Result {
        val client = HydriaHttpClient.create()
        return try {
            runBlocking {
                val result = HydriaTerrainClient.prepareTour(client, token, snapshotVersion)
                Result(result.status, JSONObject(result.body.toString()))
            }
        } finally {
            client.close()
        }
    }

    fun saveItemBlocking(token: String, payload: JSONObject): Result {
        val client = HydriaHttpClient.create()
        return try {
            runBlocking {
                val jsonPayload = HydriaHttpClient.json.parseToJsonElement(payload.toString()).jsonObject
                val result = HydriaTerrainClient.saveItem(client, token, jsonPayload)
                Result(result.status, JSONObject(result.body.toString()))
            }
        } finally {
            client.close()
        }
    }
}
