package mg.hydria.bienetre.feature.household

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import mg.hydria.bienetre.core.model.HouseholdOverview
import mg.hydria.bienetre.core.model.ProfileLookup
import mg.hydria.bienetre.core.network.ApiErrorKind
import mg.hydria.bienetre.core.network.ApiException
import mg.hydria.bienetre.core.network.NewHouseholdMember
import mg.hydria.bienetre.core.network.NewSharedIngredient
import mg.hydria.bienetre.core.network.NewSharedMeal
import mg.hydria.bienetre.core.network.NewSharedParticipant
import mg.hydria.bienetre.core.network.SharedMealRepository
import java.time.LocalDateTime
import javax.inject.Inject

data class HouseholdContent(
    val overview: HouseholdOverview,
    val profiles: List<ProfileLookup> = emptyList(),
    val busy: Boolean = false,
    val searching: Boolean = false,
    val message: String? = null,
)
data class SharedIngredientDraft(val id: Long, val quantity: Double, val unit: String)
data class SharedParticipantDraft(val profileId: Long?, val householdMemberId: Long?, val servings: Double)

sealed interface HouseholdUiState {
    data object Loading : HouseholdUiState
    data class Content(val data: HouseholdContent) : HouseholdUiState
    data class Error(val message: String) : HouseholdUiState
    data object SessionExpired : HouseholdUiState
}

@HiltViewModel
class HouseholdViewModel @Inject constructor(private val repository: SharedMealRepository) : ViewModel() {
    private val _state = MutableStateFlow<HouseholdUiState>(HouseholdUiState.Loading)
    val state: StateFlow<HouseholdUiState> = _state.asStateFlow()
    init { load() }

    fun load() {
        _state.value = HouseholdUiState.Loading
        viewModelScope.launch { runCatching { repository.load() }.onSuccess { _state.value = HouseholdUiState.Content(HouseholdContent(it)) }.onFailure(::fail) }
    }

    fun searchProfiles(query: String) {
        val current = content() ?: return
        if (query.trim().length < 2) { _state.value = HouseholdUiState.Content(current.copy(profiles = emptyList())); return }
        _state.value = HouseholdUiState.Content(current.copy(searching = true, message = null))
        viewModelScope.launch {
            runCatching { repository.searchProfiles(query) }
                .onSuccess { results -> content()?.let { _state.value = HouseholdUiState.Content(it.copy(profiles = results, searching = false)) } }
                .onFailure(::failMutation)
        }
    }

    fun createMember(name: String, relationship: String, age: Int?, sex: String, linkedProfileId: Long?) {
        if (name.trim().length !in 2..120 || relationship.length > 50 || age != null && age !in 0..130) {
            message("Vérifiez le nom et l’âge du membre."); return
        }
        mutate {
            repository.createMember(NewHouseholdMember(name, relationship, age, sex, linkedProfileId))
            reload("Membre du foyer ajouté.")
        }
    }

    fun createMeal(
        title: String, eatenAt: String, source: String, notes: String,
        shoppingDoneBy: Long?, cookedBy: Long?, ingredients: List<SharedIngredientDraft>, participants: List<SharedParticipantDraft>,
    ) {
        val dateValid = runCatching { LocalDateTime.parse(eatenAt) }.isSuccess
        val valid = title.trim().length in 2..150 && dateValid && source in setOf("home_cooked", "bought", "restaurant") &&
            ingredients.isNotEmpty() && participants.isNotEmpty() && ingredients.all { it.quantity > 0 && it.quantity <= 100_000 } &&
            participants.all { it.servings > 0 && it.servings <= 100 }
        if (!valid) { message("Vérifiez le titre, la date, les ingrédients et les participants."); return }
        mutate {
            repository.createMeal(NewSharedMeal(title, eatenAt, source, notes, shoppingDoneBy, cookedBy,
                ingredients.map { NewSharedIngredient(it.id, it.quantity, it.unit) },
                participants.map { NewSharedParticipant(it.profileId, it.householdMemberId, it.servings) }))
            reload("Repas partagé créé et nutrition recalculée.")
        }
    }

    private fun mutate(action: suspend () -> Unit) {
        val current = content() ?: return
        _state.value = HouseholdUiState.Content(current.copy(busy = true, message = null))
        viewModelScope.launch { runCatching { action() }.onFailure(::failMutation) }
    }
    private suspend fun reload(message: String) { _state.value = HouseholdUiState.Content(HouseholdContent(repository.load(), message = message)) }
    private fun message(value: String) { content()?.let { _state.value = HouseholdUiState.Content(it.copy(message = value)) } }
    private fun content() = (_state.value as? HouseholdUiState.Content)?.data
    private fun fail(error: Throwable) { _state.value = if ((error as? ApiException)?.kind == ApiErrorKind.Unauthorized) HouseholdUiState.SessionExpired else HouseholdUiState.Error(error.messageForUser()) }
    private fun failMutation(error: Throwable) {
        if ((error as? ApiException)?.kind == ApiErrorKind.Unauthorized) _state.value = HouseholdUiState.SessionExpired
        else content()?.let { _state.value = HouseholdUiState.Content(it.copy(busy = false, searching = false, message = error.messageForUser())) }
    }
}

private fun Throwable.messageForUser() = when ((this as? ApiException)?.kind) {
    ApiErrorKind.Network -> "Connexion indisponible. Réessayez lorsque le réseau revient."
    ApiErrorKind.Forbidden -> "Cette action est réservée au créateur du repas."
    else -> "L’action n’a pas pu être terminée. Vérifiez les informations saisies."
}
