package mg.hydria.shared.calculator

import kotlin.test.*

class SalaryInputRulesTest {
    @Test fun validationKeepsPriorityAndModeSpecificDays() {
        assertEquals(SalaryInputError.TARGET, SalaryInputRules.validate(0, 0, -1, SalaryMode.DAILY, 0, listOf(-1), 1, 0))
        assertEquals(SalaryInputError.DEPENDENTS, SalaryInputRules.validate(1, 0, -1, SalaryMode.DAILY, 0, listOf(-1), 1, 0))
        assertEquals(SalaryInputError.DAYS, SalaryInputRules.validate(1, 0, 0, SalaryMode.DAILY, 0, listOf(-1), 1, 0))
        assertEquals(SalaryInputError.HOURS, SalaryInputRules.validate(1, 0, 0, SalaryMode.STANDARD, 0, listOf(-1), 1, 0))
        assertEquals(SalaryInputError.ORDINARY_REPLACEMENT, SalaryInputRules.validate(1, 0, 0, SalaryMode.GUARDIAN, 0, listOf(1), 1, 0))
        assertNull(SalaryInputRules.validate(1, 0, 0, SalaryMode.STANDARD, 0, listOf(0), 0, 0))
    }
    @Test fun grossSearchChoosesLowerIntegerWhenErrorsTie() {
        val search = GrossSalarySearch(object : GrossSearchArithmetic<Double> {
            override val zero = 0.0
            override val one = 1.0
            override val cent = 0.01
            override fun add(left: Double, right: Double) = left + right
            override fun subtract(left: Double, right: Double) = left - right
            override fun twice(value: Double) = value * 2
            override fun midpoint(lower: Double, upper: Double) = (lower + upper) / 2
            override fun absolute(value: Double) = kotlin.math.abs(value)
            override fun roundWhole(value: Double) = kotlin.math.floor(value + 0.5)
        })
        assertEquals(10.0, search.solve(10.5) { it })
        assertEquals(100.0, search.solve(80.0) { it * 0.8 })
    }
}
