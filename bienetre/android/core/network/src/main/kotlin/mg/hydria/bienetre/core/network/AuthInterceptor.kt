package mg.hydria.bienetre.core.network

import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject

class AuthInterceptor @Inject constructor(
    private val tokenStore: TokenStore,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = tokenStore.read()?.access?.let { token ->
            chain.request().newBuilder()
                .header("Authorization", "Bearer $token")
                .build()
        } ?: chain.request()
        return chain.proceed(request)
    }
}
