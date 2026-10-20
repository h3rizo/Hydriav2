package mg.hydria.bienetre.core.network

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface AuthApi {
    @POST("api/v1/mobile/auth/token/")
    suspend fun login(@Body request: LoginRequest): TokenResponse

    @POST("api/v1/mobile/auth/register/")
    suspend fun register(@Body request: RegisterRequest): TokenResponse

    @GET("api/v1/mobile/auth/session/")
    suspend fun session(): SessionResponse

    @POST("api/v1/mobile/auth/token/revoke/")
    suspend fun revoke(@Body request: RevokeRequest)
}

interface RefreshApi {
    @POST("api/v1/mobile/auth/token/refresh/")
    suspend fun refresh(@Body request: RefreshRequest): RefreshResponse
}
