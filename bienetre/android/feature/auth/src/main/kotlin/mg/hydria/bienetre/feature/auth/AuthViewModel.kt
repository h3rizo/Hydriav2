package mg.hydria.bienetre.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import mg.hydria.bienetre.core.model.AuthenticatedUser
import mg.hydria.bienetre.core.network.AuthErrorKind
import mg.hydria.bienetre.core.network.AuthRepository
import mg.hydria.bienetre.core.network.AuthServiceException
import javax.inject.Inject

sealed interface AuthState {
    data object Checking : AuthState
    data object SignedOut : AuthState
    data class SignedIn(val user: AuthenticatedUser) : AuthState
}

data class AuthFormState(
    val isSubmitting: Boolean = false,
    val message: String? = null,
)

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val repository: AuthRepository,
) : ViewModel() {
    private val _authState = MutableStateFlow<AuthState>(AuthState.Checking)
    val authState: StateFlow<AuthState> = _authState.asStateFlow()

    private val _formState = MutableStateFlow(AuthFormState())
    val formState: StateFlow<AuthFormState> = _formState.asStateFlow()

    init {
        restoreSession()
    }

    fun login(username: String, password: String) {
        if (username.isBlank() || password.isBlank()) {
            _formState.value = AuthFormState(message = "Renseignez votre identifiant et votre mot de passe.")
            return
        }
        submit {
            repository.login(username, password).user
        }
    }

    fun register(username: String, email: String, password: String, confirmation: String) {
        if (username.isBlank() || email.isBlank() || password.isBlank()) {
            _formState.value = AuthFormState(message = "Tous les champs sont nécessaires.")
            return
        }
        if (password != confirmation) {
            _formState.value = AuthFormState(message = "Les mots de passe ne correspondent pas.")
            return
        }
        submit {
            repository.register(username, email, password, confirmation).user
        }
    }

    fun logout() {
        viewModelScope.launch {
            runCatching { repository.logout() }
            _authState.value = AuthState.SignedOut
            _formState.value = AuthFormState()
        }
    }

    fun clearMessage() {
        _formState.value = _formState.value.copy(message = null)
    }

    private fun restoreSession() {
        viewModelScope.launch {
            if (!repository.hasStoredSession()) {
                _authState.value = AuthState.SignedOut
                return@launch
            }
            _authState.value = runCatching { repository.restoreSession() }
                .fold(
                    onSuccess = { AuthState.SignedIn(it) },
                    onFailure = {
                        runCatching { repository.logout() }
                        AuthState.SignedOut
                    },
                )
        }
    }

    private fun submit(action: suspend () -> AuthenticatedUser) {
        if (_formState.value.isSubmitting) return
        viewModelScope.launch {
            _formState.value = AuthFormState(isSubmitting = true)
            runCatching { action() }
                .onSuccess {
                    _authState.value = AuthState.SignedIn(it)
                    _formState.value = AuthFormState()
                }
                .onFailure {
                    _formState.value = AuthFormState(message = it.toUserMessage())
                }
        }
    }
}

private fun Throwable.toUserMessage(): String = when (this) {
    is AuthServiceException -> when (kind) {
        AuthErrorKind.InvalidInput -> "Les informations saisies ne sont pas valides."
        AuthErrorKind.Unauthorized -> "Identifiant ou mot de passe incorrect."
        AuthErrorKind.RateLimited -> "Trop de tentatives. Réessayez dans quelques instants."
        AuthErrorKind.Network -> "Connexion impossible. Vérifiez votre accès à Internet."
        AuthErrorKind.Service -> "Le service est momentanément indisponible."
    }
    else -> "Une erreur inattendue est survenue."
}
