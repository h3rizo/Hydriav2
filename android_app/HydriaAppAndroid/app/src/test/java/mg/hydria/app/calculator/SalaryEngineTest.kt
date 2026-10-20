package mg.hydria.app.calculator

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class SalaryEngineTest {
    private val config = SalaryConfig(
        id = "fixture-v1",
        organisation = "global",
        version = "1",
        formulaVersion = 1,
        effectiveFrom = "2026-01-01",
        serverUpdatedAt = "2026-01-01T00:00:00Z",
        checksum = "x".repeat(64),
        localSyncedAt = 0,
        parameters = SalaryParameters(
            minimumSalary = bd("250000"),
            cnapsCeilingMultiplier = bd("8"),
            cnapsEmployeeRate = bd("0.01"),
            healthMutualMatchesCnaps = true,
            dependentIrsaDeduction = bd("2000"),
            minimumIrsa = bd("3000"),
            prorataReferenceDays = bd("30"),
            guardianReferenceHours = bd("240"),
            employeeReferenceHours = bd("173.33"),
            guardianDefaultNightHours = bd("56"),
            nightRate = bd("0.30"),
            sundayRate = bd("0.40"),
            officialHolidayRate = bd("0.50"),
            decreePaidHolidayRate = bd("0.30"),
            mayFirstRate = bd("1.00"),
            guardianReplacementRate = bd("1.00"),
            guardianOrdinaryReplacementExtraRate = bd("0.30"),
            taxableBaseFloorIncrement = bd("100"),
            netRoundingIncrement = bd("100"),
        ),
        brackets = listOf(
            IrsaBracket(1, bd("350000"), bd("0")),
            IrsaBracket(2, bd("400000"), bd("5")),
            IrsaBracket(3, bd("500000"), bd("10")),
            IrsaBracket(4, bd("1000000000"), bd("20")),
        ),
    )
    private val engine = SalaryEngine(config)

    @Test fun standardGrossMatchesDjangoRules() {
        val result = success(SalaryInput(SalaryBasis.GROSS, bd("500000"), dependents = 1))
        decimal("500000", result.baseGross)
        decimal("500000", result.totalGross)
        decimal("500000", result.cnapsBase)
        decimal("5000", result.employeeCnaps)
        decimal("5000", result.healthMutual)
        decimal("490000", result.taxableBase)
        decimal("2000", result.taxDeduction)
        decimal("11500", result.irsaBeforeDeduction)
        decimal("9500", result.irsa)
        decimal("480500", result.netExact)
        decimal("480500", result.netRounded)
        assertEquals(3, result.brackets.size)
    }

    @Test fun grossFromNetFindsBestIntegerGross() {
        val result = success(SalaryInput(SalaryBasis.NET, bd("480500"), dependents = 1))
        decimal("499990", result.baseGross)
        decimal("480500.20", result.netExact)
        decimal("0.20", result.netDifference)
    }

    @Test fun prorataDailyMinimumIrsaAndCnapsCeilingMatch() {
        val prorata = success(SalaryInput(SalaryBasis.GROSS, bd("600000"), mode = SalaryMode.PRORATA, days = 15))
        decimal("300000", prorata.totalGross)
        decimal("3000", prorata.irsa)
        decimal("291000", prorata.netRounded)

        val daily = success(SalaryInput(SalaryBasis.GROSS, bd("20000"), mode = SalaryMode.DAILY, days = 20))
        decimal("400000", daily.totalGross)
        decimal("3000", daily.irsa)
        decimal("389000", daily.netRounded)

        val capped = success(SalaryInput(SalaryBasis.GROSS, bd("3000000")))
        decimal("2000000", capped.cnapsBase)
        decimal("20000", capped.employeeCnaps)
    }

    @Test fun guardianMajorationsAndOrdinaryReplacementMatch() {
        val result = success(SalaryInput(
            basis = SalaryBasis.GROSS,
            target = bd("480000"),
            mode = SalaryMode.GUARDIAN,
            nightHours = bd("56"),
            sundayHours = bd("10"),
            officialHolidayHours = bd("5"),
            decreePaidHolidayHours = bd("4"),
            mayFirstHours = bd("8"),
            replacementHours = bd("12"),
            ordinaryReplacementHours = bd("6"),
        ))
        decimal("33600", result.majorations.night)
        decimal("8000", result.majorations.sunday)
        decimal("5000", result.majorations.officialHoliday)
        decimal("2400", result.majorations.decreePaidHoliday)
        decimal("16000", result.majorations.mayFirst)
        decimal("27600", result.majorations.replacement)
        decimal("572600", result.totalGross)
        decimal("561100", result.taxableBase)
        decimal("24720", result.irsa)
        decimal("536400", result.netRounded)
    }

    @Test fun validationsRejectInvalidInputs() {
        assertEquals(SalaryInputError.TARGET, engine.validate(SalaryInput(target = BigDecimal.ZERO)))
        assertEquals(SalaryInputError.DEPENDENTS, engine.validate(SalaryInput(target = BigDecimal.ONE, dependents = -1)))
        assertEquals(SalaryInputError.DAYS, engine.validate(SalaryInput(target = BigDecimal.ONE, mode = SalaryMode.PRORATA)))
        assertEquals(SalaryInputError.HOURS, engine.validate(SalaryInput(target = BigDecimal.ONE, nightHours = bd("-1"))))
        assertEquals(SalaryInputError.ORDINARY_REPLACEMENT, engine.validate(SalaryInput(target = BigDecimal.ONE,
            replacementHours = bd("2"), ordinaryReplacementHours = bd("3"))))
    }

    private fun success(input: SalaryInput): SalaryResult {
        val simulation = engine.simulate(input)
        assertTrue(simulation is mg.hydria.shared.calculator.SalarySimulation.Success)
        return (simulation as mg.hydria.shared.calculator.SalarySimulation.Success).result
    }

    private fun decimal(expected: String, actual: BigDecimal) = assertEquals("$expected != ${actual.toPlainString()}", 0, bd(expected).compareTo(actual))
    private fun bd(value: String) = BigDecimal(value)
}
