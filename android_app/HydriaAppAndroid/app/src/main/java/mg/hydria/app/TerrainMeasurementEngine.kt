package mg.hydria.app

/** Les calculs sont communs ; ce relais conserve les appels Android existants. */
object TerrainMeasurementEngine {
    fun flowFromVolume(volumeLiters: Double, durationSeconds: Double): Double =
        mg.hydria.shared.terrain.TerrainMeasurementEngine.flowFromVolume(volumeLiters, durationSeconds)
    fun trend(current: Double, recentNewestFirst: List<Double>) =
        mg.hydria.shared.terrain.TerrainMeasurementEngine.trend(current, recentNewestFirst)
    fun headMeter(previousIndex: Double, newIndex: Double, downstream: Double, days: Long) =
        mg.hydria.shared.terrain.TerrainMeasurementEngine.headMeter(previousIndex, newIndex, downstream, days)
}
