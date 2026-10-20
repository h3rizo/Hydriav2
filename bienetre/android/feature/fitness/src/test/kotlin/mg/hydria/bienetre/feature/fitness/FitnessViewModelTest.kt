package mg.hydria.bienetre.feature.fitness

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import mg.hydria.bienetre.core.network.*
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class FitnessViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setUp() { Dispatchers.setMain(dispatcher) }
    @After fun tearDown() { Dispatchers.resetMain() }

    @Test
    fun startSessionReloadsPersistedServerSession() = runTest(dispatcher) {
        val api = FakeFitnessApi()
        val viewModel = FitnessViewModel(FitnessRepository(api))
        advanceUntilIdle()

        viewModel.start()
        advanceUntilIdle()

        val session = (viewModel.state.value as FitnessUiState.Content).data.overview.daySession
        assertTrue(session?.active == true)
        assertEquals("2026-08-31T08:00:00Z", session?.startedAt)
    }

    @Test
    fun invalidCompletionNeverCallsBackend() = runTest(dispatcher) {
        val api = FakeFitnessApi()
        val viewModel = FitnessViewModel(FitnessRepository(api))
        advanceUntilIdle()
        val item = (viewModel.state.value as FitnessUiState.Content).data.overview.today.items.single()

        viewModel.complete(item, "x", "10", "", 90, "60", "")
        advanceUntilIdle()

        assertEquals(0, api.completeCalls)
        assertTrue((viewModel.state.value as FitnessUiState.Content).data.message?.contains("valides") == true)
    }
}

private class FakeFitnessApi : FitnessApi {
    var active = false
    var completeCalls = 0
    private val item = WorkoutPlanItemDto(id = 3, exerciseId = 2, exerciseName = "Squat", sets = 4, repetitions = 10)
    private val plan = WorkoutPlanDto(1, "prise_masse", "2026-08-31", 3, 4, true)
    override suspend fun cycle() = WorkoutCycleDto(plan, listOf(WorkoutWeekDto(1, "2026-08-31", "2026-09-06", listOf(item))))
    override suspend fun today() = TodayWorkoutDto("2026-08-31", 1, plan, listOf(item))
    override suspend fun todaySession() = WorkoutDaySessionEnvelope(if (active) session() else null)
    override suspend fun history() = emptyList<WorkoutHistoryDto>()
    override suspend fun generate(request: WorkoutGenerateRequest) = plan
    override suspend fun start(): WorkoutDaySessionEnvelope { active = true; return WorkoutDaySessionEnvelope(session()) }
    override suspend fun end(): WorkoutDaySessionEnvelope { active = false; return WorkoutDaySessionEnvelope(session().copy(active = false)) }
    override suspend fun complete(request: WorkoutCompleteRequest): WorkoutHistoryDto { completeCalls++; return WorkoutHistoryDto(1, request.date, "Squat") }
    override suspend fun postpone(request: WorkoutPostponeRequest) = item.copy(plannedDate = request.newDate, status = "reporte")
    private fun session() = WorkoutDaySessionDto(8, "2026-08-31", "2026-08-31T08:00:00Z", active = active)
}
