package mg.hydria.bienetre.core.network

import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import mg.hydria.bienetre.core.model.HouseholdMember
import mg.hydria.bienetre.core.model.HouseholdOverview
import mg.hydria.bienetre.core.model.ProfileLookup
import mg.hydria.bienetre.core.model.SharedMeal
import mg.hydria.bienetre.core.model.SharedMealIngredient
import mg.hydria.bienetre.core.model.SharedMealParticipant
import retrofit2.HttpException
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query
import java.io.IOException
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

@Serializable
data class HouseholdMemberDto(
    val id: Long,
    val name: String,
    val relationship: String = "",
    val age: Int? = null,
    val sex: String = "",
    @SerialName("linked_profile") val linkedProfileId: Long? = null,
    @SerialName("linked_profile_display_name") val linkedProfileName: String = "",
)

@Serializable data class ProfileLookupDto(val id: Long, @SerialName("display_name") val displayName: String)
@Serializable data class SharedIngredientRefDto(val id: Long, val name: String)
@Serializable data class SharedMealIngredientDto(val id: Long, val ingredient: SharedIngredientRefDto, val quantity: String, val unit: String)
@Serializable data class SharedMealNutritionDto(
    val kcal: String = "0",
    val protein: String = "0",
    val carbs: String = "0",
    val fat: String = "0",
)
@Serializable data class SharedMealParticipantDto(
    val id: Long,
    @SerialName("profile") val profileId: Long? = null,
    @SerialName("household_member") val householdMemberId: Long? = null,
    @SerialName("participant_name") val name: String,
    @SerialName("servings_eaten") val servings: String,
    @SerialName("nutrition_totals") val nutrition: SharedMealNutritionDto = SharedMealNutritionDto(),
)
@Serializable data class SharedMealCreatorUserDto(val username: String)
@Serializable data class SharedMealCreatorDto(val user: SharedMealCreatorUserDto)
@Serializable data class SharedMealDto(
    val id: Long,
    @SerialName("created_by") val creator: SharedMealCreatorDto,
    val title: String,
    @SerialName("eaten_at") val eatenAt: String,
    @SerialName("source_type") val sourceType: String,
    @SerialName("source_type_label") val sourceLabel: String,
    @SerialName("total_servings") val totalServings: String,
    val notes: String = "",
    val ingredients: List<SharedMealIngredientDto> = emptyList(),
    val participants: List<SharedMealParticipantDto> = emptyList(),
)

@Serializable data class HouseholdMemberRequest(
    val name: String,
    val relationship: String = "",
    val age: Int? = null,
    val sex: String = "",
    @SerialName("linked_profile") val linkedProfileId: Long? = null,
)
@Serializable data class SharedMealIngredientRequest(val ingredient: Long, val quantity: String, val unit: String)
@Serializable data class SharedMealParticipantRequest(
    val profile: Long? = null,
    @SerialName("household_member") val householdMember: Long? = null,
    @SerialName("servings_eaten") val servings: String,
)
@Serializable data class SharedMealRequest(
    val title: String,
    @SerialName("eaten_at") val eatenAt: String,
    @SerialName("source_type") val sourceType: String,
    @SerialName("total_servings") val totalServings: String,
    val notes: String,
    @SerialName("shopping_done_by") val shoppingDoneBy: Long? = null,
    @SerialName("cooked_by") val cookedBy: Long? = null,
    val ingredients: List<SharedMealIngredientRequest>,
    val participants: List<SharedMealParticipantRequest>,
)

interface SharedMealApi {
    @GET("api/v1/auth/household-members/") suspend fun members(): List<HouseholdMemberDto>
    @POST("api/v1/auth/household-members/") suspend fun createMember(@Body request: HouseholdMemberRequest): HouseholdMemberDto
    @GET("api/v1/auth/profiles/search/") suspend fun searchProfiles(@Query("q") query: String): List<ProfileLookupDto>
    @GET("api/v1/auth/meals/") suspend fun meals(): List<SharedMealDto>
    @POST("api/v1/auth/meals/") suspend fun createMeal(@Body request: SharedMealRequest)
    @GET("api/v1/nutrition/ingredients/") suspend fun ingredients(): List<IngredientOptionDto>
}

data class NewHouseholdMember(val name: String, val relationship: String, val age: Int?, val sex: String, val linkedProfileId: Long?)
data class NewSharedIngredient(val id: Long, val quantity: Double, val unit: String)
data class NewSharedParticipant(val profileId: Long?, val householdMemberId: Long?, val servings: Double)
data class NewSharedMeal(
    val title: String,
    val eatenAt: String,
    val sourceType: String,
    val notes: String,
    val shoppingDoneBy: Long?,
    val cookedBy: Long?,
    val ingredients: List<NewSharedIngredient>,
    val participants: List<NewSharedParticipant>,
)

@Singleton
class SharedMealRepository @Inject constructor(private val api: SharedMealApi) {
    suspend fun load(): HouseholdOverview = safe {
        coroutineScope {
            val members = async { api.members() }
            val meals = async { api.meals() }
            val ingredients = async { api.ingredients() }
            HouseholdOverview(members.await().map { it.toModel() }, meals.await().map { it.toModel() }, ingredients.await().map { it.toModel() })
        }
    }
    suspend fun searchProfiles(query: String): List<ProfileLookup> = safe { api.searchProfiles(query.trim()).map { ProfileLookup(it.id, it.displayName) } }
    suspend fun createMember(value: NewHouseholdMember) = safe {
        api.createMember(HouseholdMemberRequest(value.name.trim(), value.relationship.trim(), value.age, value.sex, value.linkedProfileId)).toModel()
    }
    suspend fun createMeal(value: NewSharedMeal) = safe {
        val totalServings = value.participants.sumOf { it.servings }
        api.createMeal(SharedMealRequest(
            value.title.trim(), value.eatenAt, value.sourceType, totalServings.decimal(), value.notes.trim(),
            value.shoppingDoneBy, value.cookedBy,
            value.ingredients.map { SharedMealIngredientRequest(it.id, it.quantity.decimal(), it.unit) },
            value.participants.map { SharedMealParticipantRequest(it.profileId, it.householdMemberId, it.servings.decimal()) },
        ))
    }
    private suspend fun <T> safe(action: suspend () -> T): T = try { action() }
    catch (error: IOException) { throw ApiException(ApiErrorKind.Network, error) }
    catch (error: HttpException) { throw ApiException(when (error.code()) { 401 -> ApiErrorKind.Unauthorized; 403 -> ApiErrorKind.Forbidden; else -> ApiErrorKind.Server }, error) }
}

private fun HouseholdMemberDto.toModel() = HouseholdMember(id, name, relationship, age, sex, linkedProfileId, linkedProfileName)
private fun SharedMealDto.toModel() = SharedMeal(
    id, creator.user.username, title, eatenAt, sourceType, sourceLabel, totalServings.number(), notes,
    ingredients.map { SharedMealIngredient(it.id, it.ingredient.id, it.ingredient.name, it.quantity.number(), it.unit) },
    participants.map { SharedMealParticipant(it.id, it.profileId, it.householdMemberId, it.name, it.servings.number(), it.nutrition.kcal.number(), it.nutrition.protein.number(), it.nutrition.carbs.number(), it.nutrition.fat.number()) },
)
private fun String?.number() = this?.replace(',', '.')?.toDoubleOrNull() ?: 0.0
private fun Double.decimal() = "%.2f".format(Locale.US, this)
