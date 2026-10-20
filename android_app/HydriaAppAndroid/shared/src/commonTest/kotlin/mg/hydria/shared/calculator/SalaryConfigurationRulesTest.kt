package mg.hydria.shared.calculator

import kotlin.test.*

class SalaryConfigurationRulesTest {
    private val brackets = listOf(SalaryCalculationBracket(1, 100, 0), SalaryCalculationBracket(2, 200, 10))
    private fun valid(rows: List<SalaryCalculationBracket<Int>> = brackets, positives: List<Int> = listOf(1, 30, 240, 173, 100, 100),
        minimum: Int = 0, mutual: Boolean = true, formula: Int = 1, organisation: String = "global", version: String = "1") =
        SalaryConfigurationRules.valid(formula, 1, organisation, version, rows, 0, minimum, positives, mutual)
    @Test fun acceptsBaselineAndRejectsUnknownVersionOrMissingIdentity() {
        assertTrue(valid())
        assertFalse(valid(formula = 2))
        assertFalse(valid(organisation = " "))
        assertFalse(valid(version = ""))
    }
    @Test fun bracketsRequireUniqueOrderAndIncreasingPositiveBounds() {
        assertFalse(valid(rows = emptyList()))
        assertFalse(valid(rows = listOf(brackets[0], brackets[1].copy(order = 1))))
        assertFalse(valid(rows = brackets.reversed()))
        assertFalse(valid(rows = listOf(SalaryCalculationBracket(1, 0, 0))))
        assertFalse(valid(rows = listOf(SalaryCalculationBracket(1, 100, -1))))
    }
    @Test fun divisorsAndRequiredPolicyStayValidated() {
        assertFalse(valid(positives = listOf(1, 0, 2)))
        assertFalse(valid(positives = listOf(-1)))
        assertFalse(valid(minimum = -1))
        assertFalse(valid(mutual = false))
    }
}
