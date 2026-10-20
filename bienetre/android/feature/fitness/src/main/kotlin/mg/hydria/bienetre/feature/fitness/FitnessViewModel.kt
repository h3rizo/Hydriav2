package mg.hydria.bienetre.feature.fitness

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import mg.hydria.bienetre.core.model.FitnessOverview
import mg.hydria.bienetre.core.model.WorkoutPlanItem
import mg.hydria.bienetre.core.network.ApiErrorKind
import mg.hydria.bienetre.core.network.ApiException
import mg.hydria.bienetre.core.network.FitnessRepository
import mg.hydria.bienetre.core.network.WorkoutCompletion
import java.time.LocalDate
import javax.inject.Inject

data class FitnessContent(val overview: FitnessOverview, val busy: Boolean = false, val busyItemIds: Set<Long> = emptySet(), val message: String? = null)
sealed interface FitnessUiState {
    data object Loading : FitnessUiState
    data class Content(val data: FitnessContent) : FitnessUiState
    data class Error(val message: String) : FitnessUiState
    data object SessionExpired : FitnessUiState
}

@HiltViewModel
class FitnessViewModel @Inject constructor(private val repository: FitnessRepository) : ViewModel() {
    private val _state = MutableStateFlow<FitnessUiState>(FitnessUiState.Loading)
    val state: StateFlow<FitnessUiState> = _state.asStateFlow()
    init { load() }

    fun load() {
        _state.value = FitnessUiState.Loading
        viewModelScope.launch { runCatching { repository.load() }
            .onSuccess { _state.value = FitnessUiState.Content(FitnessContent(it)) }
            .onFailure(::fail) }
    }

    fun generate(date: String, frequency: Int, weeks: Int) {
        if (runCatching { LocalDate.parse(date) }.isFailure || frequency !in 2..5 || weeks !in 1..12) {
            message("Vérifiez la date, la fréquence et la durée du programme."); return
        }
        mutate { repository.generate(date, frequency, weeks); reload("Programme généré.") }
    }

    fun start() = mutate { repository.start(); reload("Séance démarrée.") }
    fun end() = mutate { repository.end(); reload("Séance terminée.") }

    fun complete(item: WorkoutPlanItem, sets: String, repetitions: String, weight: String, rest: Int, duration: String, comment: String) {
        val setCount = sets.toIntOrNull(); val repetitionCount = repetitions.toIntOrNull(); val durationSeconds = duration.toIntOrNull()
        val weightKg = weight.replace(',', '.').toDoubleOrNull()
        if (setCount == null || setCount < 0 || repetitionCount == null || repetitionCount < 0 || durationSeconds == null || durationSeconds < 0 || (weight.isNotBlank() && weightKg == null)) {
            message("Les séries, répétitions, poids et durée doivent être valides."); return
        }
        val content = content() ?: return
        val session = content.overview.daySession
        mutate(item.id) {
            repository.complete(WorkoutCompletion(item.id, content.overview.today.date, session?.id, setCount, repetitionCount, weightKg, rest, durationSeconds, comment))
            reload("Exercice validé.")
        }
    }

    fun postpone(item: WorkoutPlanItem, date: String) {
        if (runCatching { LocalDate.parse(date) }.isFailure) { message("La date de report doit utiliser AAAA-MM-JJ."); return }
        mutate(item.id) { repository.postpone(item.id, date); reload("Exercice reporté au $date.") }
    }

    private fun mutate(itemId: Long? = null, action: suspend () -> Unit) {
        val current = content() ?: return
        _state.value = FitnessUiState.Content(current.copy(busy = itemId == null, busyItemIds = itemId?.let { current.busyItemIds + it } ?: current.busyItemIds, message = null))
        viewModelScope.launch { runCatching { action() }.onFailure(::mutationFailed) }
    }
    private suspend fun reload(message: String) { _state.value = FitnessUiState.Content(FitnessContent(repository.load(), message = message)) }
    private fun content() = (_state.value as? FitnessUiState.Content)?.data
    private fun message(value: String) { content()?.let { _state.value = FitnessUiState.Content(it.copy(message = value)) } }
    private fun fail(error: Throwable) {
        Log.e(TAG, "Echec du chargement du programme sportif (load)", error)
        _state.value = error.toState()
    }
    private fun mutationFailed(error: Throwable) {
        Log.e(TAG, "Echec d'une action sportive (mutate)", error)
        if ((error as? ApiException)?.kind == ApiErrorKind.Unauthorized) _state.value = FitnessUiState.SessionExpired
        else content()?.let { _state.value = FitnessUiState.Content(it.copy(busy = false, busyItemIds = emptySet(), message = error.userMessage())) }
    }
}
private const val TAG = "FitnessViewModel"
private fun Throwable.userMessage() = when ((this as? ApiException)?.kind) {
    ApiErrorKind.Network -> "Connexion indisponible. L’action n’a pas été enregistrée."
    ApiErrorKind.Forbidden -> "Cette action sportive n’est pas autorisée."
    else -> "L’action sportive a échoué. Vérifiez votre profil et le programme actif."
}
private fun Throwable.toState() = when ((this as? ApiException)?.kind) { ApiErrorKind.Unauthorized -> FitnessUiState.SessionExpired; else -> FitnessUiState.Error(userMessage()) }
