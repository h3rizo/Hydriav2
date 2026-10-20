package mg.hydria.bienetre.feature.meals

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import mg.hydria.bienetre.core.model.MealPlanEntry
import mg.hydria.bienetre.core.model.MealPlanOverview
import mg.hydria.bienetre.core.model.Recipe
import mg.hydria.bienetre.core.model.IngredientOption
import mg.hydria.bienetre.core.network.ApiErrorKind
import mg.hydria.bienetre.core.network.ApiException
import mg.hydria.bienetre.core.network.MealRepository
import mg.hydria.bienetre.core.network.NewPersonalRecipe
import mg.hydria.bienetre.core.network.NewRecipeIngredient
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters
import javax.inject.Inject

data class MealsContent(
    val weekStart: LocalDate,
    val meals: List<MealPlanEntry>,
    val recipes: List<Recipe>,
    val ingredients: List<IngredientOption>,
    val busyMealIds: Set<Long> = emptySet(),
    val generating: Boolean = false,
    val creatingRecipe: Boolean = false,
    val message: String? = null,
)

data class RecipeIngredientDraft(val ingredientId: Long, val quantity: Double, val unit: String)

sealed interface MealsUiState {
    data object Loading : MealsUiState
    data class Content(val data: MealsContent) : MealsUiState
    data class Error(val message: String) : MealsUiState
    data object SessionExpired : MealsUiState
}

@HiltViewModel
class MealsViewModel @Inject constructor(private val repository: MealRepository) : ViewModel() {
    private val initialWeek = LocalDate.now().with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
    private val _state = MutableStateFlow<MealsUiState>(MealsUiState.Loading)
    val state: StateFlow<MealsUiState> = _state.asStateFlow()
    private var weekStart = initialWeek

    init { load() }

    fun previousWeek() { weekStart = weekStart.minusWeeks(1); load() }
    fun nextWeek() { weekStart = weekStart.plusWeeks(1); load() }
    fun currentWeek() { weekStart = initialWeek; load() }

    fun load() {
        _state.value = MealsUiState.Loading
        viewModelScope.launch {
            runCatching { repository.load(weekStart.toString(), weekStart.plusDays(6).toString()) }
                .onSuccess { overview -> _state.value = MealsUiState.Content(overview.toContent(weekStart)) }
                .onFailure(::fail)
        }
    }

    fun generate() = mutate(generating = true) {
        repository.generate(weekStart.toString(), weekStart.plusDays(6).toString())
        reload("Plan de repas généré pour la semaine.")
    }

    fun setStatus(meal: MealPlanEntry, status: String) = mutate(meal.id) {
        replace(repository.update(meal.id, status = status), "Statut mis à jour.")
    }

    fun setPortions(meal: MealPlanEntry, portions: Double) = mutate(meal.id) {
        replace(repository.update(meal.id, portions = portions.coerceIn(0.25, 10.0)), "Portions mises à jour.")
    }

    fun delete(meal: MealPlanEntry) = mutate(meal.id) {
        repository.delete(meal.id)
        val content = content() ?: return@mutate
        _state.value = MealsUiState.Content(content.copy(meals = content.meals.filterNot { it.id == meal.id }, message = "Repas supprimé."))
    }

    fun add(date: LocalDate, type: String, recipeId: Long) = mutate {
        val created = repository.create(date.toString(), type, recipeId)
        val content = content() ?: return@mutate
        _state.value = MealsUiState.Content(content.copy(meals = (content.meals + created).sortedWith(compareBy({ it.date }, { it.type })), message = "Repas ajouté."))
    }

    fun createPersonalRecipe(name: String, category: String, preparation: String, ingredients: List<RecipeIngredientDraft>) {
        val allowedCategories = setOf("petit_dejeuner", "dejeuner", "diner", "collation")
        val valid = name.trim().length in 3..255 && category in allowedCategories && preparation.length <= 10_000 &&
            ingredients.isNotEmpty() && ingredients.map { it.ingredientId }.distinct().size == ingredients.size &&
            ingredients.all { it.quantity > 0 && it.quantity <= 100_000 && it.unit.isNotBlank() && it.unit.length <= 50 }
        if (!valid) {
            val content = content() ?: return
            _state.value = MealsUiState.Content(content.copy(message = "Vérifiez le nom, la catégorie et les quantités des ingrédients."))
            return
        }
        mutate(creatingRecipe = true) {
            repository.createRecipe(NewPersonalRecipe(name, preparation, category, ingredients.map { NewRecipeIngredient(it.ingredientId, it.quantity, it.unit) }))
            reload("Recette personnelle créée et calculée par le serveur.")
        }
    }

    private fun mutate(mealId: Long? = null, generating: Boolean = false, creatingRecipe: Boolean = false, action: suspend () -> Unit) {
        val current = content() ?: return
        _state.value = MealsUiState.Content(current.copy(
            busyMealIds = mealId?.let { current.busyMealIds + it } ?: current.busyMealIds,
            generating = generating || current.generating,
            creatingRecipe = creatingRecipe || current.creatingRecipe,
            message = null,
        ))
        viewModelScope.launch { runCatching { action() }.onFailure(::failMutation) }
    }

    private suspend fun reload(message: String) {
        val overview = repository.load(weekStart.toString(), weekStart.plusDays(6).toString())
        _state.value = MealsUiState.Content(overview.toContent(weekStart).copy(message = message))
    }

    private fun replace(updated: MealPlanEntry, message: String) {
        val content = content() ?: return
        _state.value = MealsUiState.Content(content.copy(
            meals = content.meals.map { if (it.id == updated.id) updated else it },
            busyMealIds = content.busyMealIds - updated.id,
            message = message,
        ))
    }

    private fun content() = (_state.value as? MealsUiState.Content)?.data
    private fun fail(error: Throwable) { _state.value = error.toState() }
    private fun failMutation(error: Throwable) {
        if ((error as? ApiException)?.kind == ApiErrorKind.Unauthorized) _state.value = MealsUiState.SessionExpired
        else {
            val content = content()
            _state.value = content?.let { MealsUiState.Content(it.copy(busyMealIds = emptySet(), generating = false, creatingRecipe = false, message = error.userMessage())) }
                ?: error.toState()
        }
    }
}

private fun MealPlanOverview.toContent(weekStart: LocalDate) = MealsContent(weekStart, meals, recipes, ingredients)
private fun Throwable.userMessage() = when ((this as? ApiException)?.kind) {
    ApiErrorKind.Network -> "Connexion indisponible. Vos changements n’ont pas été envoyés."
    ApiErrorKind.Forbidden -> "Cette action n’est pas autorisée."
    else -> "L’action n’a pas pu être terminée. Vérifiez les données du profil."
}
private fun Throwable.toState() = when ((this as? ApiException)?.kind) {
    ApiErrorKind.Unauthorized -> MealsUiState.SessionExpired
    else -> MealsUiState.Error(userMessage())
}
