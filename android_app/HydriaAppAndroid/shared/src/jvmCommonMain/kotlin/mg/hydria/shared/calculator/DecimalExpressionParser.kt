package mg.hydria.shared.calculator

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode

data class ExpressionResult(val value: BigDecimal? = null, val error: ExpressionError? = null)

/** Adaptateur décimal JVM. La grammaire et les références de lignes sont communes. */
class DecimalExpressionParser(private val mathContext: MathContext = MathContext(24, RoundingMode.HALF_UP)) {
    private val core = ExpressionCore(object : DecimalArithmetic<BigDecimal> {
        override val hundred = BigDecimal("100")
        private val maximum = BigDecimal("1E100")
        override fun parse(value: String) = value.toBigDecimalOrNull()?.round(mathContext)
        override fun add(left: BigDecimal, right: BigDecimal) = left.add(right, mathContext)
        override fun subtract(left: BigDecimal, right: BigDecimal) = left.subtract(right, mathContext)
        override fun multiply(left: BigDecimal, right: BigDecimal) = left.multiply(right, mathContext)
        override fun divide(left: BigDecimal, right: BigDecimal) = left.divide(right, mathContext)
        override fun negate(value: BigDecimal) = value.negate(mathContext)
        override fun isZero(value: BigDecimal) = value.compareTo(BigDecimal.ZERO) == 0
        override fun exceedsLimit(value: BigDecimal) = value.abs() > maximum
        override fun normalize(value: BigDecimal) = value.stripTrailingZeros()
    })
    internal fun evaluateCommon(expression: String, currentLineIndex: Int, totalLineCount: Int,
        previousResults: List<ArithmeticResult<BigDecimal>>): ArithmeticResult<BigDecimal> =
        core.evaluate(expression, currentLineIndex, totalLineCount, previousResults)
    fun evaluate(expression: String, currentLineIndex: Int, totalLineCount: Int, previousResults: List<ExpressionResult>): ExpressionResult {
        val result = core.evaluate(expression, currentLineIndex, totalLineCount,
            previousResults.map { ArithmeticResult(it.value, it.error) })
        return ExpressionResult(result.value, result.error)
    }
}
