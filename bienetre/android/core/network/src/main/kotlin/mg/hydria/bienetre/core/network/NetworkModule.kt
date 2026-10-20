package mg.hydria.bienetre.core.network

import android.content.Context
import androidx.room.Room
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import okhttp3.MediaType.Companion.toMediaType
import javax.inject.Named
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class TokenStoreModule {
    @Binds
    @Singleton
    abstract fun bindTokenStore(store: EncryptedTokenStore): TokenStore

    @Binds
    @Singleton
    abstract fun bindShoppingSyncScheduler(scheduler: WorkManagerShoppingSyncScheduler): ShoppingSyncScheduler
}

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides
    @Singleton
    fun database(@ApplicationContext context: Context): BienetreDatabase =
        Room.databaseBuilder(context, BienetreDatabase::class.java, "bienetre.db").build()

    @Provides
    fun shoppingDao(database: BienetreDatabase): ShoppingDao = database.shoppingDao()

    @Provides
    @Singleton
    fun json(): Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    @Provides
    @Singleton
    @Named("refresh")
    fun refreshClient(): OkHttpClient = OkHttpClient.Builder().build()

    @Provides
    @Singleton
    fun refreshApi(json: Json, @Named("refresh") client: OkHttpClient): RefreshApi =
        retrofit(json, client).create(RefreshApi::class.java)

    @Provides
    @Singleton
    fun authenticatedClient(
        authInterceptor: AuthInterceptor,
        authenticator: TokenAuthenticator,
    ): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(authInterceptor)
        .addInterceptor(
            HttpLoggingInterceptor().apply {
                // BODY en debug (au lieu de BASIC) : nécessaire pour diagnostiquer les échecs
                // de désérialisation côté client (ex. "L'action sportive a échoué"), où la
                // requête HTTP réussit (200) mais le corps ne correspond pas au DTO attendu —
                // BASIC ne logue que la ligne de requête/réponse, jamais le contenu JSON.
                level = if (BuildConfig.DEBUG) {
                    HttpLoggingInterceptor.Level.BODY
                } else {
                    HttpLoggingInterceptor.Level.NONE
                }
                redactHeader("Authorization")
            },
        )
        .authenticator(authenticator)
        .build()

    @Provides
    @Singleton
    fun authApi(json: Json, client: OkHttpClient): AuthApi =
        retrofit(json, client).create(AuthApi::class.java)

    @Provides
    @Singleton
    fun dashboardApi(json: Json, client: OkHttpClient): DashboardApi =
        retrofit(json, client).create(DashboardApi::class.java)

    @Provides
    @Singleton
    fun profileApi(json: Json, client: OkHttpClient): ProfileApi =
        retrofit(json, client).create(ProfileApi::class.java)

    @Provides
    @Singleton
    fun mealApi(json: Json, client: OkHttpClient): MealApi =
        retrofit(json, client).create(MealApi::class.java)

    @Provides
    @Singleton
    fun sharedMealApi(json: Json, client: OkHttpClient): SharedMealApi =
        retrofit(json, client).create(SharedMealApi::class.java)

    @Provides
    @Singleton
    fun shoppingApi(json: Json, client: OkHttpClient): ShoppingApi =
        retrofit(json, client).create(ShoppingApi::class.java)

    @Provides
    @Singleton
    fun fitnessApi(json: Json, client: OkHttpClient): FitnessApi =
        retrofit(json, client).create(FitnessApi::class.java)

    @Provides
    @Singleton
    fun progressApi(json: Json, client: OkHttpClient): ProgressApi =
        retrofit(json, client).create(ProgressApi::class.java)

    private fun retrofit(json: Json, client: OkHttpClient): Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(client)
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()
}
