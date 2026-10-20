package mg.hydria.bienetre.core.network

import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import mg.hydria.bienetre.core.model.*
import retrofit2.HttpException
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import java.io.IOException
import java.time.LocalDate
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

interface FitnessApi {
    @GET("api/v1/fitness/workout-plans/cycle/") suspend fun cycle(): WorkoutCycleDto
    @GET("api/v1/fitness/workout-plans/today/") suspend fun today(): TodayWorkoutDto
    @GET("api/v1/fitness/workout-plans/today-session/") suspend fun todaySession(): WorkoutDaySessionEnvelope
    @GET("api/v1/fitness/workout-sessions/") suspend fun history(): List<WorkoutHistoryDto>
    @POST("api/v1/fitness/workout-plans/generate/") suspend fun generate(@Body request: WorkoutGenerateRequest): WorkoutPlanDto
    @POST("api/v1/fitness/workout-plans/start-session/") suspend fun start(): WorkoutDaySessionEnvelope
    @POST("api/v1/fitness/workout-plans/end-session/") suspend fun end(): WorkoutDaySessionEnvelope
    @POST("api/v1/fitness/workout-plans/complete-item/") suspend fun complete(@Body request: WorkoutCompleteRequest): WorkoutHistoryDto
    @POST("api/v1/fitness/workout-plans/postpone-item/") suspend fun postpone(@Body request: WorkoutPostponeRequest): WorkoutPlanItemDto
}

data class WorkoutCompletion(
    val itemId: Long, val date: String, val daySessionId: Long?, val sets: Int, val repetitions: Int,
    val weightKg: Double?, val restSeconds: Int, val durationSeconds: Int, val comment: String,
)

@Singleton
class FitnessRepository @Inject constructor(private val api: FitnessApi) {
    suspend fun load(): FitnessOverview = safe { coroutineScope {
        val cycle = async { optional<WorkoutCycleDto?>(null) { api.cycle() } }
        val today = async { optional<TodayWorkoutDto?>(null) { api.today() } }
        val session = async { optional(WorkoutDaySessionEnvelope()) { api.todaySession() } }
        val history = async { optional(emptyList<WorkoutHistoryDto>()) { api.history() } }
        val cycleDto = cycle.await()
        val todayDto = today.await()
        check(cycleDto != null || todayDto != null) { "Les réponses principales Sport sont illisibles." }
        val cycleModel = cycleDto?.toModel()
            ?: WorkoutCycle(todayDto?.plan?.toModel(), emptyList())
        val todayModel = todayDto?.toModel()
            ?: TodayWorkout(
                date = LocalDate.now().toString(),
                weekIndex = null,
                plan = cycleDto?.plan?.toModel(),
                items = emptyList(),
            )
        FitnessOverview(
            cycleModel,
            todayModel,
            session.await().session?.toModel(),
            history.await().take(20).map { it.toModel() },
        )
    } }
    suspend fun generate(date: String, frequency: Int, weeks: Int) = safe { api.generate(WorkoutGenerateRequest(date, frequency, weeks)) }
    suspend fun start() = safe { api.start().session?.toModel() ?: error("Réponse de séance invalide") }
    suspend fun end() = safe { api.end().session?.toModel() ?: error("Réponse de séance invalide") }
    suspend fun complete(value: WorkoutCompletion) = safe { api.complete(WorkoutCompleteRequest(value.itemId, value.date, value.daySessionId, value.sets, value.repetitions, value.weightKg?.let { "%.2f".format(Locale.US, it) }, value.restSeconds, value.durationSeconds, value.comment)).toModel() }
    suspend fun postpone(itemId: Long, newDate: String) = safe { api.postpone(WorkoutPostponeRequest(itemId, newDate)).toModel() }
    private suspend fun <T> safe(action: suspend () -> T): T = try { action() }
    catch (error: IOException) { throw ApiException(ApiErrorKind.Network, error) }
    catch (error: HttpException) { throw ApiException(when (error.code()) { 401 -> ApiErrorKind.Unauthorized; 403 -> ApiErrorKind.Forbidden; else -> ApiErrorKind.Server }, error) }

    private suspend fun <T> optional(fallback: T, action: suspend () -> T): T = try {
        action()
    } catch (error: IOException) {
        throw error
    } catch (error: HttpException) {
        if (error.code() == 401 || error.code() == 403) throw error else fallback
    } catch (_: Exception) {
        fallback
    }
}
