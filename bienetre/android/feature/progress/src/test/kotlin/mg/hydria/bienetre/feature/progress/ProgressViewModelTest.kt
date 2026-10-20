package mg.hydria.bienetre.feature.progress

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import mg.hydria.bienetre.core.network.BodyMeasurementDto
import mg.hydria.bienetre.core.network.BodyMeasurementRequest
import mg.hydria.bienetre.core.network.ProgressApi
import mg.hydria.bienetre.core.network.ProgressRepository
import mg.hydria.bienetre.core.network.ProgressPhotoDto
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.time.LocalDate

@OptIn(ExperimentalCoroutinesApi::class)
class ProgressViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setUp() { Dispatchers.setMain(dispatcher) }
    @After fun tearDown() { Dispatchers.resetMain() }

    @Test
    fun validMeasurementIsReloadedFromServer() = runTest(dispatcher) {
        val api = FakeProgressApi()
        val viewModel = ProgressViewModel(ProgressRepository(api))
        advanceUntilIdle()

        viewModel.add(LocalDate.now().toString(), "68,5", "31", "14.2")
        advanceUntilIdle()

        val content = viewModel.state.value as ProgressUiState.Content
        assertEquals(1, api.createCalls)
        assertEquals(68.5, content.data.latest?.weightKg ?: 0.0, 0.0)
        assertEquals("Mesure enregistrée.", content.message)
    }

    @Test
    fun emptyMeasurementNeverCallsBackend() = runTest(dispatcher) {
        val api = FakeProgressApi()
        val viewModel = ProgressViewModel(ProgressRepository(api))
        advanceUntilIdle()

        viewModel.add(LocalDate.now().toString(), "", "", "")
        advanceUntilIdle()

        assertEquals(0, api.createCalls)
        assertTrue((viewModel.state.value as ProgressUiState.Content).message?.contains("au moins une") == true)
    }

    @Test
    fun selectedPrivatePhotoIsUploadedThenReloaded() = runTest(dispatcher) {
        val api = FakeProgressApi()
        val viewModel = ProgressViewModel(ProgressRepository(api))
        advanceUntilIdle()

        viewModel.selectPhoto(byteArrayOf(1, 2, 3), "image/jpeg", "progress.jpg")
        viewModel.uploadPhoto(LocalDate.now().toString(), "Départ")
        advanceUntilIdle()

        val content = viewModel.state.value as ProgressUiState.Content
        assertEquals(1, api.uploadCalls)
        assertEquals(1, content.photos.size)
        assertEquals("Départ", content.photos.single().metadata.note)
        assertTrue(content.pendingPhoto == null)
    }
}

private class FakeProgressApi : ProgressApi {
    private val values = mutableListOf<BodyMeasurementDto>()
    var createCalls = 0
    var uploadCalls = 0
    private val photos = mutableListOf<ProgressPhotoDto>()
    override suspend fun measurements() = values.toList()
    override suspend fun create(request: BodyMeasurementRequest): BodyMeasurementDto {
        createCalls++
        return BodyMeasurementDto(
            id = createCalls.toLong(),
            date = request.date,
            weightKg = request.weightKg,
            muscleMassKg = request.muscleMassKg,
            fatMassKg = request.fatMassKg,
        ).also { values.add(0, it) }
    }
    override suspend fun photos() = photos.toList()
    override suspend fun photoContent(id: Long) = byteArrayOf(1, 2, 3).toResponseBody("image/jpeg".toMediaType())
    override suspend fun uploadPhoto(date: RequestBody, note: RequestBody, image: MultipartBody.Part): ProgressPhotoDto {
        uploadCalls++
        return ProgressPhotoDto(uploadCalls.toLong(), bodyText(date), bodyText(note), "/private", "2026-08-31T10:00:00Z").also { photos.add(it) }
    }
    private fun bodyText(body: RequestBody): String {
        val buffer = okio.Buffer()
        body.writeTo(buffer)
        return buffer.readUtf8()
    }
}
