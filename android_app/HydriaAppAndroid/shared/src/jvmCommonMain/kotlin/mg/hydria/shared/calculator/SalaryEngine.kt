package mg.hydria.shared.calculator

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode

data class SalaryInput(
    val basis: SalaryBasis = SalaryBasis.NET,
    val target: BigDecimal,
    val dependents: Int = 0,
    val mode: SalaryMode = SalaryMode.STANDARD,
    val days: Int = 0,
    val nightHours: BigDecimal = BigDecimal.ZERO,
    val sundayHours: BigDecimal = BigDecimal.ZERO,
    val officialHolidayHours: BigDecimal = BigDecimal.ZERO,
    val decreePaidHolidayHours: BigDecimal = BigDecimal.ZERO,
    val mayFirstHours: BigDecimal = BigDecimal.ZERO,
    val replacementHours: BigDecimal = BigDecimal.ZERO,
    val ordinaryReplacementHours: BigDecimal = BigDecimal.ZERO,
)


data class IrsaBracketResult(
    val order: Int,
    val lowerBound: BigDecimal,
    val upperBound: BigDecimal,
    val ratePercent: BigDecimal,
    val taxableAmount: BigDecimal,
    val tax: BigDecimal,
)

data class SalaryMajorations(
    val night: BigDecimal = BigDecimal.ZERO,
    val sunday: BigDecimal = BigDecimal.ZERO,
    val officialHoliday: BigDecimal = BigDecimal.ZERO,
    val decreePaidHoliday: BigDecimal = BigDecimal.ZERO,
    val mayFirst: BigDecimal = BigDecimal.ZERO,
    val replacement: BigDecimal = BigDecimal.ZERO,
) {
    val total: BigDecimal get() = night + sunday + officialHoliday + decreePaidHoliday + mayFirst + replacement
}

data class SalaryResult(
    val target: BigDecimal,
    val baseGross: BigDecimal,
    val totalGross: BigDecimal,
    val netExact: BigDecimal,
    val netRounded: BigDecimal,
    val netDifference: BigDecimal,
    val cnapsBase: BigDecimal,
    val employeeCnaps: BigDecimal,
    val healthMutual: BigDecimal,
    val taxableBase: BigDecimal,
    val taxDeduction: BigDecimal,
    val irsaBeforeDeduction: BigDecimal,
    val irsa: BigDecimal,
    val minimumIrsaApplied: Boolean,
    val majorations: SalaryMajorations,
    val brackets: List<IrsaBracketResult>,
)

sealed class SalarySimulation {
    data class Success(val result: SalaryResult) : SalarySimulation()
    data class Invalid(val error: SalaryInputError) : SalarySimulation()
}

class SalaryEngine(private val config: SalaryConfig) {
    fun simulate(input: SalaryInput): SalarySimulation {
        validate(input)?.let { return SalarySimulation.Invalid(it) }
        val gross = if (input.basis == SalaryBasis.GROSS) input.target else solveGross(input)
        val result = calculate(gross, input)
        return SalarySimulation.Success(result.copy(
            target = input.target,
            netDifference = if (input.basis == SalaryBasis.NET) result.netExact.subtract(input.target).abs() else BigDecimal.ZERO,
        ))
    }

    fun validate(input: SalaryInput): SalaryInputError? = SalaryInputRules.validate(
        input.target, BigDecimal.ZERO, input.dependents, input.mode, input.days,
        listOf(input.nightHours, input.sundayHours, input.officialHolidayHours, input.decreePaidHolidayHours,
            input.mayFirstHours, input.replacementHours, input.ordinaryReplacementHours),
        input.ordinaryReplacementHours, input.replacementHours)

    private val grossSearch = GrossSalarySearch(object : GrossSearchArithmetic<BigDecimal> {
        override val zero = BigDecimal.ZERO
        override val one = BigDecimal.ONE
        override val cent = CENT
        override fun add(left: BigDecimal, right: BigDecimal) = left.add(right)
        override fun subtract(left: BigDecimal, right: BigDecimal) = left.subtract(right)
        override fun twice(value: BigDecimal) = value.multiply(TWO)
        override fun midpoint(lower: BigDecimal, upper: BigDecimal) = lower.add(upper).divide(TWO, CONTEXT)
        override fun absolute(value: BigDecimal) = value.abs()
        override fun roundWhole(value: BigDecimal) = value.setScale(0, RoundingMode.HALF_UP)
    })
    private fun solveGross(input: SalaryInput): BigDecimal = grossSearch.solve(input.target) { calculate(it, input).netExact }

