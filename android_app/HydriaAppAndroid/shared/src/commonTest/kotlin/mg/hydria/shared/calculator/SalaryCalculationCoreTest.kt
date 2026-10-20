package mg.hydria.shared.calculator

import kotlin.test.*

/** Synthetic rates for algorithm tests; JVM regression tests verify exact production arithmetic. */
class SalaryCalculationCoreTest {
    private val parameters = SalaryCalculationParameters(100.0, 2.0, 0.01, true, 2.0, 3.0,
        30.0, 240.0, 173.33, 56.0, 0.3, 0.4, 0.5, 0.3, 1.0, 1.0, 0.3, 1.0, 1.0)
    private val arithmetic = object : SalaryCalculationArithmetic<Double> {
        override val zero = 0.0
        override val hundred = 100.0
        override fun integer(value: Int) = value.toDouble()
        override fun add(left: Double, right: Double) = left + right
        override fun subtract(left: Double, right: Double) = left - right
        override fun multiply(left: Double, right: Double) = left * right
        override fun divide(left: Double, right: Double) = left / right
        override fun floorToIncrement(value: Double, increment: Double) = kotlin.math.floor(value / increment) * increment
        override fun roundToIncrement(value: Double, increment: Double) = kotlin.math.floor(value / increment + 0.5) * increment
    }
    private val core = SalaryCalculationCore(parameters,
        listOf(SalaryCalculationBracket(1, 100.0, 0.0), SalaryCalculationBracket(2, 10000.0, 10.0)), arithmetic)
    private fun input(mode: SalaryMode = SalaryMode.STANDARD, days: Int = 0) =
        SalaryCalculationInput(SalaryBasis.GROSS, 200.0, 0, mode, days, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    @Test fun bracketsCeilingAndRoundingAreAppliedInOrder() {
        val result = core.calculate(300.0, input())
        assertEquals(200.0, result.cnapsBase)
        assertEquals(2.0, result.employeeCnaps)
        assertEquals(296.0, result.taxableBase)
        assertEquals(19.6, result.irsa, 0.000001)
        assertEquals(276.4, result.netExact, 0.000001)
        assertEquals(276.0, result.netRounded)
        assertEquals(2, result.brackets.size)
    }
    @Test fun prorataAndDailyUseConfiguredReference() {
        assertEquals(100.0, core.calculate(200.0, input(SalaryMode.PRORATA, 15)).totalGross)
        assertEquals(600.0, core.calculate(20.0, input(SalaryMode.DAILY, 30)).totalGross)
        val small = core.calculate(10.0, input())
        assertTrue(small.minimumIrsaApplied)
        assertEquals(3.0, small.irsa)
    }
    @Test fun guardianAddsEachMajorationAndReplacementExtra() {
        val result = core.calculate(2400.0, input(SalaryMode.GUARDIAN).copy(nightHours = 10.0, sundayHours = 5.0,
            officialHolidayHours = 2.0, decreePaidHolidayHours = 3.0, mayFirstHours = 1.0,
            replacementHours = 4.0, ordinaryReplacementHours = 2.0))
        assertEquals(30.0, result.majorations.night, 0.000001)
        assertEquals(46.0, result.majorations.replacement, 0.000001)
        assertEquals(125.0, result.majorations.total, 0.000001)
        assertEquals(2525.0, result.totalGross, 0.000001)
    }
}
