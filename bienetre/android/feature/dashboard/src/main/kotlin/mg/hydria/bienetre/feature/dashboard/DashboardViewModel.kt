package mg.hydria.bienetre.feature.dashboard

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import mg.hydria.bienetre.core.model.Dashboard
import mg.hydria.bienetre.core.network.ApiErrorKind
import mg.hydria.bienetre.core.network.ApiException
import mg.hydria.bienetre.core.network.DashboardRepository
import javax.inject.Inject

sealed interface DashboardUiState {
    data object Loading : DashboardUiState
    data class Content(val dashboard: Dashboard) : DashboardUiState
    data class Error(val message: String) : DashboardUiState
    data object SessionExpired : DashboardUiState
}

@HiltViewModel
class DashboardViewModel @Inject constructor(
    private val repository: DashboardRepository,
) : ViewModel() {
    private val _state = MutableStateFlow<DashboardUiState>(DashboardUiState.Loading)
    val state: StateFlow<DashboardUiState> = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = DashboardUiState.Loading
        viewModelScope.launch {
            runCatching { repository.load() }
                .onSuccess { _state.value = DashboardUiState.Content(it) }
                .onFailure { error ->
                    _state.value = when ((error as? ApiException)?.kind) {
                        ApiErrorKind.Unauthorized -> DashboardUiState.SessionExpired
                        ApiErrorKind.Forbidden -> DashboardUiState.Error("Ce compte ne peut pas ouvrir ce tableau de bord.")
                        ApiErrorKind.Network -> DashboardUiState.Error("Connexion impossible. Vérifiez votre accès à Internet.")
                        else -> DashboardUiState.Error("Le tableau de bord est momentanément indisponible.")
                    }
                }
        }
    }
}
