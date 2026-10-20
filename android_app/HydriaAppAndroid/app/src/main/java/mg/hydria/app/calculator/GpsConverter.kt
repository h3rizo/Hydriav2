package mg.hydria.app.calculator

/**
 * Relais fin vers le module partage `shared` (Phase 1 de la migration KMP).
 * Le code reel a demenage vers
 * shared/src/jvmCommonMain/kotlin/mg/hydria/shared/calculator/GpsConverter.kt.
 */
typealias GpsCoordinate = mg.hydria.shared.calculator.GpsCoordinate
typealias GpsError = mg.hydria.shared.calculator.GpsError
typealias GpsConversion = mg.hydria.shared.calculator.GpsConversion
typealias GpsDraft = mg.hydria.shared.calculator.GpsDraft

object GpsConverter {
    fun fromDms(input: String): GpsConversion = mg.hydria.shared.calculator.GpsConverter.fromDms(input)
    fun fromDecimal(latitude: String, longitude: String): GpsConversion =
        mg.hydria.shared.calculator.GpsConverter.fromDecimal(latitude, longitude)
}