    private val calculation = SalaryCalculationCore(
        SalaryCalculationParameters(
            minimumSalary = config.parameters.minimumSalary,
            cnapsCeilingMultiplier = config.parameters.cnapsCeilingMultiplier,
            cnapsEmployeeRate = config.parameters.cnapsEmployeeRate,
            healthMutualMatchesCnaps = config.parameters.healthMutualMatchesCnaps,
            dependentIrsaDeduction = config.parameters.dependentIrsaDeduction,
            minimumIrsa = config.parameters.minimumIrsa,
            prorataReferenceDays = config.parameters.prorataReferenceDays,
            guardianReferenceHours = config.parameters.guardianReferenceHours,
            employeeReferenceHours = config.parameters.employeeReferenceHours,
            guardianDefaultNightHours = config.parameters.guardianDefaultNightHours,
            nightRate = config.parameters.nightRate,
            sundayRate = config.parameters.sundayRate,
            officialHolidayRate = config.parameters.officialHolidayRate,
            decreePaidHolidayRate = config.parameters.decreePaidHolidayRate,
            mayFirstRate = config.parameters.mayFirstRate,
            guardianReplacementRate = config.parameters.guardianReplacementRate,
            guardianOrdinaryReplacementExtraRate = config.parameters.guardianOrdinaryReplacementExtraRate,
            taxableBaseFloorIncrement = config.parameters.taxableBaseFloorIncrement,
            netRoundingIncrement = config.parameters.netRoundingIncrement),
        config.brackets.map { SalaryCalculationBracket(it.order, it.upperBound, it.ratePercent) },
        object : SalaryCalculationArithmetic<BigDecimal> {
            override val zero = BigDecimal.ZERO
            override val hundred = HUNDRED
            override fun integer(value: Int) = BigDecimal(value)
            override fun add(left: BigDecimal, right: BigDecimal) = left.add(right)
            override fun subtract(left: BigDecimal, right: BigDecimal) = left.subtract(right)
            override fun multiply(left: BigDecimal, right: BigDecimal) = left.multiply(right)
            override fun divide(left: BigDecimal, right: BigDecimal) = left.divide(right, CONTEXT)
            override fun floorToIncrement(value: BigDecimal, increment: BigDecimal) =
                value.divide(increment, 0, RoundingMode.FLOOR).multiply(increment)
            override fun roundToIncrement(value: BigDecimal, increment: BigDecimal) =
                value.divide(increment, 0, RoundingMode.HALF_UP).multiply(increment)
        })

    private fun calculate(baseGross: BigDecimal, input: SalaryInput): SalaryResult {
        val result = calculation.calculate(baseGross, SalaryCalculationInput(
            basis = input.basis,
            target = input.target,
            dependents = input.dependents,
            mode = input.mode,
            days = input.days,
            nightHours = input.nightHours,
            sundayHours = input.sundayHours,
            officialHolidayHours = input.officialHolidayHours,
            decreePaidHolidayHours = input.decreePaidHolidayHours,
            mayFirstHours = input.mayFirstHours,
            replacementHours = input.replacementHours,
            ordinaryReplacementHours = input.ordinaryReplacementHours))
        return SalaryResult(
            target = result.target,
            baseGross = result.baseGross,
            totalGross = result.totalGross,
            netExact = result.netExact,
            netRounded = result.netRounded,
            netDifference = result.netDifference,
            cnapsBase = result.cnapsBase,
            employeeCnaps = result.employeeCnaps,
            healthMutual = result.healthMutual,
            taxableBase = result.taxableBase,
            taxDeduction = result.taxDeduction,
            irsaBeforeDeduction = result.irsaBeforeDeduction,
            irsa = result.irsa,
            minimumIrsaApplied = result.minimumIrsaApplied,
            majorations = SalaryMajorations(result.majorations.night, result.majorations.sunday, result.majorations.officialHoliday, result.majorations.decreePaidHoliday, result.majorations.mayFirst, result.majorations.replacement),
            brackets = result.brackets.map { IrsaBracketResult(it.order, it.lowerBound, it.upperBound, it.ratePercent, it.taxableAmount, it.tax) })
    }

    companion object {
        private val CONTEXT = MathContext(28, RoundingMode.HALF_EVEN)
        private val TWO = BigDecimal("2")
        private val CENT = BigDecimal("0.01")
        private val HUNDRED = BigDecimal("100")
    }
}
