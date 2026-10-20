package mg.hydria.bienetre.feature.progress

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import mg.hydria.bienetre.core.model.ProgressOverview
import mg.hydria.bienetre.core.model.ProgressPhoto
import mg.hydria.bienetre.core.network.ApiErrorKind
import mg.hydria.bienetre.core.network.ApiException
import mg.hydria.bienetre.core.network.NewBodyMeasurement
import mg.hydria.bienetre.core.network.ProgressRepository
import java.time.LocalDate
import javax.inject.Inject

data class PrivateProgressPhoto(val metadata: ProgressPhoto, val bytes: ByteArray)
data class PendingProgressPhoto(val bytes: ByteArray, val mimeType: String, val filename: String)

sealed interface ProgressUiState {
    data object Loading : ProgressUiState
    data class Content(
        val data: ProgressOverview,
        val photos: List<PrivateProgressPhoto> = emptyList(),
        val saving: Boolean = false,
        val uploadingPhoto: Boolean = false,
        val pendingPhoto: PendingProgressPhoto? = null,
        val message: String? = null,
    ) : ProgressUiState
    data class Error(val message: String) : ProgressUiState
    data object SessionExpired : ProgressUiState
}

@HiltViewModel
class ProgressViewModel @Inject constructor(private val repository: ProgressRepository) : ViewModel() {
    private val _state = MutableStateFlow<ProgressUiState>(ProgressUiState.Loading)
    val state: StateFlow<ProgressUiState> = _state.asStateFlow()

    init { load() }

    fun load() {
        _state.value = ProgressUiState.Loading
        viewModelScope.launch {
            runCatching { loadContent() }
                .onSuccess { _state.value = it }
                .onFailure(::fail)
        }
    }

    fun add(date: String, weight: String, muscle: String, fat: String) {
        val parsedDate = runCatching { LocalDate.parse(date) }.getOrNull()
        val weightValue = weight.decimalOrNull()
        val muscleValue = muscle.decimalOrNull()
        val fatValue = fat.decimalOrNull()
        val invalidNumber = listOf(weight to weightValue, muscle to muscleValue, fat to fatValue).any { (raw, value) -> raw.isNotBlank() && value == null }
        if (parsedDate == null || parsedDate > LocalDate.now() || invalidNumber || listOfNotNull(weightValue, muscleValue, fatValue).isEmpty() || listOfNotNull(weightValue, muscleValue, fatValue).any { it <= 0 || it > 500 }) {
            message("Saisissez une date valide et au moins une mesure positive.")
            return
        }
        val content = _state.value as? ProgressUiState.Content ?: return
        _state.value = content.copy(saving = true, message = null)
        viewModelScope.launch {
            runCatching { repository.create(NewBodyMeasurement(date, weightValue, muscleValue, fatValue)); loadContent("Mesure enregistrée.") }
                .onSuccess { _state.value = it }
                .onFailure(::mutationFailed)
        }
    }

    fun selectPhoto(bytes: ByteArray, mimeType: String, filename: String) {
        val content = _state.value as? ProgressUiState.Content ?: return
        val allowed = mimeType in setOf("image/jpeg", "image/png", "image/webp")
        _state.value = when {
            !allowed -> content.copy(message = "Formats autorisés : JPEG, PNG ou WebP.")
            bytes.isEmpty() || bytes.size > MAX_PHOTO_BYTES -> content.copy(message = "La photo doit faire moins de 10 Mo.")
            else -> content.copy(pendingPhoto = PendingProgressPhoto(bytes, mimeType, filename), message = null)
        }
    }

    fun clearSelectedPhoto() {
        val content = _state.value as? ProgressUiState.Content ?: return
        _state.value = content.copy(pendingPhoto = null)
    }

    fun uploadPhoto(date: String, note: String) {
        val content = _state.value as? ProgressUiState.Content ?: return
        val pending = content.pendingPhoto ?: return message("Sélectionnez ou prenez une photo.")
        if (runCatching { LocalDate.parse(date) }.getOrNull()?.let { it <= LocalDate.now() } != true || note.length > 255) {
            message("Vérifiez la date et limitez la note à 255 caractères.")
            return
        }
        _state.value = content.copy(uploadingPhoto = true, message = null)
        viewModelScope.launch {
            runCatching {
                repository.uploadPhoto(date, note.trim(), pending.bytes, pending.mimeType, pending.filename)
                loadContent("Photo privée enregistrée.")
            }.onSuccess { _state.value = it }.onFailure(::mutationFailed)
        }
    }

    private suspend fun loadContent(message: String? = null): ProgressUiState.Content = coroutineScope {
        val measurements = async { repository.load() }
        val photoMetadata = async { repository.loadPhotos() }
        val metadata = photoMetadata.await()
        val selected = if (metadata.size <= MAX_LOADED_PHOTOS) metadata else listOf(metadata.first()) + metadata.takeLast(MAX_LOADED_PHOTOS - 1)
        val photos = selected.mapNotNull { photo ->
            runCatching { PrivateProgressPhoto(photo, repository.loadPhotoContent(photo.id)) }.getOrNull()
        }
        ProgressUiState.Content(ProgressOverview(measurements.await()), photos = photos, message = message)
    }

    private fun message(value: String) {
        val content = _state.value as? ProgressUiState.Content ?: return
        _state.value = content.copy(message = value)
    }

    private fun fail(error: Throwable) {
        _state.value = if ((error as? ApiException)?.kind == ApiErrorKind.Unauthorized) ProgressUiState.SessionExpired
        else ProgressUiState.Error(error.userMessage())
    }

    private fun mutationFailed(error: Throwable) {
        if ((error as? ApiException)?.kind == ApiErrorKind.Unauthorized) _state.value = ProgressUiState.SessionExpired
        else (_state.value as? ProgressUiState.Content)?.let { _state.value = it.copy(saving = false, uploadingPhoto = false, message = error.userMessage()) }
    }

    private companion object {
        const val MAX_PHOTO_BYTES = 10 * 1024 * 1024
        const val MAX_LOADED_PHOTOS = 8
    }
}

private fun String.decimalOrNull(): Double? = trim().replace(',', '.').takeIf { it.isNotEmpty() }?.toDoubleOrNull()
private fun Throwable.userMessage() = when ((this as? ApiException)?.kind) {
    ApiErrorKind.Network -> "Connexion indisponible. La mesure n’a pas été enregistrée."
    ApiErrorKind.Forbidden -> "Vous n’êtes pas autorisé à modifier ces mesures."
    else -> "Impossible de charger ou d’enregistrer vos mesures."
}
