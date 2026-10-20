package mg.hydria.bienetre.core.network

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedMealRepositoryTest {
    @Test
    fun loadMapsVisibleMealsAndNutrition() = runTest {
        val repository = SharedMealRepository(FakeSharedMealApi())

        val overview = repository.load()

        assertEquals("Lova", overview.members.single().name)
        assertEquals("Riz", overview.ingredients.single().name)
        assertEquals(450.0, overview.meals.single().calories, 0.0)
        assertEquals("Lova", overview.meals.single().participants.single().name)
    }

    @Test
    fun createUsesStableDecimalsAndTotalParticipantServings() = runTest {
        val api = FakeSharedMealApi()
        val repository = SharedMealRepository(api)

        repository.createMeal(NewSharedMeal(
            title = "Dîner famille", eatenAt = "2026-08-31T19:30:00", sourceType = "home_cooked", notes = "",
            shoppingDoneBy = 1, cookedBy = 1,
            ingredients = listOf(NewSharedIngredient(9, 250.0, "g")),
            participants = listOf(NewSharedParticipant(1, null, 1.0), NewSharedParticipant(null, 4, 0.5)),
        ))

        val request = requireNotNull(api.created)
        assertEquals("250.00", request.ingredients.single().quantity)
        assertEquals("1.50", request.totalServings)
        assertTrue(request.participants.any { it.householdMember == 4L && it.servings == "0.50" })
    }
}

private class FakeSharedMealApi : SharedMealApi {
    var created: SharedMealRequest? = null
    override suspend fun members() = listOf(HouseholdMemberDto(4, "Lova", "Enfant", 12))
    override suspend fun createMember(request: HouseholdMemberRequest) = HouseholdMemberDto(4, request.name)
    override suspend fun searchProfiles(query: String) = emptyList<ProfileLookupDto>()
    override suspend fun meals() = listOf(SharedMealDto(
        id = 8,
        creator = SharedMealCreatorDto(SharedMealCreatorUserDto("soakoja")),
        title = "Dîner famille",
        eatenAt = "2026-08-31T19:30:00",
        sourceType = "home_cooked",
        sourceLabel = "Cuisine maison",
        totalServings = "1.00",
        participants = listOf(SharedMealParticipantDto(3, householdMemberId = 4, name = "Lova", servings = "1.00", nutrition = SharedMealNutritionDto(kcal = "450.00"))),
    ))
    override suspend fun createMeal(request: SharedMealRequest) { created = request }
    override suspend fun ingredients() = listOf(IngredientOptionDto(9, "Riz", baseUnit = "g"))
}
