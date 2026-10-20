package mg.hydria.app.calculator

import mg.hydria.shared.calculator.*
import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode

internal class LegacySalaryEngine(private val config: SalaryConfig) {
    fun simulate(input: SalaryInput): SalarySimulation {
        validate(input)?.let { return mg.hydria.shared.calculator.SalarySimulation.Invalid(it) }
        val gross = if (input.basis == SalaryBasis.GROSS) input.target else solveGross(input)
        val result = calculate(gross, input)
        return mg.hydria.shared.calculator.SalarySimulation.Success(result.copy(
            target = input.target,
            netDifference = if (input.basis == SalaryBasis.NET) result.netExact.subtract(input.target).abs() else BigDecimal.ZERO,
        ))
    }

    fun validate(input: SalaryInput): SalaryInputError? = when {
        input.target <= BigDecimal.ZERO -> SalaryInputError.TARGET
        input.dependents < 0 -> SalaryInputError.DEPENDENTS
        input.mode in setOf(SalaryMode.PRORATA, SalaryMode.DAILY) && input.days <= 0 -> SalaryInputError.DAYS
        listOf(input.nightHours, input.sundayHours, input.officialHolidayHours, input.decreePaidHolidayHours,
            input.mayFirstHours, input.replacementHours, input.ordinaryReplacementHours).any { it < BigDecimal.ZERO } -> SalaryInputError.HOURS
        input.ordinaryReplacementHours > input.replacementHours -> SalaryInputError.ORDINARY_REPLACEMENT
        else -> null
    }

    private fun solveGross(input: SalaryInput): BigDecimal {
        var lower = BigDecimal.ZERO
        var upper = input.target.max(BigDecimal.ONE)
        repeat(100) {
            if (calculate(upper, input).netExact >= input.target) return@repeat
            upper = upper.multiply(TWO)
        }
        var estimate = upper
        repeat(100) {
            estimate = lower.add(upper).divide(TWO, CONTEXT)
            val net = calculate(estimate, input).netExact
            if (net.subtract(input.target).abs() <= CENT) return@repeat
            if (net < input.target) lower = estimate else upper = estimate
        }
        val rounded = estimate.setScale(0, RoundingMode.HALF_UP)
        return listOf((rounded - BigDecimal.ONE).max(BigDecimal.ZERO), rounded.max(BigDecimal.ZERO), rounded + BigDecimal.ONE)
            .minWith(compareBy<BigDecimal> { calculate(it, input).netExact.subtract(input.target).abs() }.thenBy { it })
    }

    private fun calculate(baseGross: BigDecimal, input: SalaryInput): SalaryResult {
        val parameters = config.parameters
        val majorations = if (input.mode == SalaryMode.GUARDIAN) {
            val hourly = baseGross.divide(parameters.guardianReferenceHours, CONTEXT)
            SalaryMajorations(
                night = hourly.multiply(input.nightHours).multiply(parameters.nightRate),
                sunday = hourly.multiply(input.sundayHours).multiply(parameters.sundayRate),
                officialHoliday = hourly.multiply(input.officialHolidayHours).multiply(parameters.officialHolidayRate),
                decreePaidHoliday = hourly.multiply(input.decreePaidHolidayHours).multiply(parameters.decreePaidHolidayRate),
                mayFirst = hourly.multiply(input.mayFirstHours).multiply(parameters.mayFirstRate),
                replacement = hourly.multiply(input.replacementHours).multiply(parameters.guardianReplacementRate)
                    .add(hourly.multiply(input.ordinaryReplacementHours).multiply(parameters.guardianOrdinaryReplacementExtraRate)),
            )
        } else SalaryMajorations()
        val effectiveGross = when (input.mode) {
            SalaryMode.DAILY -> baseGross.multiply(BigDecimal(input.days))
            SalaryMode.PRORATA -> baseGross.multiply(BigDecimal(input.days)).divide(parameters.prorataReferenceDays, CONTEXT)
            else -> baseGross
        }
        val totalGross = effectiveGross.add(majorations.total)
        val ceiling = parameters.minimumSalary.multiply(parameters.cnapsCeilingMultiplier)
        val cnapsBase = totalGross.min(ceiling)
        val cnaps = cnapsBase.multiply(parameters.cnapsEmployeeRate)
        val mutual = cnaps
        val taxableExact = totalGross.subtract(cnaps).subtract(mutual)
        val taxable = floorToIncrement(taxableExact, parameters.taxableBaseFloorIncrement)
        val deduction = parameters.dependentIrsaDeduction.multiply(BigDecimal(input.dependents))
        var remaining = taxable
        var previous = BigDecimal.ZERO
        var irsaBefore = BigDecimal.ZERO
        val details = buildList {
            for (bracket in config.brackets) {
                if (remaining <= BigDecimal.ZERO) break
                val width = bracket.upperBound.subtract(previous)
                val taxableAmount = remaining.min(width)
                val tax = taxableAmount.multiply(bracket.ratePercent.divide(HUNDRED, CONTEXT))
                add(IrsaBracketResult(bracket.order, previous, bracket.upperBound, bracket.ratePercent, taxableAmount, tax))
                irsaBefore = irsaBefore.add(tax)
                remaining = remaining.subtract(taxableAmount)
                previous = bracket.upperBound
            }
        }
        val afterDeduction = irsaBefore.subtract(deduction).max(BigDecimal.ZERO)
        val minimumApplied = taxable > BigDecimal.ZERO && afterDeduction < parameters.minimumIrsa
        val irsa = if (taxable > BigDecimal.ZERO) afterDeduction.max(parameters.minimumIrsa) else BigDecimal.ZERO
        val netExact = totalGross.subtract(cnaps).subtract(mutual).subtract(irsa)
        val netRounded = roundToIncrement(netExact, parameters.netRoundingIncrement)
        return SalaryResult(BigDecimal.ZERO, baseGross, totalGross, netExact, netRounded, BigDecimal.ZERO,
            cnapsBase, cnaps, mutual, taxable, deduction, irsaBefore, irsa, minimumApplied, majorations, details)
    }

    private fun floorToIncrement(value: BigDecimal, increment: BigDecimal): BigDecimal =
        value.divide(increment, 0, RoundingMode.FLOOR).multiply(increment)

    private fun roundToIncrement(value: BigDecimal, increment: BigDecimal): BigDecimal =
        value.divide(increment, 0, RoundingMode.HALF_UP).multiply(increment)

    companion object {
        private val CONTEXT = MathContext(28, RoundingMode.HALF_EVEN)
        private val TWO = BigDecimal("2")
        private val CENT = BigDecimal("0.01")
        private val HUNDRED = BigDecimal("100")
    }
}

