package mg.hydria.bienetre.feature.profile

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import mg.hydria.bienetre.core.network.ProfileApi
import mg.hydria.bienetre.core.network.ProfileDto
import mg.hydria.bienetre.core.network.ProfileMetricsDto
import mg.hydria.bienetre.core.network.ProfileRepository
import mg.hydria.bienetre.core.network.ProfileUpdateDto
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ProfileViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setUp() = Dispatchers.setMain(dispatcher)

    @After
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun validatesAndSavesEditedProfile() = runTest(dispatcher) {
        val api = FakeProfileApi()
        val viewModel = ProfileViewModel(ProfileRepository(api))
        advanceUntilIdle()
        viewModel.edit {
            it.copy(
                birthDate = "1994-06-12",
                heightCm = "168,5",
                weightKg = "62.4",
                activitiesPerWeek = "4",
                averageDurationMinutes = "50",
                objective = "alimentation_saine",
            )
        }

        viewModel.save()
        advanceUntilIdle()

        assertEquals(168.5, api.lastUpdate?.heightCm ?: 0.0, 0.0)
        assertEquals("alimentation_saine", api.lastUpdate?.objectif)
        val state = viewModel.state.value as ProfileUiState.Content
        assertEquals("Profil mis à jour.", state.message)
    }

    @Test
    fun rejectsOutOfRangeHeightBeforeNetworkCall() = runTest(dispatcher) {
        val api = FakeProfileApi()
        val viewModel = ProfileViewModel(ProfileRepository(api))
        advanceUntilIdle()
        viewModel.edit { it.copy(heightCm = "80") }

        viewModel.save()
        advanceUntilIdle()

        assertNull(api.lastUpdate)
        val state = viewModel.state.value as ProfileUiState.Content
        assertNotNull(state.validationError)
        assertTrue(state.validationError!!.contains("100 et 250"))
    }
}

private class FakeProfileApi : ProfileApi {
    private var profile = ProfileDto(
        id = 9,
        username = "aina",
        birthDate = "1994-06-12",
        sexe = "femme",
        heightCm = "165.00",
        weightKg = "62.00",
        activitiesPerWeek = 3,
        averageDurationMinutes = 45,
        objectif = "perte_poids",
        fastingMode = "aucun",
    )
    var lastUpdate: ProfileUpdateDto? = null

    override suspend fun getProfile(): ProfileDto = profile

    override suspend fun updateProfile(update: ProfileUpdateDto): ProfileDto {
        lastUpdate = update
        profile = profile.copy(
            birthDate = update.birthDate,
            sexe = update.sexe,
            heightCm = update.heightCm?.toString(),
            weightKg = update.weightKg?.toString(),
            activitiesPerWeek = update.activitiesPerWeek,
            averageDurationMinutes = update.averageDurationMinutes,
            objectif = update.objectif,
            fastingMode = update.fastingMode,
            listedAsCoach = update.listedAsCoach,
        )
        return profile
    }

    override suspend fun getMetrics() = ProfileMetricsDto(
        complet = true,
        bmr = 1420.0,
        tdee = 2050.0,
        targetCalories = 1750.0,
    )
}

