package mg.hydria.bienetre.core.network

import mg.hydria.bienetre.core.model.Dashboard
import retrofit2.HttpException
import retrofit2.http.GET
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

interface DashboardApi {
    @GET("api/v1/profiles/dashboard/")
    suspend fun getDashboard(): DashboardDto
}

enum class ApiErrorKind { Unauthorized, Forbidden, Network, Server }

class ApiException(val kind: ApiErrorKind, cause: Throwable) : Exception(cause)

@Singleton
class DashboardRepository @Inject constructor(private val api: DashboardApi) {
    suspend fun load(): Dashboard = try {
        api.getDashboard().toModel()
    } catch (error: IOException) {
        throw ApiException(ApiErrorKind.Network, error)
    } catch (error: HttpException) {
        val kind = when (error.code()) {
            401 -> ApiErrorKind.Unauthorized
            403 -> ApiErrorKind.Forbidden
            else -> ApiErrorKind.Server
        }
        throw ApiException(kind, error)
    }
}

