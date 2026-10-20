package mg.hydria.bienetre.core.network

import mg.hydria.bienetre.core.model.AuthenticatedUser
import mg.hydria.bienetre.core.model.UserSession
import retrofit2.HttpException
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

enum class AuthErrorKind { InvalidInput, Unauthorized, RateLimited, Network, Service }

class AuthServiceException(val kind: AuthErrorKind, cause: Throwable) : Exception(cause)

@Singleton
class AuthRepository @Inject constructor(
    private val api: AuthApi,
    private val tokenStore: TokenStore,
) {
    fun hasStoredSession(): Boolean = tokenStore.read() != null

    suspend fun login(username: String, password: String): UserSession =
        authCall { persist(api.login(LoginRequest(username.trim(), password))) }

    suspend fun register(
        username: String,
        email: String,
        password: String,
        passwordConfirm: String,
    ): UserSession = authCall {
        persist(api.register(RegisterRequest(username.trim(), email.trim(), password, passwordConfirm)))
    }

    suspend fun restoreSession(): AuthenticatedUser = authCall { api.session().user.toModel() }

    suspend fun logout() {
        val refresh = tokenStore.read()?.refresh
        try {
            if (refresh != null) api.revoke(RevokeRequest(refresh))
        } finally {
            tokenStore.clear()
        }
    }

    private fun persist(response: TokenResponse): UserSession {
        val tokens = StoredTokens(response.access, response.refresh)
        tokenStore.write(tokens)
        return UserSession(response.user.toModel(), tokens.access, tokens.refresh)
    }

    private suspend fun <T> authCall(action: suspend () -> T): T = try {
        action()
    } catch (error: IOException) {
        throw AuthServiceException(AuthErrorKind.Network, error)
    } catch (error: HttpException) {
        val kind = when (error.code()) {
            400 -> AuthErrorKind.InvalidInput
            401 -> AuthErrorKind.Unauthorized
            429 -> AuthErrorKind.RateLimited
            else -> AuthErrorKind.Service
        }
        throw AuthServiceException(kind, error)
    }
}
