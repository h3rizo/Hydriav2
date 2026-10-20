package mg.hydria.bienetre.core.network

import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import mg.hydria.bienetre.core.model.MealPlanEntry
import mg.hydria.bienetre.core.model.MealPlanOverview
import retrofit2.HttpException
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

interface MealApi {
    @GET("api/v1/meal-plans/")
    suspend fun plans(@Query("date_from") from: String, @Query("date_to") to: String): List<MealPlanDto>
    @POST("api/v1/meal-plans/generate/")
    suspend fun generate(@Body request: GenerateMealPlanRequest)
    @PATCH("api/v1/meal-plans/{id}/")
    suspend fun update(@Path("id") id: Long, @Body request: UpdateMealRequest): MealPlanDto
    @DELETE("api/v1/meal-plans/{id}/")
    suspend fun delete(@Path("id") id: Long)
    @POST("api/v1/meal-plans/")
    suspend fun create(@Body request: CreateMealRequest): MealPlanDto
    @GET("api/v1/nutrition/recipes/")
    suspend fun recipes(): List<RecipeDto>
    @GET("api/v1/nutrition/ingredients/")
    suspend fun ingredients(): List<IngredientOptionDto>
    @POST("api/v1/nutrition/recipes/")
    suspend fun createRecipe(@Body request: CreateRecipeRequest): RecipeDto
}

data class NewRecipeIngredient(val ingredientId: Long, val quantity: Double, val unit: String)
data class NewPersonalRecipe(val name: String, val preparation: String, val mealCategory: String, val ingredients: List<NewRecipeIngredient>)

@Singleton
class MealRepository @Inject constructor(private val api: MealApi) {
    suspend fun load(from: String, to: String): MealPlanOverview = safe {
        coroutineScope {
            val meals = async { api.plans(from, to) }
            val recipes = async { api.recipes() }
            val ingredients = async { api.ingredients() }
            MealPlanOverview(meals.await().map { it.toModel() }, recipes.await().map { it.toModel() }, ingredients.await().map { it.toModel() })
        }
    }
    suspend fun generate(from: String, to: String) = safe { api.generate(GenerateMealPlanRequest(from, to)) }
    suspend fun update(id: Long, status: String? = null, portions: Double? = null): MealPlanEntry = safe {
        api.update(id, UpdateMealRequest(portions?.let { "%.2f".format(java.util.Locale.US, it) }, status)).toModel()
    }
    suspend fun delete(id: Long) = safe { api.delete(id) }
    suspend fun create(date: String, type: String, recipeId: Long): MealPlanEntry = safe {
        api.create(CreateMealRequest(date, type, recipeId)).toModel()
    }
    suspend fun createRecipe(value: NewPersonalRecipe): mg.hydria.bienetre.core.model.Recipe = safe {
        api.createRecipe(
            CreateRecipeRequest(
                name = value.name.trim(),
                preparation = value.preparation.trim(),
                mealCategory = value.mealCategory,
                ingredients = value.ingredients.map {
                    CreateRecipeIngredientRequest(it.ingredientId, "%.2f".format(java.util.Locale.US, it.quantity), it.unit)
                },
            ),
        ).toModel()
    }
    private suspend fun <T> safe(action: suspend () -> T): T = try { action() }
    catch (error: IOException) { throw ApiException(ApiErrorKind.Network, error) }
    catch (error: HttpException) {
        throw ApiException(when (error.code()) { 401 -> ApiErrorKind.Unauthorized; 403 -> ApiErrorKind.Forbidden; else -> ApiErrorKind.Server }, error)
    }
}
