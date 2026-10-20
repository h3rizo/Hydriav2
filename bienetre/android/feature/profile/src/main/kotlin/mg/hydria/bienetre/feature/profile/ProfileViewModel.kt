package mg.hydria.bienetre.feature.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import mg.hydria.bienetre.core.model.ProfileOverview
import mg.hydria.bienetre.core.model.ProfileUpdate
import mg.hydria.bienetre.core.network.ApiErrorKind
import mg.hydria.bienetre.core.network.ApiException
import mg.hydria.bienetre.core.network.ProfileRepository
import java.time.LocalDate
import javax.inject.Inject

data class ProfileForm(
    val birthDate: String = "",
    val gender: String = "",
    val heightCm: String = "",
    val weightKg: String = "",
    val activitiesPerWeek: String = "0",
    val averageDurationMinutes: String = "0",
    val objective: String = "",
    val fastingMode: String = "aucun",
    val listedAsCoach: Boolean = false,
    val coachBio: String = "",
    val coachSpecialties: String = "",
    val coachAvailability: String = "",
)

sealed interface ProfileUiState {
    data object Loading : ProfileUiState
    data class Content(
        val overview: ProfileOverview,
        val form: ProfileForm,
        val saving: Boolean = false,
        val message: String? = null,
        val validationError: String? = null,
    ) : ProfileUiState
    data class Error(val message: String) : ProfileUiState
    data object SessionExpired : ProfileUiState
}

@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val repository: ProfileRepository,
) : ViewModel() {
    private val _state = MutableStateFlow<ProfileUiState>(ProfileUiState.Loading)
    val state: StateFlow<ProfileUiState> = _state.asStateFlow()

    init { load() }

    fun load() {
        _state.value = ProfileUiState.Loading
        viewModelScope.launch {
            runCatching { repository.load() }
                .onSuccess { _state.value = it.toContent() }
                .onFailure(::handleFailure)
        }
    }

    fun edit(transform: (ProfileForm) -> ProfileForm) {
        val current = _state.value as? ProfileUiState.Content ?: return
        _state.value = current.copy(
            form = transform(current.form),
            message = null,
            validationError = null,
        )
    }

    fun save() {
        val current = _state.value as? ProfileUiState.Content ?: return
        val update = current.form.validatedUpdate().getOrElse { error ->
            _state.value = current.copy(validationError = error.message)
            return
        }
        if (current.saving) return
        _state.value = current.copy(saving = true, message = null, validationError = null)
        viewModelScope.launch {
            runCatching { repository.update(update) }
                .onSuccess {
                    _state.value = it.toContent(message = "Profil mis à jour.")
                }
                .onFailure(::handleFailure)
        }
    }

    private fun handleFailure(error: Throwable) {
        _state.value = when ((error as? ApiException)?.kind) {
            ApiErrorKind.Unauthorized -> ProfileUiState.SessionExpired
            ApiErrorKind.Network -> ProfileUiState.Error("Connexion impossible. Vérifiez votre accès à Internet.")
            ApiErrorKind.Forbidden -> ProfileUiState.Error("Ce compte ne peut pas modifier ce profil.")
            else -> ProfileUiState.Error("Le profil est momentanément indisponible.")
        }
    }
}

private fun ProfileOverview.toContent(message: String? = null) = ProfileUiState.Content(
    overview = this,
    form = ProfileForm(
        birthDate = profile.birthDate.orEmpty(),
        gender = profile.gender,
        heightCm = profile.heightCm?.plain().orEmpty(),
        weightKg = profile.referenceWeightKg?.plain().orEmpty(),
        activitiesPerWeek = profile.activitiesPerWeek.toString(),
        averageDurationMinutes = profile.averageDurationMinutes.toString(),
        objective = profile.objective,
        fastingMode = profile.fastingMode,
        listedAsCoach = profile.listedAsCoach,
        coachBio = profile.coachBio,
        coachSpecialties = profile.coachSpecialties,
        coachAvailability = profile.coachAvailability,
    ),
    message = message,
)

private fun ProfileForm.validatedUpdate(): Result<ProfileUpdate> = runCatching {
    val parsedBirthDate = birthDate.trim().takeIf(String::isNotEmpty)?.also { value ->
        runCatching { LocalDate.parse(value) }
            .getOrElse { error("La date de naissance doit utiliser le format AAAA-MM-JJ.") }
    }
    val height = heightCm.replace(',', '.').toDoubleOrNull()
    val weight = weightKg.replace(',', '.').toDoubleOrNull()
    val activities = activitiesPerWeek.toIntOrNull() ?: error("La fréquence d’activité doit être un nombre.")
    val duration = averageDurationMinutes.toIntOrNull() ?: error("La durée moyenne doit être un nombre.")
    require(height == null || height in 100.0..250.0) { "La taille doit être comprise entre 100 et 250 cm." }
    require(weight == null || weight in 25.0..300.0) { "Le poids doit être compris entre 25 et 300 kg." }
    require(activities in 0..14) { "La fréquence doit être comprise entre 0 et 14 séances." }
    require(duration in 0..300) { "La durée doit être comprise entre 0 et 300 minutes." }
    ProfileUpdate(
        birthDate = parsedBirthDate,
        gender = gender,
        heightCm = height,
        referenceWeightKg = weight,
        activitiesPerWeek = activities,
        averageDurationMinutes = duration,
        objective = objective,
        fastingMode = fastingMode,
        listedAsCoach = listedAsCoach,
        coachBio = coachBio.trim(),
        coachSpecialties = coachSpecialties.trim(),
        coachAvailability = coachAvailability.trim(),
    )
}

private fun Double.plain(): String = if (this % 1.0 == 0.0) toInt().toString() else toString()
