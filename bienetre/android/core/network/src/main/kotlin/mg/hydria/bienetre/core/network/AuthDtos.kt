package mg.hydria.bienetre.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import mg.hydria.bienetre.core.model.AuthenticatedUser
import mg.hydria.bienetre.core.model.UserCapabilities

@Serializable
data class LoginRequest(val username: String, val password: String)

@Serializable
data class RegisterRequest(
    val username: String,
    val email: String,
    val password: String,
    @SerialName("password_confirm") val passwordConfirm: String,
)

@Serializable
data class RefreshRequest(val refresh: String)

@Serializable
data class RevokeRequest(val refresh: String)

@Serializable
data class TokenResponse(
    val access: String,
    val refresh: String,
    val user: UserDto,
)

@Serializable
data class RefreshResponse(val access: String, val refresh: String? = null)

@Serializable
data class SessionResponse(val user: UserDto)

@Serializable
data class UserDto(
    val id: Long,
    val username: String,
    val email: String = "",
    @SerialName("first_name") val firstName: String = "",
    @SerialName("last_name") val lastName: String = "",
    val capabilities: CapabilitiesDto,
)

@Serializable
data class CapabilitiesDto(
    val roles: List<String> = emptyList(),
    @SerialName("is_admin") val isAdmin: Boolean = false,
    @SerialName("is_listed_as_coach") val isListedAsCoach: Boolean = false,
    @SerialName("can_access_coach_space") val canAccessCoachSpace: Boolean = false,
    @SerialName("has_active_coach") val hasActiveCoach: Boolean = false,
)

internal fun UserDto.toModel() = AuthenticatedUser(
    id = id,
    username = username,
    email = email,
    firstName = firstName,
    lastName = lastName,
    capabilities = UserCapabilities(
        roles = capabilities.roles.toSet(),
        isAdmin = capabilities.isAdmin,
        isListedAsCoach = capabilities.isListedAsCoach,
        canAccessCoachSpace = capabilities.canAccessCoachSpace,
        hasActiveCoach = capabilities.hasActiveCoach,
    ),
)

