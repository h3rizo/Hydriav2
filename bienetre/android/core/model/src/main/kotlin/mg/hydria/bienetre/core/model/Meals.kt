package mg.hydria.bienetre.core.model

data class MealPlanEntry(
    val id: Long,
    val date: String,
    val type: String,
    val recipeId: Long,
    val recipeName: String,
    val recipeIcon: String,
    val imageUrl: String?,
    val calories: Double,
    val proteins: Double,
    val carbohydrates: Double,
    val fats: Double,
    val portions: Double,
    val status: String,
)

data class Recipe(
    val id: Long,
    val name: String,
    val icon: String,
    val imageUrl: String?,
    val preparation: String,
    val mealCategory: String,
    val calories: Double,
    val proteins: Double,
    val carbohydrates: Double,
    val fats: Double,
    val ingredients: List<RecipeIngredient>,
    val personal: Boolean = false,
)

data class RecipeIngredient(val name: String, val quantity: Double, val unit: String)

data class IngredientOption(
    val id: Long,
    val name: String,
    val icon: String,
    val category: String,
    val baseUnit: String,
)

data class MealPlanOverview(
    val meals: List<MealPlanEntry>,
    val recipes: List<Recipe>,
    val ingredients: List<IngredientOption> = emptyList(),
)
