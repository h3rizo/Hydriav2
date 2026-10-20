package mg.hydria.bienetre.core.network

import android.util.Base64
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mg.hydria.bienetre.core.model.ShoppingItem
import mg.hydria.bienetre.core.model.ShoppingOverview
import mg.hydria.bienetre.core.model.IngredientSupplyPreference
import mg.hydria.bienetre.core.model.VendorOption
import mg.hydria.bienetre.core.model.WellbeingSupplyPreference
import retrofit2.HttpException
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.DELETE
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import java.io.IOException
import java.security.MessageDigest
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

interface ShoppingApi {
    @GET("api/v1/shopping/lists/") suspend fun lists(): List<ShoppingListDto>
    @POST("api/v1/shopping/lists/generate/") suspend fun generate(@Body request: ShoppingGenerateRequest): ShoppingListDto
    @PATCH("api/v1/shopping/items/{id}/check/") suspend fun check(@Path("id") id: Long, @Body request: ShoppingCheckRequest): ShoppingCheckResponse
    @PATCH("api/v1/shopping/items/{id}/purchase-date/") suspend fun purchaseDate(@Path("id") id: Long, @Body request: ShoppingPurchaseDateRequest): ShoppingPurchaseDateResponse
    @PATCH("api/v1/shopping/items/{id}/price/") suspend fun price(@Path("id") id: Long, @Body request: ShoppingPriceRequest): ShoppingPriceResponse
    @POST("api/v1/shopping/lists/{id}/manual-items/") suspend fun manualItem(@Path("id") id: Long, @Body request: ManualShoppingItemRequest): ShoppingListDto
    @GET("api/v1/nutrition/wellbeing-articles/") suspend fun articles(): List<WellbeingArticleDto>
    @GET("api/v1/nutrition/ingredients/") suspend fun ingredients(): List<IngredientOptionDto>
    @GET("api/v1/profiles/shopping-preferences/meta/") suspend fun preferenceMeta(): ShoppingPreferenceMetaDto
    @GET("api/v1/profiles/shopping-preferences/") suspend fun ingredientPreferences(): List<IngredientPreferenceDto>
    @POST("api/v1/profiles/shopping-preferences/") suspend fun saveIngredientPreference(@Body request: IngredientPreferenceRequest): IngredientPreferenceDto
    @DELETE("api/v1/profiles/shopping-preferences/item/{id}/") suspend fun deleteIngredientPreference(@Path("id") id: Long)
    @GET("api/v1/profiles/wellbeing-articles/meta/") suspend fun wellbeingMeta(): WellbeingPreferenceMetaDto
    @GET("api/v1/profiles/wellbeing-articles/preferences/") suspend fun wellbeingPreferences(): List<WellbeingPreferenceDto>
    @POST("api/v1/profiles/wellbeing-articles/preferences/") suspend fun saveWellbeingPreference(@Body request: WellbeingPreferenceRequest): WellbeingPreferenceDto
    @DELETE("api/v1/profiles/wellbeing-articles/preferences/item/{id}/") suspend fun deleteWellbeingPreference(@Path("id") id: Long)
}

