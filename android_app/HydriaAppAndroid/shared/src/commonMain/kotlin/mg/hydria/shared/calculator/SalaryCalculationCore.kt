package mg.hydria.shared.calculator

data class SalaryCalculationInput<N>(
    val basis: SalaryBasis,
    val target: N,
    val dependents: Int,
    val mode: SalaryMode,
    val days: Int,
    val nightHours: N,
    val sundayHours: N,
    val officialHolidayHours: N,
    val decreePaidHolidayHours: N,
    val mayFirstHours: N,
    val replacementHours: N,
    val ordinaryReplacementHours: N,
)

data class SalaryCalculationParameters<N>(
    val minimumSalary: N,
    val cnapsCeilingMultiplier: N,
    val cnapsEmployeeRate: N,
    val healthMutualMatchesCnaps: Boolean,
    val dependentIrsaDeduction: N,
    val minimumIrsa: N,
    val prorataReferenceDays: N,
    val guardianReferenceHours: N,
    val employeeReferenceHours: N,
    val guardianDefaultNightHours: N,
    val nightRate: N,
    val sundayRate: N,
    val officialHolidayRate: N,
    val decreePaidHolidayRate: N,
    val mayFirstRate: N,
    val guardianReplacementRate: N,
    val guardianOrdinaryReplacementExtraRate: N,
    val taxableBaseFloorIncrement: N,
    val netRoundingIncrement: N,
)

data class SalaryCalculationBracket<N>(
    val order: Int,
    val upperBound: N,
    val ratePercent: N,
)

data class SalaryCalculationBracketResult<N>(
    val order: Int,
    val lowerBound: N,
    val upperBound: N,
    val ratePercent: N,
    val taxableAmount: N,
    val tax: N,
)

data class SalaryCalculationMajorations<N>(
    val night: N,
    val sunday: N,
    val officialHoliday: N,
    val decreePaidHoliday: N,
    val mayFirst: N,
    val replacement: N,
    val total: N,
)

data class SalaryCalculationResult<N>(
    val target: N,
    val baseGross: N,
    val totalGross: N,
    val netExact: N,
    val netRounded: N,
    val netDifference: N,
    val cnapsBase: N,
    val employeeCnaps: N,
    val healthMutual: N,
    val taxableBase: N,
    val taxDeduction: N,
    val irsaBeforeDeduction: N,
    val irsa: N,
    val minimumIrsaApplied: Boolean,
    val majorations: SalaryCalculationMajorations<N>,
    val brackets: List<SalaryCalculationBracketResult<N>>,
)

/** Les taux viennent de la configuration ; les arrondis sont fournis par la plateforme. */
interface SalaryCalculationArithmetic<N> {
    val zero: N
    val hundred: N
    fun integer(value: Int): N
    fun add(left: N, right: N): N
    fun subtract(left: N, right: N): N
    fun multiply(left: N, right: N): N
    fun divide(left: N, right: N): N
    fun floorToIncrement(value: N, increment: N): N
    fun roundToIncrement(value: N, increment: N): N
}

class SalaryCalculationCore<N : Comparable<N>>(
    private val parameters: SalaryCalculationParameters<N>,
    private val brackets: List<SalaryCalculationBracket<N>>,
    private val arithmetic: SalaryCalculationArithmetic<N>,
) {
    private val zero: N get() = arithmetic.zero
    private fun N.add(other: N): N = arithmetic.add(this, other)
    private fun N.subtract(other: N): N = arithmetic.subtract(this, other)
    private fun N.multiply(other: N): N = arithmetic.multiply(this, other)
    private fun N.divide(other: N): N = arithmetic.divide(this, other)
    private fun N.min(other: N): N = if (this <= other) this else other
    private fun N.max(other: N): N = if (this >= other) this else other
    private fun majorations(night: N = zero, sunday: N = zero, officialHoliday: N = zero,
        decreePaidHoliday: N = zero, mayFirst: N = zero, replacement: N = zero) = SalaryCalculationMajorations(
        night, sunday, officialHoliday, decreePaidHoliday, mayFirst, replacement,
        night.add(sunday).add(officialHoliday).add(decreePaidHoliday).add(mayFirst).add(replacement))

    fun calculate(baseGross: N, input: SalaryCalculationInput<N>): SalaryCalculationResult<N> {
        val majorations = if (input.mode == SalaryMode.GUARDIAN) {
            val hourly = baseGross.divide(parameters.guardianReferenceHours)
            majorations(
                night = hourly.multiply(input.nightHours).multiply(parameters.nightRate),
                sunday = hourly.multiply(input.sundayHours).multiply(parameters.sundayRate),
                officialHoliday = hourly.multiply(input.officialHolidayHours).multiply(parameters.officialHolidayRate),
                decreePaidHoliday = hourly.multiply(input.decreePaidHolidayHours).multiply(parameters.decreePaidHolidayRate),
                mayFirst = hourly.multiply(input.mayFirstHours).multiply(parameters.mayFirstRate),
                replacement = hourly.multiply(input.replacementHours).multiply(parameters.guardianReplacementRate)
                    .add(hourly.multiply(input.ordinaryReplacementHours).multiply(parameters.guardianOrdinaryReplacementExtraRate)),
            )
        } else majorations()
        val effectiveGross = when (input.mode) {
            SalaryMode.DAILY -> baseGross.multiply(arithmetic.integer(input.days))
            SalaryMode.PRORATA -> baseGross.multiply(arithmetic.integer(input.days)).divide(parameters.prorataReferenceDays)
            else -> baseGross
        }
        val totalGross = effectiveGross.add(majorations.total)
        val ceiling = parameters.minimumSalary.multiply(parameters.cnapsCeilingMultiplier)
        val cnapsBase = totalGross.min(ceiling)
        val cnaps = cnapsBase.multiply(parameters.cnapsEmployeeRate)
        val mutual = cnaps
        val taxableExact = totalGross.subtract(cnaps).subtract(mutual)
        val taxable = arithmetic.floorToIncrement(taxableExact, parameters.taxableBaseFloorIncrement)
        val deduction = parameters.dependentIrsaDeduction.multiply(arithmetic.integer(input.dependents))
        var remaining = taxable
        var previous = zero
        var irsaBefore = zero
        val details = buildList {
            for (bracket in brackets) {
                if (remaining <= zero) break
                val width = bracket.upperBound.subtract(previous)
                val taxableAmount = remaining.min(width)
                val tax = taxableAmount.multiply(bracket.ratePercent.divide(arithmetic.hundred))
                add(SalaryCalculationBracketResult(bracket.order, previous, bracket.upperBound, bracket.ratePercent, taxableAmount, tax))
                irsaBefore = irsaBefore.add(tax)
                remaining = remaining.subtract(taxableAmount)
                previous = bracket.upperBound
            }
        }
        val afterDeduction = irsaBefore.subtract(deduction).max(zero)
        val minimumApplied = taxable > zero && afterDeduction < parameters.minimumIrsa
        val irsa = if (taxable > zero) afterDeduction.max(parameters.minimumIrsa) else zero
        val netExact = totalGross.subtract(cnaps).subtract(mutual).subtract(irsa)
        val netRounded = arithmetic.roundToIncrement(netExact, parameters.netRoundingIncrement)
        return SalaryCalculationResult(zero, baseGross, totalGross, netExact, netRounded, zero,
            cnapsBase, cnaps, mutual, taxable, deduction, irsaBefore, irsa, minimumApplied, majorations, details)
    }

}
