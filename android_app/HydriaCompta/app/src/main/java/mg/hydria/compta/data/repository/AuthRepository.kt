package mg.hydria.compta.data.repository

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mg.hydria.compta.core.AppResult
import mg.hydria.compta.data.prefs.SessionStore
import mg.hydria.compta.data.remote.ComptaApi

class AuthRepository(
    private val api: ComptaApi,
    private val session: SessionStore,
) {

    suspend fun login(username: String, password: String): AppResult<Unit> = withContext(Dispatchers.IO) {
        val response = api.login(
            username = username,
            password = password,
            deviceId = session.deviceId,
            deviceLabel = android.os.Build.MODEL ?: "Android",
        )
        val body = response.body
        if (!response.successful || !body.optBoolean("success", true)) {
            val kind = if (response.isAuthError) AppResult.ErrorKind.AUTH else AppResult.ErrorKind.SERVER
            return@withContext AppResult.Err(kind, body.optString("error", response.error))
        }
        // Réponse de /mobile/api/login/ : { success, token, user, employe_id, employe_nom }
        val token = body.optString("token")
        if (token.isBlank()) {
            return@withContext AppResult.Err(AppResult.ErrorKind.SERVER, "Jeton absent de la réponse")
        }
        session.save(
            SessionStore.Session(
                accessToken = token,
                refreshToken = token, // jeton mobile longue durée, pas de rotation
                userId = body.optString("employe_id").ifBlank { body.optString("user") },
                displayName = body.optString("employe_nom").ifBlank { body.optString("user") },
                baseId = body.optString("base_id").takeIf { it.isNotBlank() },
            )
        )
        android.util.Log.d("AuthRepository", "login OK, jeton stocké (${token.length} car.)")
        AppResult.Ok(Unit)
    }

    fun logout() = session.clear()
}
