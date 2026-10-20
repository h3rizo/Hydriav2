package mg.hydria.bienetre.core.model

data class UserCapabilities(
    val roles: Set<String>,
    val isAdmin: Boolean,
    val isListedAsCoach: Boolean,
    val canAccessCoachSpace: Boolean,
    val hasActiveCoach: Boolean,
)

data class AuthenticatedUser(
    val id: Long,
    val username: String,
    val email: String,
    val firstName: String,
    val lastName: String,
    val capabilities: UserCapabilities,
) {
    val displayName: String
        get() = listOf(firstName, lastName).filter(String::isNotBlank).joinToString(" ")
            .ifBlank { username }
}

data class UserSession(
    val user: AuthenticatedUser,
    val accessToken: String,
    val refreshToken: String,
)

