package mg.hydria.bienetre.core.network

import java.io.File
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import org.junit.Test


class FitnessProductionPayloadTest {
    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }
    private val payloadDirectory = File(System.getProperty("user.dir"))
        .resolve("../../../.tmp_fitness_responses")

    @Test
    fun productionPayloadsMatchAndroidModels() {
        json.decodeFromString<WorkoutCycleDto>(payload("cycle"))
        json.decodeFromString<TodayWorkoutDto>(payload("today"))
        json.decodeFromString<WorkoutDaySessionEnvelope>(payload("today_session"))
        json.decodeFromString<List<WorkoutHistoryDto>>(payload("history"))
    }

    private fun payload(name: String) = payloadDirectory.resolve("$name.json").readText()
}
