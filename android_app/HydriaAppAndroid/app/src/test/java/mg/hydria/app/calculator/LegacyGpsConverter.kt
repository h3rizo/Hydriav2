package mg.hydria.app.calculator

import mg.hydria.shared.calculator.*
import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode

internal object LegacyGpsConverter {
    private val dmsPattern = Regex(
        "([NSEOW])\\s*(\\d{1,3})\\s*[°º]\\s*(\\d{1,2})\\s*['’′]\\s*(\\d{1,2}(?:[.,]\\d+)?)\\s*[\"”″]?",
        RegexOption.IGNORE_CASE,
    )

    fun fromDms(input: String): GpsConversion {
        val matches = dmsPattern.findAll(input.trim()).toList()
        if (matches.size < 2) return mg.hydria.shared.calculator.GpsConversion.Invalid(
            if (!Regex("[NSEOW]", RegexOption.IGNORE_CASE).containsMatchIn(input)) GpsError.ORIENTATION_MISSING else GpsError.INVALID_FORMAT
        )
        val remainder = dmsPattern.replace(input.trim(), "")
        if (remainder.any { !it.isWhitespace() && it !in charArrayOf(',', ';', '/', '-') }) return mg.hydria.shared.calculator.GpsConversion.Invalid(GpsError.INVALID_FORMAT)
        val latitudeMatches = matches.filter { it.groupValues[1].uppercase() in setOf("N", "S") }
        val longitudeMatches = matches.filter { it.groupValues[1].uppercase() in setOf("E", "O", "W") }
        if (latitudeMatches.size > 1 || longitudeMatches.size > 1) return mg.hydria.shared.calculator.GpsConversion.Invalid(GpsError.DUPLICATE_COORDINATE)
        if (latitudeMatches.size != 1 || longitudeMatches.size != 1) return mg.hydria.shared.calculator.GpsConversion.Invalid(GpsError.ORIENTATION_MISSING)
        val latitude = component(latitudeMatches.single(), true)
        if (latitude is Component.Invalid) return mg.hydria.shared.calculator.GpsConversion.Invalid(latitude.error)
        val longitude = component(longitudeMatches.single(), false)
        if (longitude is Component.Invalid) return mg.hydria.shared.calculator.GpsConversion.Invalid(longitude.error)
        return mg.hydria.shared.calculator.GpsConversion.Success(GpsCoordinate((latitude as Component.Value).value, (longitude as Component.Value).value))
    }

    fun fromDecimal(latitude: String, longitude: String): GpsConversion {
        val lat = DecimalInput.parse(latitude) ?: return mg.hydria.shared.calculator.GpsConversion.Invalid(GpsError.INVALID_FORMAT)
        val lon = DecimalInput.parse(longitude) ?: return mg.hydria.shared.calculator.GpsConversion.Invalid(GpsError.INVALID_FORMAT)
        if (lat < MIN_LATITUDE || lat > MAX_LATITUDE) return mg.hydria.shared.calculator.GpsConversion.Invalid(GpsError.LATITUDE_RANGE)
        if (lon < MIN_LONGITUDE || lon > MAX_LONGITUDE) return mg.hydria.shared.calculator.GpsConversion.Invalid(GpsError.LONGITUDE_RANGE)
        return mg.hydria.shared.calculator.GpsConversion.Success(GpsCoordinate(lat.setScale(8, RoundingMode.HALF_UP), lon.setScale(8, RoundingMode.HALF_UP)))
    }

    private fun component(match: MatchResult, latitude: Boolean): Component {
        val direction = match.groupValues[1].uppercase()
        val degrees = BigDecimal(match.groupValues[2])
        val minutes = BigDecimal(match.groupValues[3])
        val seconds = BigDecimal(match.groupValues[4].replace(',', '.'))
        if (minutes < BigDecimal.ZERO || minutes >= SIXTY) return Component.Invalid(GpsError.INVALID_MINUTES)
        if (seconds < BigDecimal.ZERO || seconds >= SIXTY) return Component.Invalid(GpsError.INVALID_SECONDS)
        val maximum = if (latitude) MAX_LATITUDE else MAX_LONGITUDE
        val rangeError = if (latitude) GpsError.LATITUDE_RANGE else GpsError.LONGITUDE_RANGE
        if (degrees > maximum || degrees == maximum && (minutes.signum() != 0 || seconds.signum() != 0)) return Component.Invalid(rangeError)
        var decimal = degrees.add(minutes.divide(SIXTY, CONTEXT)).add(seconds.divide(THREE_THOUSAND_SIX_HUNDRED, CONTEXT))
        if (direction == "S" || direction == "O" || direction == "W") decimal = decimal.negate()
        return Component.Value(decimal.setScale(8, RoundingMode.HALF_UP))
    }

    private sealed class Component {
        data class Value(val value: BigDecimal) : Component()
        data class Invalid(val error: GpsError) : Component()
    }

    private val CONTEXT = MathContext(24, RoundingMode.HALF_UP)
    private val SIXTY = BigDecimal("60")
    private val THREE_THOUSAND_SIX_HUNDRED = BigDecimal("3600")
    private val MIN_LATITUDE = BigDecimal("-90")
    private val MAX_LATITUDE = BigDecimal("90")
    private val MIN_LONGITUDE = BigDecimal("-180")
    private val MAX_LONGITUDE = BigDecimal("180")
}
