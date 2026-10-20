package mg.hydria.bienetre.feature.meals

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import mg.hydria.bienetre.core.network.CreateMealRequest
import mg.hydria.bienetre.core.network.CreateRecipeRequest
import mg.hydria.bienetre.core.network.GenerateMealPlanRequest
import mg.hydria.bienetre.core.network.MealApi
import mg.hydria.bienetre.core.network.MealPlanDto
import mg.hydria.bienetre.core.network.MealRepository
import mg.hydria.bienetre.core.network.RecipeDto
import mg.hydria.bienetre.core.network.IngredientOptionDto
import mg.hydria.bienetre.core.network.UpdateMealRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MealsViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setUp() { Dispatchers.setMain(dispatcher) }
    @After fun tearDown() { Dispatchers.resetMain() }

    @Test
    fun generationReloadsBackendResult() = runTest(dispatcher) {
        val api = FakeMealApi()
        val viewModel = MealsViewModel(MealRepository(api))
        advanceUntilIdle()

        viewModel.generate()
        advanceUntilIdle()

        val state = viewModel.state.value as MealsUiState.Content
        assertTrue(api.generated)
        assertEquals(1, state.data.meals.size)
        assertTrue(state.data.message?.contains("généré") == true)
    }

    @Test
    fun statusMutationUsesServerRepresentation() = runTest(dispatcher) {
        val api = FakeMealApi().apply { generated = true }
        val viewModel = MealsViewModel(MealRepository(api))
        advanceUntilIdle()
        val meal = (viewModel.state.value as MealsUiState.Content).data.meals.single()

        viewModel.setStatus(meal, "mange")
        advanceUntilIdle()

        val updated = (viewModel.state.value as MealsUiState.Content).data.meals.single()
        assertEquals("mange", updated.status)
    }

    @Test
    fun personalRecipeIsCreatedThenReloadedFromServer() = runTest(dispatcher) {
        val api = FakeMealApi()
        val viewModel = MealsViewModel(MealRepository(api))
        advanceUntilIdle()

        viewModel.createPersonalRecipe("Bol maison", "dejeuner", "Mélanger.", listOf(RecipeIngredientDraft(9, 120.0, "g")))
        advanceUntilIdle()

        val content = (viewModel.state.value as MealsUiState.Content).data
        assertEquals(1, api.recipeCreateCalls)
        assertEquals("120.00", api.lastRecipeRequest?.ingredients?.single()?.quantity)
        assertEquals("g", api.lastRecipeRequest?.ingredients?.single()?.unit)
        assertTrue(content.recipes.any { it.name == "Bol maison" && it.personal })
        assertTrue(content.message?.contains("serveur") == true)
    }

    @Test
    fun invalidPersonalRecipeNeverCallsBackend() = runTest(dispatcher) {
        val api = FakeMealApi()
        val viewModel = MealsViewModel(MealRepository(api))
        advanceUntilIdle()

        viewModel.createPersonalRecipe("x", "dejeuner", "", emptyList())
        advanceUntilIdle()

        assertEquals(0, api.recipeCreateCalls)
    }
}

private class FakeMealApi : MealApi {
    var generated = false
    var recipeCreateCalls = 0
    var lastRecipeRequest: CreateRecipeRequest? = null
    private var status = "prevu"
    private val recipeValues = mutableListOf(RecipeDto(id = 2, name = "Bol vitalité"))
    override suspend fun plans(from: String, to: String) = if (!generated) emptyList() else listOf(meal())
    override suspend fun generate(request: GenerateMealPlanRequest) { generated = true }
    override suspend fun update(id: Long, request: UpdateMealRequest): MealPlanDto {
        request.status?.let { status = it }
        return meal()
    }
    override suspend fun delete(id: Long) = Unit
    override suspend fun create(request: CreateMealRequest) = meal()
    override suspend fun recipes() = recipeValues.toList()
    override suspend fun ingredients() = listOf(IngredientOptionDto(9, "Riz", category = "Féculents", baseUnit = "g"))
    override suspend fun createRecipe(request: CreateRecipeRequest): RecipeDto {
        recipeCreateCalls++
        lastRecipeRequest = request
        return RecipeDto(id = 10, name = request.name, preparation = request.preparation, mealCategory = request.mealCategory, personal = true).also { recipeValues.add(it) }
    }
    private fun meal() = MealPlanDto(1, "2026-08-31", "midi", 2, "Bol vitalité", status = status)
}
