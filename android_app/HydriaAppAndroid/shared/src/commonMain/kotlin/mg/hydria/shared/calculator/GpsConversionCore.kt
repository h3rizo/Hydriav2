package mg.hydria.shared.calculator

enum class GpsError { INVALID_FORMAT, ORIENTATION_MISSING, DUPLICATE_COORDINATE, INVALID_MINUTES, INVALID_SECONDS, LATITUDE_RANGE, LONGITUDE_RANGE }

data class GpsDraft(
    val dmsInput: String = "",
    val latitudeInput: String = "",
    val longitudeInput: String = "",
    val latitude: String = "",
    val longitude: String = "",
    val updatedAt: Long = 0,
)

data class GpsCoreResult<N>(val latitude: N? = null, val longitude: N? = null, val error: GpsError? = null)
interface GpsArithmetic<N> {
    val zero: N
    fun number(text: String): N
    fun input(text: String): N?
    fun add(left: N, right: N): N
    fun divide(left: N, right: N): N
    fun negate(value: N): N
    fun roundCoordinate(value: N): N
    fun isZero(value: N): Boolean
}
class GpsConversionCore<N : Comparable<N>>(private val math: GpsArithmetic<N>) {
    private val dmsPattern = Regex(
        "([NSEOW])\\s*(\\d{1,3})\\s*[°º]\\s*(\\d{1,2})\\s*['’′]\\s*(\\d{1,2}(?:[.,]\\d+)?)\\s*[\"”″]?",
        RegexOption.IGNORE_CASE,
    )


    private val sixty = math.number("60")
    private val hour = math.number("3600")
    private val maxLat = math.number("90")
    private val maxLon = math.number("180")
    fun fromDecimal(latitude: String, longitude: String): GpsCoreResult<N> {
        val lat = math.input(latitude) ?: return GpsCoreResult(error = GpsError.INVALID_FORMAT)
        val lon = math.input(longitude) ?: return GpsCoreResult(error = GpsError.INVALID_FORMAT)
        if (lat < math.negate(maxLat) || lat > maxLat) return GpsCoreResult(error = GpsError.LATITUDE_RANGE)
        if (lon < math.negate(maxLon) || lon > maxLon) return GpsCoreResult(error = GpsError.LONGITUDE_RANGE)
        return GpsCoreResult(math.roundCoordinate(lat), math.roundCoordinate(lon))
    }
    fun fromDms(input: String): GpsCoreResult<N> {
        val matches = dmsPattern.findAll(input.trim()).toList()
        if (matches.size < 2) return GpsCoreResult(error =
            if (!Regex("[NSEOW]", RegexOption.IGNORE_CASE).containsMatchIn(input)) GpsError.ORIENTATION_MISSING else GpsError.INVALID_FORMAT)
        val remainder = dmsPattern.replace(input.trim(), "")
        if (remainder.any { !it.isWhitespace() && it !in charArrayOf(',', ';', '/', '-') }) return GpsCoreResult(error = GpsError.INVALID_FORMAT)
        val lat = matches.filter { it.groupValues[1].uppercase() in setOf("N", "S") }
        val lon = matches.filter { it.groupValues[1].uppercase() in setOf("E", "O", "W") }
        if (lat.size > 1 || lon.size > 1) return GpsCoreResult(error = GpsError.DUPLICATE_COORDINATE)
        if (lat.size != 1 || lon.size != 1) return GpsCoreResult(error = GpsError.ORIENTATION_MISSING)
        val latitude = component(lat.single(), true)
        if (latitude.error != null) return GpsCoreResult(error = latitude.error)
        val longitude = component(lon.single(), false)
        if (longitude.error != null) return GpsCoreResult(error = longitude.error)
        return GpsCoreResult(latitude.value, longitude.value)
    }
    private data class Component<N>(val value: N? = null, val error: GpsError? = null)
    private fun component(match: MatchResult, latitude: Boolean): Component<N> {
        val direction = match.groupValues[1].uppercase()
        val degrees = math.number(match.groupValues[2])
        val minutes = math.number(match.groupValues[3])
        val seconds = math.number(match.groupValues[4].replace(',', '.'))
        if (minutes < math.zero || minutes >= sixty) return Component(error = GpsError.INVALID_MINUTES)
        if (seconds < math.zero || seconds >= sixty) return Component(error = GpsError.INVALID_SECONDS)
        val maximum = if (latitude) maxLat else maxLon
        val error = if (latitude) GpsError.LATITUDE_RANGE else GpsError.LONGITUDE_RANGE
        if (degrees > maximum || degrees == maximum && (!math.isZero(minutes) || !math.isZero(seconds))) return Component(error = error)
        var decimal = math.add(math.add(degrees, math.divide(minutes, sixty)), math.divide(seconds, hour))
        if (direction == "S" || direction == "O" || direction == "W") decimal = math.negate(decimal)
        return Component(math.roundCoordinate(decimal))
    }
}
