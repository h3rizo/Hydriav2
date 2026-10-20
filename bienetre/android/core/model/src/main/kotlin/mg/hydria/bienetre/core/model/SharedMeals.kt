package mg.hydria.bienetre.core.model

data class HouseholdMember(
    val id: Long,
    val name: String,
    val relationship: String,
    val age: Int?,
    val sex: String,
    val linkedProfileId: Long?,
    val linkedProfileName: String,
)

data class ProfileLookup(val id: Long, val displayName: String)

data class SharedMealIngredient(val id: Long, val ingredientId: Long, val name: String, val quantity: Double, val unit: String)

data class SharedMealParticipant(
    val id: Long,
    val profileId: Long?,
    val householdMemberId: Long?,
    val name: String,
    val servings: Double,
    val calories: Double,
    val proteins: Double,
    val carbohydrates: Double,
    val fats: Double,
)

data class SharedMeal(
    val id: Long,
    val creatorUsername: String,
    val title: String,
    val eatenAt: String,
    val sourceType: String,
    val sourceLabel: String,
    val totalServings: Double,
    val notes: String,
    val ingredients: List<SharedMealIngredient>,
    val participants: List<SharedMealParticipant>,
) {
    val calories: Double get() = participants.sumOf { it.calories }
    val proteins: Double get() = participants.sumOf { it.proteins }
    val carbohydrates: Double get() = participants.sumOf { it.carbohydrates }
    val fats: Double get() = participants.sumOf { it.fats }
}

data class HouseholdOverview(
    val members: List<HouseholdMember>,
    val meals: List<SharedMeal>,
    val ingredients: List<IngredientOption>,
)
