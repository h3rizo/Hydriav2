package mg.hydria.bienetre.core.model

data class BodyMeasurement(
    val id: Long,
    val date: String,
    val weightKg: Double?,
    val muscleMassKg: Double?,
    val fatMassKg: Double?,
)

data class ProgressOverview(
    val measurements: List<BodyMeasurement>,
) {
    val latest: BodyMeasurement? get() = measurements.firstOrNull()
    val previous: BodyMeasurement? get() = measurements.getOrNull(1)
    val weightDelta: Double? get() {
        val current = latest?.weightKg ?: return null
        val prior = previous?.weightKg ?: return null
        return current - prior
    }
}

data class ProgressPhoto(
    val id: Long,
    val date: String,
    val note: String,
    val imageUrl: String?,
    val createdAt: String,
)
