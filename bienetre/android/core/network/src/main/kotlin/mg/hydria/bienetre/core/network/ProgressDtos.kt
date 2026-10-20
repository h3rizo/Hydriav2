package mg.hydria.bienetre.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import mg.hydria.bienetre.core.model.BodyMeasurement
import mg.hydria.bienetre.core.model.ProgressPhoto

@Serializable
data class BodyMeasurementDto(
    val id: Long,
    val date: String,
    @SerialName("poids") val weightKg: String? = null,
    @SerialName("masse_musculaire_kg") val muscleMassKg: String? = null,
    @SerialName("masse_graisseuse_kg") val fatMassKg: String? = null,
)

@Serializable
data class BodyMeasurementRequest(
    val date: String,
    @SerialName("poids") val weightKg: String? = null,
    @SerialName("masse_musculaire_kg") val muscleMassKg: String? = null,
    @SerialName("masse_graisseuse_kg") val fatMassKg: String? = null,
)

fun BodyMeasurementDto.toModel() = BodyMeasurement(
    id = id,
    date = date,
    weightKg = weightKg?.toDoubleOrNull(),
    muscleMassKg = muscleMassKg?.toDoubleOrNull(),
    fatMassKg = fatMassKg?.toDoubleOrNull(),
)

@Serializable
data class ProgressPhotoDto(
    val id: Long,
    val date: String,
    val note: String = "",
    @SerialName("image_url") val imageUrl: String? = null,
    @SerialName("created_at") val createdAt: String = "",
)

fun ProgressPhotoDto.toModel() = ProgressPhoto(id, date, note, imageUrl, createdAt)
