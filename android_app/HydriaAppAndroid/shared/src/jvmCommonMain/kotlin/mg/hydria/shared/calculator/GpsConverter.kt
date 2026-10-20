package mg.hydria.shared.calculator

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode

data class GpsCoordinate(val latitude: BigDecimal, val longitude: BigDecimal) {
    val combined: String get() = "${latitude.setScale(8, RoundingMode.HALF_UP).toPlainString()}, ${longitude.setScale(8, RoundingMode.HALF_UP).toPlainString()}"
}

sealed class GpsConversion {
    data class Success(val coordinate: GpsCoordinate) : GpsConversion()
    data class Invalid(val error: GpsError) : GpsConversion()
}

object GpsConverter {
    private val context = MathContext(24, RoundingMode.HALF_UP)
    private val core = GpsConversionCore(object : GpsArithmetic<BigDecimal> {
        override val zero = BigDecimal.ZERO
        override fun number(text: String) = BigDecimal(text)
        override fun input(text: String) = DecimalInput.parse(text)
        override fun add(left: BigDecimal, right: BigDecimal) = left.add(right)
        override fun divide(left: BigDecimal, right: BigDecimal) = left.divide(right, context)
        override fun negate(value: BigDecimal) = value.negate()
        override fun roundCoordinate(value: BigDecimal) = value.setScale(8, RoundingMode.HALF_UP)
        override fun isZero(value: BigDecimal) = value.signum() == 0
    })
    private fun adapt(result: GpsCoreResult<BigDecimal>): GpsConversion = result.error?.let { GpsConversion.Invalid(it) }
        ?: GpsConversion.Success(GpsCoordinate(requireNotNull(result.latitude), requireNotNull(result.longitude)))
    fun fromDms(input: String): GpsConversion = adapt(core.fromDms(input))
    fun fromDecimal(latitude: String, longitude: String): GpsConversion = adapt(core.fromDecimal(latitude, longitude))
}
