package mg.hydria.bienetre.feature.dashboard

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import mg.hydria.bienetre.core.network.DashboardApi
import mg.hydria.bienetre.core.network.DashboardDto
import mg.hydria.bienetre.core.network.DashboardProfileDto
import mg.hydria.bienetre.core.network.DashboardRepository
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.IOException

@OptIn(ExperimentalCoroutinesApi::class)
class DashboardViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun exposesContentReturnedByRepository() = runTest(dispatcher) {
        val api = object : DashboardApi {
            override suspend fun getDashboard() = DashboardDto(
                date = "2026-08-31",
                profile = DashboardProfileDto(objectif = "maintien"),
            )
        }

        val viewModel = DashboardViewModel(DashboardRepository(api))
        advanceUntilIdle()

        val state = viewModel.state.value
        assertTrue(state is DashboardUiState.Content)
        assertEquals("maintien", (state as DashboardUiState.Content).dashboard.objective)
    }

    @Test
    fun exposesUsefulOfflineError() = runTest(dispatcher) {
        val api = object : DashboardApi {
            override suspend fun getDashboard(): DashboardDto = throw IOException("offline")
        }

        val viewModel = DashboardViewModel(DashboardRepository(api))
        advanceUntilIdle()

        val state = viewModel.state.value
        assertTrue(state is DashboardUiState.Error)
        assertTrue((state as DashboardUiState.Error).message.contains("Internet"))
    }
}

