package mg.hydria.shared.repairs

import io.ktor.client.HttpClient
import kotlinx.serialization.json.JsonObject
import mg.hydria.shared.network.HydriaHttpClient
import mg.hydria.shared.network.HydriaResult
import mg.hydria.shared.network.toHydriaResult

/**
 * Client Ktor pour /plannings/reparations/api/{planningId}/marquer-terminee/,
 * POST x-www-form-urlencoded sans champ (form vide), meme helper que
 * HydriaReadingsClient/HydriaAuthClient. Miroir de HydriaApi.finishRepair().
 * Branche via HydriaOperationsGateway et le repli de session Reparations.
 */
object HydriaRepairsClient {
    suspend fun finishRepair(client: HttpClient, token: String, planningId: String): HydriaResult {
        val response = HydriaHttpClient.postForm(
            client = client,
            path = "/plannings/reparations/api/$planningId/marquer-terminee/",
            token = token,
            form = emptyMap(),
        )
        return response.toHydriaResult()
    }
}
