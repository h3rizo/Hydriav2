package mg.hydria.bienetre.core.network

import mg.hydria.bienetre.core.model.BodyMeasurement
import mg.hydria.bienetre.core.model.ProgressPhoto
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.ResponseBody
import retrofit2.HttpException
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.POST
import java.io.IOException
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

interface ProgressApi {
    @GET("api/v1/progress/body-measurements/")
    suspend fun measurements(): List<BodyMeasurementDto>

    @POST("api/v1/progress/body-measurements/")
    suspend fun create(@Body request: BodyMeasurementRequest): BodyMeasurementDto

    @GET("api/v1/progress/photos/")
    suspend fun photos(): List<ProgressPhotoDto>

    @GET("api/v1/progress/photos/{id}/content/")
    suspend fun photoContent(@Path("id") id: Long): ResponseBody

    @Multipart
    @POST("api/v1/progress/photos/")
    suspend fun uploadPhoto(
        @Part("date") date: okhttp3.RequestBody,
        @Part("note") note: okhttp3.RequestBody,
        @Part image: MultipartBody.Part,
    ): ProgressPhotoDto
}

data class NewBodyMeasurement(
    val date: String,
    val weightKg: Double?,
    val muscleMassKg: Double?,
    val fatMassKg: Double?,
)

@Singleton
class ProgressRepository @Inject constructor(private val api: ProgressApi) {
    suspend fun load(): List<BodyMeasurement> = safe { api.measurements().map { it.toModel() } }

    suspend fun create(value: NewBodyMeasurement): BodyMeasurement = safe {
        api.create(
            BodyMeasurementRequest(
                date = value.date,
                weightKg = value.weightKg.asPayload(),
                muscleMassKg = value.muscleMassKg.asPayload(),
                fatMassKg = value.fatMassKg.asPayload(),
            ),
        ).toModel()
    }

    suspend fun loadPhotos(): List<ProgressPhoto> = safe { api.photos().map { it.toModel() } }

    suspend fun loadPhotoContent(id: Long): ByteArray = safe {
        api.photoContent(id).use { response ->
            val bytes = response.byteStream().use { it.readNBytes(MAX_PHOTO_BYTES + 1) }
            if (bytes.size > MAX_PHOTO_BYTES) throw IOException("Private photo exceeds the accepted size")
            bytes
        }
    }

    suspend fun uploadPhoto(date: String, note: String, bytes: ByteArray, mimeType: String, filename: String): ProgressPhoto = safe {
        val text = "text/plain".toMediaType()
        val body = bytes.toRequestBody(mimeType.toMediaType())
        api.uploadPhoto(
            date.toRequestBody(text),
            note.toRequestBody(text),
            MultipartBody.Part.createFormData("image", filename, body),
        ).toModel()
    }

    private suspend fun <T> safe(action: suspend () -> T): T = try {
        action()
    } catch (error: IOException) {
        throw ApiException(ApiErrorKind.Network, error)
    } catch (error: HttpException) {
        throw ApiException(
            when (error.code()) {
                401 -> ApiErrorKind.Unauthorized
                403 -> ApiErrorKind.Forbidden
                else -> ApiErrorKind.Server
            },
            error,
        )
    }

    private companion object { const val MAX_PHOTO_BYTES = 10 * 1024 * 1024 }
}

private fun Double?.asPayload(): String? = this?.let { "%.2f".format(Locale.US, it) }
