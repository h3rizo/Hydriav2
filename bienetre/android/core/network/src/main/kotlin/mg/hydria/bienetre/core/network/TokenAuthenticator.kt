package mg.hydria.bienetre.core.network

import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.Authenticator
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route
import javax.inject.Inject

class TokenAuthenticator @Inject constructor(
    private val tokenStore: TokenStore,
    private val refreshApi: RefreshApi,
) : Authenticator {
    private val refreshMutex = Mutex()

    override fun authenticate(route: Route?, response: Response): Request? {
        if (responseCount(response) >= 2) return null
        return runBlocking {
            refreshMutex.withLock {
                val stored = tokenStore.read() ?: return@withLock null
                val requestToken = response.request.header("Authorization")?.removePrefix("Bearer ")
                if (requestToken != null && requestToken != stored.access) {
                    return@withLock response.request.withBearer(stored.access)
                }
                runCatching { refreshApi.refresh(RefreshRequest(stored.refresh)) }
                    .fold(
                        onSuccess = { refreshed ->
                            val tokens = StoredTokens(
                                access = refreshed.access,
                                refresh = refreshed.refresh ?: stored.refresh,
                            )
                            tokenStore.write(tokens)
                            response.request.withBearer(tokens.access)
                        },
                        onFailure = {
                            tokenStore.clear()
                            null
                        },
                    )
            }
        }
    }

    private fun Request.withBearer(token: String) = newBuilder()
        .header("Authorization", "Bearer $token")
        .build()

    private fun responseCount(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        return count
    }
}
