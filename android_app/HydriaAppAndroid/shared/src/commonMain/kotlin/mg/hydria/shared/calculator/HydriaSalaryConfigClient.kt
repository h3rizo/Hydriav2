package mg.hydria.shared.calculator

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.http.HttpHeaders
import mg.hydria.shared.network.toHydriaResult
import mg.hydria.shared.network.HydriaResult

/**
 * Client Ktor pour /mobile/api/salary-calculation-config/, meme schema que
 * HydriaPlanningsClient (GET + token + parametre optionnel). Miroir de
 * HydriaApi.salaryCalculationConfig(). Branche via HydriaOperationsGateway
 * et le repli de session Calculator. La validation reste dans le repository.
 */
object HydriaSalaryConfigClient {
    suspend fun fetch(client: HttpClient, token: String, checksum: String = ""): HydriaResult {
        val response = client.get("/mobile/api/salary-calculation-config/") {
            header(HttpHeaders.Authorization, "Token $token")
            checksum.takeIf { it.isNotBlank() }?.let { parameter("checksum", it) }
        }
        return response.toHydriaResult()
    }
}
