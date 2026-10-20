package mg.hydria.bienetre.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import mg.hydria.bienetre.core.model.ProfileMetrics
import mg.hydria.bienetre.core.model.ProfileUpdate
import mg.hydria.bienetre.core.model.WellbeingProfile

@Serializable
data class ProfileDto(
    val id: Long,
    val username: String,
    @SerialName("date_naissance") val birthDate: String? = null,
    val sexe: String = "",
    @SerialName("taille_cm") val heightCm: String? = null,
    @SerialName("poids_kg") val weightKg: String? = null,
    @SerialName("activites_par_semaine") val activitiesPerWeek: Int = 0,
    @SerialName("duree_moyenne_minutes") val averageDurationMinutes: Int = 0,
    @SerialName("niveau_activite") val activityLevel: String = "",
    val objectif: String = "",
    @SerialName("fasting_mode") val fastingMode: String = "aucun",
    @SerialName("residence_city") val residenceCityId: Long? = null,
    @SerialName("residence_city_nom") val residenceCityName: String? = null,
    @SerialName("is_listed_as_coach") val listedAsCoach: Boolean = false,
    @SerialName("coach_bio") val coachBio: String = "",
    @SerialName("coach_specialites") val coachSpecialties: String = "",
    @SerialName("coach_availability") val coachAvailability: String = "",
)

@Serializable
data class ProfileUpdateDto(
    @SerialName("date_naissance") val birthDate: String? = null,
    val sexe: String,
    @SerialName("taille_cm") val heightCm: Double? = null,
    @SerialName("poids_kg") val weightKg: Double? = null,
    @SerialName("activites_par_semaine") val activitiesPerWeek: Int,
    @SerialName("duree_moyenne_minutes") val averageDurationMinutes: Int,
    val objectif: String,
    @SerialName("fasting_mode") val fastingMode: String,
    @SerialName("is_listed_as_coach") val listedAsCoach: Boolean,
    @SerialName("coach_bio") val coachBio: String,
    @SerialName("coach_specialites") val coachSpecialties: String,
    @SerialName("coach_availability") val coachAvailability: String,
)

@Serializable
data class ProfileMetricsDto(
    val complet: Boolean = false,
    val bmr: Double? = null,
    val tdee: Double? = null,
    @SerialName("objectif_calories") val targetCalories: Double? = null,
    @SerialName("objectif_proteines_g") val targetProteins: Double? = null,
    @SerialName("objectif_glucides_g") val targetCarbohydrates: Double? = null,
    @SerialName("objectif_lipides_g") val targetFats: Double? = null,
    @SerialName("niveau_activite_calcule") val calculatedActivityLevel: String = "sedentaire",
    val message: String = "",
    @SerialName("missing_fields") val missingFields: List<String> = emptyList(),
)

fun ProfileDto.toModel() = WellbeingProfile(
    id = id,
    username = username,
    birthDate = birthDate,
    gender = sexe,
    heightCm = heightCm?.toDoubleOrNull(),
    referenceWeightKg = weightKg?.toDoubleOrNull(),
    activitiesPerWeek = activitiesPerWeek,
    averageDurationMinutes = averageDurationMinutes,
    activityLevel = activityLevel,
    objective = objectif,
    fastingMode = fastingMode,
    residenceCityId = residenceCityId,
    residenceCityName = residenceCityName,
    listedAsCoach = listedAsCoach,
    coachBio = coachBio,
    coachSpecialties = coachSpecialties,
    coachAvailability = coachAvailability,
)

fun ProfileMetricsDto.toModel() = ProfileMetrics(
    complete = complet,
    basalMetabolism = bmr,
    dailyEnergyExpenditure = tdee,
    calorieTarget = targetCalories,
    proteinTarget = targetProteins,
    carbohydrateTarget = targetCarbohydrates,
    fatTarget = targetFats,
    calculatedActivityLevel = calculatedActivityLevel,
    message = message,
    missingFields = missingFields,
)

fun ProfileUpdate.toDto() = ProfileUpdateDto(
    birthDate = birthDate,
    sexe = gender,
    heightCm = heightCm,
    weightKg = referenceWeightKg,
    activitiesPerWeek = activitiesPerWeek,
    averageDurationMinutes = averageDurationMinutes,
    objectif = objective,
    fastingMode = fastingMode,
    listedAsCoach = listedAsCoach,
    coachBio = if (listedAsCoach) coachBio else "",
    coachSpecialties = if (listedAsCoach) coachSpecialties else "",
    coachAvailability = if (listedAsCoach) coachAvailability else "",
)
