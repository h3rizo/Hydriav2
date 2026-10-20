package mg.hydria.bienetre.feature.shopping

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import mg.hydria.bienetre.core.network.ManualShoppingItemRequest
import mg.hydria.bienetre.core.network.ShoppingApi
import mg.hydria.bienetre.core.network.ShoppingCheckRequest
import mg.hydria.bienetre.core.network.ShoppingCheckResponse
import mg.hydria.bienetre.core.network.ShoppingGenerateRequest
import mg.hydria.bienetre.core.network.ShoppingItemDto
import mg.hydria.bienetre.core.network.ShoppingListDto
import mg.hydria.bienetre.core.network.ShoppingPriceRequest
import mg.hydria.bienetre.core.network.ShoppingPriceResponse
import mg.hydria.bienetre.core.network.ShoppingPurchaseDateRequest
import mg.hydria.bienetre.core.network.ShoppingPurchaseDateResponse
import mg.hydria.bienetre.core.network.ShoppingRepository
import mg.hydria.bienetre.core.network.WellbeingArticleDto
import mg.hydria.bienetre.core.network.IngredientOptionDto
import mg.hydria.bienetre.core.network.IngredientPreferenceDto
import mg.hydria.bienetre.core.network.IngredientPreferenceRequest
import mg.hydria.bienetre.core.network.ShoppingPreferenceMetaDto
import mg.hydria.bienetre.core.network.ShoppingVendorDto
import mg.hydria.bienetre.core.network.WellbeingPreferenceDto
import mg.hydria.bienetre.core.network.WellbeingPreferenceMetaDto
import mg.hydria.bienetre.core.network.WellbeingPreferenceRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.IOException

@OptIn(ExperimentalCoroutinesApi::class)
class ShoppingViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setUp() { Dispatchers.setMain(dispatcher) }
    @After fun tearDown() { Dispatchers.resetMain() }

    @Test
    fun checkingItemUsesConfirmedServerState() = runTest(dispatcher) {
        val viewModel = ShoppingViewModel(ShoppingRepository(FakeShoppingApi()))
        advanceUntilIdle()
        val item = (viewModel.state.value as ShoppingUiState.Content).data.items.single()

        viewModel.check(item, true)
        advanceUntilIdle()

        val content = (viewModel.state.value as ShoppingUiState.Content).data
        assertTrue(content.items.single().checked)
        assertEquals("2026-08-31", content.items.single().purchaseDate)
    }

    @Test
    fun invalidGenerationPeriodDoesNotCallApi() = runTest(dispatcher) {
        val api = FakeShoppingApi()
        val viewModel = ShoppingViewModel(ShoppingRepository(api))
        advanceUntilIdle()

        viewModel.generate("2026-09-10", "2026-08-01")
        advanceUntilIdle()

        assertEquals(0, api.generateCalls)
        assertTrue((viewModel.state.value as ShoppingUiState.Content).data.message?.contains("31 jours") == true)
    }

    @Test
    fun ingredientPreferenceIsSavedAndReloaded() = runTest(dispatcher) {
        val api = FakeShoppingApi()
        val viewModel = ShoppingViewModel(ShoppingRepository(api))
        advanceUntilIdle()

        viewModel.saveIngredientPreference(9, 3, disliked = true, unavailable = false, note = "Sans gluten")
        advanceUntilIdle()

        val content = (viewModel.state.value as ShoppingUiState.Content).data
        assertEquals(3L, api.savedIngredient?.preferredVendor)
        assertTrue(content.ingredientPreferences.single().disliked)
        assertEquals("Sans gluten", content.ingredientPreferences.single().note)
    }

    @Test
    fun cachedShoppingListRemainsAvailableOffline() = runTest(dispatcher) {
        val api = FakeShoppingApi()
        val viewModel = ShoppingViewModel(ShoppingRepository(api))
        advanceUntilIdle()

        api.offline = true
        viewModel.load()
        advanceUntilIdle()

        val content = (viewModel.state.value as ShoppingUiState.Content).data
        assertTrue(content.offline)
        assertEquals("Riz", content.items.single().name)
    }

    @Test
    fun offlineCheckIsAppliedOptimisticallyAndQueued() = runTest(dispatcher) {
        val api = FakeShoppingApi()
        val viewModel = ShoppingViewModel(ShoppingRepository(api))
        advanceUntilIdle()
        val item = (viewModel.state.value as ShoppingUiState.Content).data.items.single()

        api.checkOffline = true
        viewModel.check(item, true)
        advanceUntilIdle()

        val content = (viewModel.state.value as ShoppingUiState.Content).data
        assertTrue(content.items.single().checked)
        assertTrue(content.items.single().pendingSync)
        assertTrue(content.message?.contains("Synchronisation automatique") == true)
    }
}

private class FakeShoppingApi : ShoppingApi {
    var generateCalls = 0
    var savedIngredient: IngredientPreferenceRequest? = null
    var offline = false
    var checkOffline = false
    private val ingredientPreferenceValues = mutableListOf<IngredientPreferenceDto>()
    private fun list() = ShoppingListDto(1, "2026-08-31", "2026-09-06", listOf(ShoppingItemDto(4, displayName = "Riz", quantity = "1", unit = "kg")))
    override suspend fun lists(): List<ShoppingListDto> {
        if (offline) throw IOException("offline")
        return listOf(list())
    }
    override suspend fun generate(request: ShoppingGenerateRequest): ShoppingListDto { generateCalls++; return list() }
    override suspend fun check(id: Long, request: ShoppingCheckRequest): ShoppingCheckResponse {
        if (checkOffline) throw IOException("offline")
        return ShoppingCheckResponse(id, request.checked, if (request.checked) "2026-08-31" else null)
    }
    override suspend fun purchaseDate(id: Long, request: ShoppingPurchaseDateRequest) = ShoppingPurchaseDateResponse(id, request.purchaseDate)
    override suspend fun price(id: Long, request: ShoppingPriceRequest) = ShoppingPriceResponse(request.price, request.unit)
    override suspend fun manualItem(id: Long, request: ManualShoppingItemRequest) = list()
    override suspend fun articles() = listOf(WellbeingArticleDto(2, "Gourde"))
    override suspend fun ingredients() = listOf(IngredientOptionDto(9, "Riz"))
    override suspend fun preferenceMeta() = ShoppingPreferenceMetaDto(listOf(ShoppingVendorDto(3, "Marché", 1, "Tana")))
    override suspend fun ingredientPreferences() = ingredientPreferenceValues.toList()
    override suspend fun saveIngredientPreference(request: IngredientPreferenceRequest): IngredientPreferenceDto {
        savedIngredient = request
        return IngredientPreferenceDto(5, request.ingredient, "Riz", request.preferredVendor, "Marché", "Tana", request.disliked, request.unavailable, request.note)
            .also { ingredientPreferenceValues.clear(); ingredientPreferenceValues.add(it) }
    }
    override suspend fun deleteIngredientPreference(id: Long) { ingredientPreferenceValues.removeAll { it.id == id } }
    override suspend fun wellbeingMeta() = WellbeingPreferenceMetaDto()
    override suspend fun wellbeingPreferences() = emptyList<WellbeingPreferenceDto>()
    override suspend fun saveWellbeingPreference(request: WellbeingPreferenceRequest) = WellbeingPreferenceDto(6, request.article, "Gourde", request.preferredVendor, unavailable = request.unavailable, note = request.note)
    override suspend fun deleteWellbeingPreference(id: Long) = Unit
}
