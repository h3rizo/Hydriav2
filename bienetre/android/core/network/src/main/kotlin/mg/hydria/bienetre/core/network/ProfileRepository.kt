package mg.hydria.bienetre.core.network

import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import mg.hydria.bienetre.core.model.ProfileOverview
import mg.hydria.bienetre.core.model.ProfileUpdate
import retrofit2.HttpException
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.PATCH
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

interface ProfileApi {
    @GET("api/v1/profiles/me/")
    suspend fun getProfile(): ProfileDto

    @PATCH("api/v1/profiles/me/")
    suspend fun updateProfile(@Body update: ProfileUpdateDto): ProfileDto

    @GET("api/v1/profiles/metrics/")
    suspend fun getMetrics(): ProfileMetricsDto
}

@Singleton
class ProfileRepository @Inject constructor(private val api: ProfileApi) {
    suspend fun load(): ProfileOverview = apiCall {
        coroutineScope {
            val profile = async { api.getProfile() }
            val metrics = async { api.getMetrics() }
            ProfileOverview(profile.await().toModel(), metrics.await().toModel())
        }
    }

    suspend fun update(update: ProfileUpdate): ProfileOverview = apiCall {
        val profile = api.updateProfile(update.toDto()).toModel()
        ProfileOverview(profile, api.getMetrics().toModel())
    }

    private suspend fun <T> apiCall(action: suspend () -> T): T = try {
        action()
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

