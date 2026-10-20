package mg.hydria.app.calculator

import mg.hydria.shared.calculator.*
import org.junit.Assert.*
import org.junit.Test
import java.math.BigDecimal

class SalaryMigrationCompatibilityTest {
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

    private fun bd(text: String) = BigDecimal(text)
    @Test fun allModesAndBasesMatchEveryLegacyResultField() {
        val old = LegacySalaryEngine(config)
        val current = mg.hydria.shared.calculator.SalaryEngine(config)
        for (mode in SalaryMode.entries) for (basis in SalaryBasis.entries)
            for (target in listOf("1", "20000", "350000", "480500", "2000000", "3000000.25")) {
                val input = SalaryInput(basis = basis, target = bd(target), mode = mode, days = 15, dependents = 2,
                    nightHours = bd("56"), sundayHours = bd("10"), officialHolidayHours = bd("5"),
                    decreePaidHolidayHours = bd("4"), mayFirstHours = bd("8"), replacementHours = bd("12"), ordinaryReplacementHours = bd("6"))
                assertEquals("$mode $basis $target", old.simulate(input), current.simulate(input))
            }
    }
    @Test fun invalidInputsKeepErrorPriority() {
        val old = LegacySalaryEngine(config)
        val current = mg.hydria.shared.calculator.SalaryEngine(config)
        val inputs = listOf(SalaryInput(target = BigDecimal.ZERO, dependents = -1),
            SalaryInput(target = BigDecimal.ONE, dependents = -1, mode = SalaryMode.DAILY),
            SalaryInput(target = BigDecimal.ONE, mode = SalaryMode.DAILY, nightHours = bd("-1")),
            SalaryInput(target = BigDecimal.ONE, nightHours = bd("-1"), ordinaryReplacementHours = bd("1")),
            SalaryInput(target = BigDecimal.ONE, ordinaryReplacementHours = bd("1")))
        inputs.forEach { assertEquals(old.simulate(it), current.simulate(it)) }
    }

    @Test fun parameterVariationsPreserveEveryResultField() {
        val configurations = listOf(config,
            config.copy(parameters = config.parameters.copy(minimumSalary = bd("300000"), cnapsEmployeeRate = bd("0.02"),
                cnapsCeilingMultiplier = bd("4"), dependentIrsaDeduction = bd("2500"), minimumIrsa = bd("5000"))),
            config.copy(parameters = config.parameters.copy(prorataReferenceDays = bd("26"), guardianReferenceHours = bd("173.33"),
                nightRate = bd("0.25"), sundayRate = bd("0.35"), officialHolidayRate = bd("0.45"), decreePaidHolidayRate = bd("0.15"),
                mayFirstRate = bd("1.25"), guardianReplacementRate = bd("1.1"), guardianOrdinaryReplacementExtraRate = bd("0.2"))),
            config.copy(parameters = config.parameters.copy(taxableBaseFloorIncrement = bd("50"), netRoundingIncrement = bd("25")),
                brackets = config.brackets.map { it.copy(ratePercent = it.ratePercent.add(bd("1.25"))) }))
        for (configuration in configurations) for (mode in SalaryMode.entries) for (basis in SalaryBasis.entries) {
            val input = SalaryInput(basis = basis, target = bd("480500.125"), mode = mode, days = 17, dependents = 3,
                nightHours = bd("56.5"), sundayHours = bd("9"), officialHolidayHours = bd("5"), decreePaidHolidayHours = bd("3"),
                mayFirstHours = bd("2"), replacementHours = bd("8"), ordinaryReplacementHours = bd("4"))
            assertEquals("$mode $basis", LegacySalaryEngine(configuration).simulate(input),
                mg.hydria.shared.calculator.SalaryEngine(configuration).simulate(input))
        }
    }
}
