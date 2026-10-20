package mg.hydria.bienetre.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import mg.hydria.bienetre.core.model.MealPlanEntry
import mg.hydria.bienetre.core.model.Recipe
import mg.hydria.bienetre.core.model.RecipeIngredient
import mg.hydria.bienetre.core.model.IngredientOption

@Serializable
data class MealPlanDto(
    val id: Long,
    val date: String,
    @SerialName("repas") val type: String,
    @SerialName("recipe") val recipeId: Long,
    @SerialName("recipe_nom") val recipeName: String = "",
    @SerialName("recipe_icone") val recipeIcon: String? = null,
    @SerialName("recipe_image_url") val remoteImageUrl: String? = null,
    @SerialName("recipe_image_file_url") val uploadedImageUrl: String? = null,
    @SerialName("recipe_calories") val calories: String? = null,
    @SerialName("recipe_proteines") val proteins: String? = null,
    @SerialName("recipe_glucides") val carbohydrates: String? = null,
    @SerialName("recipe_lipides") val fats: String? = null,
    @SerialName("nombre_portions") val portions: String = "1",
    @SerialName("statut") val status: String,
)

@Serializable
data class RecipeIngredientDto(
    @SerialName("ingredient") val ingredientId: Long? = null,
    @SerialName("ingredient_nom") val name: String = "",
    @SerialName("quantite") val quantity: String = "0",
    @SerialName("unite") val unit: String = "",
)

@Serializable
data class RecipeDto(
    val id: Long,
    @SerialName("nom") val name: String,
    @SerialName("icone") val icon: String? = null,
    @SerialName("image_url") val remoteImageUrl: String? = null,
    @SerialName("image_file_url") val uploadedImageUrl: String? = null,
    @SerialName("preparation") val preparation: String = "",
    @SerialName("categorie_repas") val mealCategory: String = "",
    @SerialName("calories_totales") val calories: String? = null,
    @SerialName("proteines_totales") val proteins: String? = null,
    @SerialName("glucides_totaux") val carbohydrates: String? = null,
    @SerialName("lipides_totaux") val fats: String? = null,
    @SerialName("recipe_ingredients") val ingredients: List<RecipeIngredientDto> = emptyList(),
    @SerialName("is_personal") val personal: Boolean = false,
)

@Serializable
data class IngredientOptionDto(
    val id: Long,
    @SerialName("nom") val name: String,
    @SerialName("icone") val icon: String = "",
    @SerialName("categorie") val category: String = "",
    @SerialName("unite_base") val baseUnit: String = "g",
)

@Serializable
data class CreateRecipeIngredientRequest(
    @SerialName("ingredient") val ingredientId: Long,
    @SerialName("quantite") val quantity: String,
    @SerialName("unite") val unit: String,
)

@Serializable
data class CreateRecipeRequest(
    @SerialName("nom") val name: String,
    @SerialName("icone") val icon: String = "🍽",
    @SerialName("preparation") val preparation: String,
    @SerialName("categorie_repas") val mealCategory: String,
    @SerialName("objectif_adapte") val objective: String = "",
    @SerialName("recipe_ingredients") val ingredients: List<CreateRecipeIngredientRequest>,
)

@Serializable data class GenerateMealPlanRequest(
    @SerialName("date_debut") val startDate: String,
    @SerialName("date_fin") val endDate: String,
    @SerialName("replace_existing") val replaceExisting: Boolean = true,
)
@Serializable data class UpdateMealRequest(
    @SerialName("nombre_portions") val portions: String? = null,
    @SerialName("statut") val status: String? = null,
)
@Serializable data class CreateMealRequest(
    val date: String,
    @SerialName("repas") val type: String,
    @SerialName("recipe") val recipeId: Long,
    @SerialName("nombre_portions") val portions: String = "1.00",
    @SerialName("statut") val status: String = "prevu",
)

internal fun MealPlanDto.toModel() = MealPlanEntry(
    id, date, type, recipeId, recipeName, recipeIcon.orEmpty(), uploadedImageUrl ?: remoteImageUrl,
    calories.decimal(), proteins.decimal(), carbohydrates.decimal(), fats.decimal(), portions.decimal(1.0), status,
)

internal fun RecipeDto.toModel() = Recipe(
    id, name, icon.orEmpty(), uploadedImageUrl ?: remoteImageUrl, preparation, mealCategory,
    calories.decimal(), proteins.decimal(), carbohydrates.decimal(), fats.decimal(),
    ingredients.map { RecipeIngredient(it.name, it.quantity.decimal(), it.unit) }, personal,
)

internal fun IngredientOptionDto.toModel() = IngredientOption(id, name, icon, category, baseUnit)

private fun String?.decimal(default: Double = 0.0) = this?.replace(',', '.')?.toDoubleOrNull() ?: default
