package mg.hydria.desktop.auth

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mg.hydria.desktop.storage.DesktopPrefs
import mg.hydria.shared.auth.HydriaAuthGateway

/**
 * Session Hydria cote Desktop. Meme contrat que la partie login d'OfflineStore
 * (Android) : jeton "Token ..." + nom d'employe + cle de compte, persistes
 * localement. Reutilise [HydriaAuthGateway.loginBlocking] de :shared (deja la
 * source de verite du login, avec repli HydriaApi cote Android).
 *
 * Pas de gate de login global pour l'instant : seul l'ecran Recherche exige la
 * session (la Calculatrice fonctionne sans reseau).
 */
class DesktopSession(private val prefs: DesktopPrefs) {
    var token: String? by mutableStateOf(prefs.getString(KEY_TOKEN))
        private set
    var employeeName: String by mutableStateOf(prefs.getString(KEY_NAME) ?: "")
        private set
    var accountKey: String by mutableStateOf(prefs.getString(KEY_ACCOUNT) ?: "")
        private set

    val isAuthenticated: Boolean get() = !token.isNullOrBlank()

    /** @return null si la connexion a reussi, sinon un message d'erreur. */
    suspend fun login(username: String, password: String): String? {
        val result = withContext(Dispatchers.IO) {
            runCatching {
                HydriaAuthGateway.loginBlocking(username, password, deviceLabel())
            }
        }
        val response = result.getOrElse { return "Connexion impossible : ${it.message ?: "reseau indisponible"}" }
        if (!response.successful) return response.error

        token = response.body.getString("token")
        accountKey = response.body.optString("user", username).ifBlank { username }.trim().lowercase()
        employeeName = response.body.optString("employe_nom", username).ifBlank { username }
        prefs.putString(KEY_TOKEN, token)
        prefs.putString(KEY_ACCOUNT, accountKey)
        prefs.putString(KEY_NAME, employeeName)
        return null
    }

    fun logout() {
        token = null
        employeeName = ""
        accountKey = ""
        prefs.clear(KEY_TOKEN, KEY_ACCOUNT, KEY_NAME)
    }

    private fun deviceLabel(): String = "Desktop - " + (System.getProperty("os.name") ?: "inconnu")

    private companion object {
        const val KEY_TOKEN = "token"
        const val KEY_ACCOUNT = "account_key"
        const val KEY_NAME = "employee_name"
    }
}
