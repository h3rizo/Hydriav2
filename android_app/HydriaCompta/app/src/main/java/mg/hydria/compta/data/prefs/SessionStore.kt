package mg.hydria.compta.data.prefs

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import mg.hydria.compta.data.security.openSecurePrefs
import java.util.UUID

/** Identité de l'appareil + jetons. Stockés chiffrés (repli en clair si indisponible), jamais loggés. */
class SessionStore(context: Context) {

    private val prefs by lazy { openSecurePrefs(context, "hydria_compta_session") }

    /** Identifiant appareil stable, généré au premier lancement. */
    val deviceId: String
        get() = prefs.getString(K_DEVICE_ID, null) ?: UUID.randomUUID().toString()
            .also { prefs.edit().putString(K_DEVICE_ID, it).apply() }

    data class Session(
        val accessToken: String,
        val refreshToken: String,
        val userId: String,
        val displayName: String,
        val baseId: String?,
    )

    private val _session = MutableStateFlow(readSession())
    val session: StateFlow<Session?> = _session.asStateFlow()

    val isLoggedIn: Boolean get() = _session.value != null

    fun save(session: Session) {
        prefs.edit()
            .putString(K_ACCESS, session.accessToken)
            .putString(K_REFRESH, session.refreshToken)
            .putString(K_USER_ID, session.userId)
            .putString(K_DISPLAY, session.displayName)
            .putString(K_BASE_ID, session.baseId)
            .apply()
        _session.value = session
    }

    fun updateAccessToken(access: String, refresh: String) {
        val current = _session.value ?: return
        save(current.copy(accessToken = access, refreshToken = refresh))
    }

    fun clear() {
        prefs.edit()
            .remove(K_ACCESS).remove(K_REFRESH).remove(K_USER_ID)
            .remove(K_DISPLAY).remove(K_BASE_ID)
            .apply()
        _session.value = null
    }

    private fun readSession(): Session? {
        val access = prefs.getString(K_ACCESS, null) ?: return null
        val refresh = prefs.getString(K_REFRESH, null) ?: return null
        return Session(
            accessToken = access,
            refreshToken = refresh,
            userId = prefs.getString(K_USER_ID, "").orEmpty(),
            displayName = prefs.getString(K_DISPLAY, "").orEmpty(),
            baseId = prefs.getString(K_BASE_ID, null),
        )
    }

    private companion object {
        const val K_DEVICE_ID = "device_id"
        const val K_ACCESS = "access_token"
        const val K_REFRESH = "refresh_token"
        const val K_USER_ID = "user_id"
        const val K_DISPLAY = "display_name"
        const val K_BASE_ID = "base_id"
    }
}
