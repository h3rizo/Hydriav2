package mg.hydria.logistique.network

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import retrofit2.Retrofit
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides @Singleton
    fun provideJson(): Json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    @Provides @Singleton
    fun provideHttpClient(tokenStore: SecureTokenStore): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor { chain ->
            val request = chain.request()
            val isAuthenticationCall = request.url.encodedPath.contains("/auth/")
            val token = if (isAuthenticationCall) null else runBlocking { tokenStore.accessToken.first() }
            chain.proceed(
                if (token.isNullOrBlank()) request else request.newBuilder()
                    .header("Authorization", "Bearer $token")
                    .build()
            )
        }
        .build()

    @Provides @Singleton
    fun provideApi(client: OkHttpClient, json: Json): MobileApi = Retrofit.Builder()
        .baseUrl("https://www.hydria.mg/")
        .client(client)
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()
        .create(MobileApi::class.java)
}
