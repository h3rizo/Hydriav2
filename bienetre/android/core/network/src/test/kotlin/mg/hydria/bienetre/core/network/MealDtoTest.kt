package mg.hydria.bienetre.core.network

import org.junit.Assert.assertEquals
import org.junit.Test

class MealDtoTest {
    @Test
    fun mapsDecimalStringsAndPrefersUploadedImage() {
        val meal = MealPlanDto(
            id = 4,
            date = "2026-08-31",
            type = "midi",
            recipeId = 9,
            recipeName = "Bol vitalité",
            remoteImageUrl = "https://remote/image.jpg",
            uploadedImageUrl = "https://hydria/media/image.jpg",
            calories = "420.50",
            proteins = "27.25",
            portions = "1.50",
            status = "prevu",
        ).toModel()

        assertEquals("https://hydria/media/image.jpg", meal.imageUrl)
        assertEquals(420.5, meal.calories, 0.0)
        assertEquals(1.5, meal.portions, 0.0)
    }

    @Test
    fun mapsRecipeIngredientsWithoutRecalculatingNutrition() {
        val recipe = RecipeDto(
            id = 9,
            name = "Bol vitalité",
            calories = "420.00",
            ingredients = listOf(RecipeIngredientDto(name = "Riz", quantity = "120.00", unit = "g")),
        ).toModel()

        assertEquals(420.0, recipe.calories, 0.0)
        assertEquals("Riz", recipe.ingredients.single().name)
        assertEquals(120.0, recipe.ingredients.single().quantity, 0.0)
    }

    @Test
    fun mapsPersonalRecipeFlagFromServer() {
        val recipe = RecipeDto(id = 9, name = "Bol maison", personal = true).toModel()

        assertEquals(true, recipe.personal)
    }
}
