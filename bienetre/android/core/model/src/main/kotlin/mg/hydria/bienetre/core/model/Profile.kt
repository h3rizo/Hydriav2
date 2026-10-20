package mg.hydria.bienetre.core.model

data class WellbeingProfile(
    val id: Long,
    val username: String,
    val birthDate: String?,
    val gender: String,
    val heightCm: Double?,
    val referenceWeightKg: Double?,
    val activitiesPerWeek: Int,
    val averageDurationMinutes: Int,
    val activityLevel: String,
    val objective: String,
    val fastingMode: String,
    val residenceCityId: Long?,
    val residenceCityName: String?,
    val listedAsCoach: Boolean,
    val coachBio: String,
    val coachSpecialties: String,
    val coachAvailability: String,
)

data class ProfileMetrics(
    val complete: Boolean,
    val basalMetabolism: Double?,
    val dailyEnergyExpenditure: Double?,
    val calorieTarget: Double?,
    val proteinTarget: Double?,
    val carbohydrateTarget: Double?,
    val fatTarget: Double?,
    val calculatedActivityLevel: String,
    val message: String,
    val missingFields: List<String>,
)

data class ProfileOverview(
    val profile: WellbeingProfile,
    val metrics: ProfileMetrics,
)

data class ProfileUpdate(
    val birthDate: String?,
    val gender: String,
    val heightCm: Double?,
    val referenceWeightKg: Double?,
    val activitiesPerWeek: Int,
    val averageDurationMinutes: Int,
    val objective: String,
    val fastingMode: String,
    val listedAsCoach: Boolean,
    val coachBio: String,
    val coachSpecialties: String,
    val coachAvailability: String,
)
