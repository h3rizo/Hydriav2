package mg.hydria.shared.navigation

data class LandmarkTypeImport(
    val serverId: String,
    val name: String,
    val description: String,
    val iconKey: String,
    val colorHex: String,
    val displayOrder: Long,
    val isActive: Boolean,
    val serverUpdatedAt: String,
)
