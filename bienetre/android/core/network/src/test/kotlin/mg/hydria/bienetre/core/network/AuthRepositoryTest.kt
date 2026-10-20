package mg.hydria.bienetre.core.network

import kotlinx.coroutines.test.runTest
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AuthRepositoryTest {
    @Test
    fun loginPersistsTokensAndMapsCapabilities() = runTest {
        val store = MemoryTokenStore()
        val api = FakeAuthApi(tokenResponse = tokenResponse())
        val repository = AuthRepository(api, store)

        val session = repository.login(" marie ", "secret")

        assertEquals("marie", api.lastLogin?.username)
        assertEquals(StoredTokens("access-1", "refresh-1"), store.read())
        assertEquals("Marie Raja", session.user.displayName)
        assertEquals(setOf("user", "coach"), session.user.capabilities.roles)
        assertEquals(true, session.user.capabilities.canAccessCoachSpace)
    }

    @Test
    fun authenticatorStoresRotatedRefreshToken() {
        val store = MemoryTokenStore(StoredTokens("expired", "refresh-1"))
        val authenticator = TokenAuthenticator(
            tokenStore = store,
            refreshApi = object : RefreshApi {
                override suspend fun refresh(request: RefreshRequest) =
                    RefreshResponse(access = "access-2", refresh = "refresh-2")
            },
        )
        val response = unauthorizedResponse("expired")

        val retried = authenticator.authenticate(null, response)

        assertEquals("Bearer access-2", retried?.header("Authorization"))
        assertEquals(StoredTokens("access-2", "refresh-2"), store.read())
    }

    @Test
    fun authenticatorClearsTokensWhenRefreshFails() {
        val store = MemoryTokenStore(StoredTokens("expired", "refresh-1"))
        val authenticator = TokenAuthenticator(
            tokenStore = store,
            refreshApi = object : RefreshApi {
                override suspend fun refresh(request: RefreshRequest): RefreshResponse {
                    error("refresh rejected")
                }
            },
        )

        val retried = authenticator.authenticate(null, unauthorizedResponse("expired"))

        assertNull(retried)
        assertNull(store.read())
    }

    private fun unauthorizedResponse(token: String): Response = Response.Builder()
        .request(
            Request.Builder()
                .url("https://bienetre.hydria.mg/api/v1/dashboard/")
                .header("Authorization", "Bearer $token")
                .build(),
        )
        .protocol(Protocol.HTTP_1_1)
        .code(401)
        .message("Unauthorized")
        .build()

    private fun tokenResponse() = TokenResponse(
        access = "access-1",
        refresh = "refresh-1",
        user = UserDto(
            id = 7,
            username = "marie",
            email = "marie@example.com",
            firstName = "Marie",
            lastName = "Raja",
            capabilities = CapabilitiesDto(
                roles = listOf("user", "coach"),
                canAccessCoachSpace = true,
            ),
        ),
    )
}

private class MemoryTokenStore(initial: StoredTokens? = null) : TokenStore {
    private var tokens = initial
    override fun read(): StoredTokens? = tokens
    override fun write(tokens: StoredTokens) { this.tokens = tokens }
    override fun clear() { tokens = null }
}

private class FakeAuthApi(
    private val tokenResponse: TokenResponse,
) : AuthApi {
    var lastLogin: LoginRequest? = null

    override suspend fun login(request: LoginRequest): TokenResponse {
        lastLogin = request
        return tokenResponse
    }

    override suspend fun register(request: RegisterRequest): TokenResponse = tokenResponse
    override suspend fun session(): SessionResponse = SessionResponse(tokenResponse.user)
    override suspend fun revoke(request: RevokeRequest) = Unit
}