@Singleton
class ShoppingRepository @Inject constructor(
    private val api: ShoppingApi,
    private val dao: ShoppingDao,
    private val syncScheduler: ShoppingSyncScheduler,
    private val json: Json,
    private val tokenStore: TokenStore,
) {
    private val cacheMutex = Mutex()

    constructor(api: ShoppingApi) : this(api, MemoryShoppingDao(), NoOpShoppingSyncScheduler, Json { ignoreUnknownKeys = true }, FixedTokenStore)

    suspend fun load(): ShoppingOverview = try {
        val scope = scopeKey()
        val payload = safe { fetch() }
        cacheMutex.withLock { savePayload(scope, payload) }
        payload.toModel(dao.pendingChecks(scope), offline = false)
    } catch (error: ApiException) {
        if (error.kind != ApiErrorKind.Network) throw error
        val scope = scopeKey()
        val cached = cacheMutex.withLock { cachedPayload(scope) } ?: throw error
        cached.toModel(dao.pendingChecks(scope), offline = true)
    }

    private suspend fun fetch(): ShoppingCachePayload = coroutineScope {
        val lists = async { api.lists() }
        val articles = async { api.articles() }
        val ingredients = async { api.ingredients() }
        val meta = async { api.preferenceMeta() }
        val ingredientPreferences = async { api.ingredientPreferences() }
        val wellbeingMeta = async { api.wellbeingMeta() }
        val wellbeingPreferences = async { api.wellbeingPreferences() }
        val articleMetadata = wellbeingMeta.await().articles.associateBy { it.id }
        ShoppingCachePayload(
            lists = lists.await(),
            articles = articles.await(),
            ingredients = ingredients.await(),
            vendors = meta.await().vendors,
            ingredientPreferences = ingredientPreferences.await(),
            articleMetadata = articleMetadata.values.toList(),
            wellbeingPreferences = wellbeingPreferences.await(),
        )
    }
    suspend fun generate(start: String, end: String) = safe { api.generate(ShoppingGenerateRequest(start, end)).toModel() }
    suspend fun check(item: ShoppingItem, checked: Boolean): ShoppingItem = cacheMutex.withLock {
        val scope = scopeKey()
        val pending = PendingShoppingCheckEntity(scope, item.id, checked, System.currentTimeMillis())
        dao.savePendingCheck(pending)
        updateCachedItem(scope, item.id) { it.copy(checked = checked) }
        syncScheduler.schedule()
        val optimistic = item.copy(checked = checked, pendingSync = true)
        try {
            val response = safe { api.check(item.id, ShoppingCheckRequest(checked)) }
            dao.deletePendingCheck(scope, item.id, checked)
            updateCachedItem(scope, item.id) { it.copy(checked = response.checked, purchaseDate = response.purchaseDate) }
            optimistic.copy(checked = response.checked, purchaseDate = response.purchaseDate, pendingSync = false)
        } catch (error: ApiException) {
            if (error.kind == ApiErrorKind.Network) optimistic
            else {
                dao.deletePendingCheck(scope, item.id, checked)
                updateCachedItem(scope, item.id) { it.copy(checked = item.checked, purchaseDate = item.purchaseDate) }
                throw error
            }
        }
    }

    suspend fun syncPendingChecks() = cacheMutex.withLock {
        val scope = scopeKey()
        dao.pendingChecks(scope).forEach { pending ->
            val response = safe { api.check(pending.itemId, ShoppingCheckRequest(pending.checked)) }
            if (dao.deletePendingCheck(scope, pending.itemId, pending.checked) > 0) {
                updateCachedItem(scope, pending.itemId) { it.copy(checked = response.checked, purchaseDate = response.purchaseDate) }
            }
        }
    }
    suspend fun purchaseDate(item: ShoppingItem, date: String?): ShoppingItem = safe {
        item.copy(purchaseDate = api.purchaseDate(item.id, ShoppingPurchaseDateRequest(date)).purchaseDate)
    }
    suspend fun price(item: ShoppingItem, value: Double, unit: String): ShoppingItem = safe {
        val response = api.price(item.id, ShoppingPriceRequest("%.2f".format(Locale.US, value), unit))
        item.copy(latestPrice = response.price.replace(',', '.').toDoubleOrNull(), latestPriceUnit = response.unit)
    }
    suspend fun addManual(listId: Long, articleId: Long, quantity: Double, unit: String) = safe {
        api.manualItem(listId, ManualShoppingItemRequest(articleId, "%.2f".format(Locale.US, quantity), unit)).toModel()
    }
    suspend fun saveIngredientPreference(ingredientId: Long, vendorId: Long?, disliked: Boolean, unavailable: Boolean, note: String) = safe {
        api.saveIngredientPreference(IngredientPreferenceRequest(ingredientId, vendorId, disliked, unavailable, note.trim())).toModel()
    }
    suspend fun deleteIngredientPreference(id: Long) = safe { api.deleteIngredientPreference(id) }
    suspend fun saveWellbeingPreference(articleId: Long, vendorId: Long?, unavailable: Boolean, note: String) = safe {
        api.saveWellbeingPreference(WellbeingPreferenceRequest(articleId, vendorId, unavailable, note.trim())).toModel()
    }
    suspend fun deleteWellbeingPreference(id: Long) = safe { api.deleteWellbeingPreference(id) }

    private suspend fun cachedPayload(scope: String): ShoppingCachePayload? = dao.cache(scope)?.payload?.let {
        runCatching { json.decodeFromString<ShoppingCachePayload>(it) }.getOrNull()
    }

    private suspend fun savePayload(scope: String, payload: ShoppingCachePayload) {
        dao.saveCache(ShoppingCacheEntity(scope, json.encodeToString(payload), System.currentTimeMillis()))
    }

    private suspend fun updateCachedItem(scope: String, itemId: Long, transform: (ShoppingItemDto) -> ShoppingItemDto) {
        val payload = cachedPayload(scope) ?: return
        savePayload(scope, payload.copy(lists = payload.lists.map { list ->
            list.copy(items = list.items.map { if (it.id == itemId) transform(it) else it })
        }))
    }

    private fun scopeKey(): String {
        val tokens = tokenStore.read()
            ?: throw ApiException(ApiErrorKind.Unauthorized, IllegalStateException("No authenticated session"))
        val userId = runCatching {
            val payload = tokens.access.split('.')[1]
            val decoded = Base64.decode(payload, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
            val claims = json.parseToJsonElement(decoded.toString(Charsets.UTF_8)).jsonObject
            claims["user_id"]?.jsonPrimitive?.contentOrNull ?: claims["sub"]?.jsonPrimitive?.contentOrNull
        }.getOrNull()
        if (!userId.isNullOrBlank()) return "user:$userId"
        return MessageDigest.getInstance("SHA-256").digest(tokens.refresh.toByteArray())
            .take(16).joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private suspend fun <T> safe(action: suspend () -> T): T = try { action() }
    catch (error: IOException) { throw ApiException(ApiErrorKind.Network, error) }
    catch (error: HttpException) { throw ApiException(when (error.code()) { 401 -> ApiErrorKind.Unauthorized; 403 -> ApiErrorKind.Forbidden; else -> ApiErrorKind.Server }, error) }
}

@Serializable
private data class ShoppingCachePayload(
    val lists: List<ShoppingListDto>,
    val articles: List<WellbeingArticleDto>,
    val ingredients: List<IngredientOptionDto>,
    val vendors: List<ShoppingVendorDto>,
    val ingredientPreferences: List<IngredientPreferenceDto>,
    val articleMetadata: List<WellbeingArticleOptionDto>,
    val wellbeingPreferences: List<WellbeingPreferenceDto>,
) {
    fun toModel(pending: List<PendingShoppingCheckEntity>, offline: Boolean): ShoppingOverview {
        val pendingById = pending.associateBy { it.itemId }
        val metadata = articleMetadata.associateBy { it.id }
        return ShoppingOverview(
            lists = lists.map { list ->
                list.toModel().copy(items = list.items.map { dto ->
                    val queued = pendingById[dto.id]
                    dto.toModel().copy(
                        checked = queued?.checked ?: dto.checked,
                        pendingSync = queued != null,
                    )
                })
            }.sortedByDescending { it.id },
            articles = articles.map { dto ->
                val details = metadata[dto.id]
                dto.toModel().copy(category = details?.category.orEmpty(), vendorIds = details?.vendorIds.orEmpty().toSet())
            },
            ingredients = ingredients.map { it.toModel() },
            vendors = vendors.map { VendorOption(it.id, it.name, it.cityId, it.cityName) },
            ingredientPreferences = ingredientPreferences.map { it.toModel() },
            wellbeingPreferences = wellbeingPreferences.map { it.toModel() },
            offline = offline,
        )
    }
}

private object NoOpShoppingSyncScheduler : ShoppingSyncScheduler { override fun schedule() = Unit }
private object FixedTokenStore : TokenStore {
    override fun read() = StoredTokens("test-access", "test-refresh")
    override fun write(tokens: StoredTokens) = Unit
    override fun clear() = Unit
}

private class MemoryShoppingDao : ShoppingDao {
    private val cached = linkedMapOf<String, ShoppingCacheEntity>()
    private val pending = linkedMapOf<Pair<String, Long>, PendingShoppingCheckEntity>()
    override suspend fun cache(scope: String) = cached[scope]
    override suspend fun saveCache(cache: ShoppingCacheEntity) { cached[cache.scope] = cache }
    override suspend fun pendingChecks(scope: String) = pending.values.filter { it.scope == scope }.sortedBy { it.updatedAt }
    override suspend fun pendingCheck(scope: String, itemId: Long) = pending[scope to itemId]
    override suspend fun savePendingCheck(check: PendingShoppingCheckEntity) { pending[check.scope to check.itemId] = check }
    override suspend fun deletePendingCheck(scope: String, itemId: Long, checked: Boolean): Int =
        if (pending[scope to itemId]?.checked == checked) { pending.remove(scope to itemId); 1 } else 0
}

private fun IngredientPreferenceDto.toModel() = IngredientSupplyPreference(id, ingredient, ingredientName, preferredVendor, preferredVendorName, preferredVendorCity, disliked, unavailable, note)
private fun WellbeingPreferenceDto.toModel() = WellbeingSupplyPreference(id, article, articleName, preferredVendor, preferredVendorName, preferredVendorCity, unavailable, note)
