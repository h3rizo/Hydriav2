package mg.hydria.shared.calculator

import kotlin.test.*

class CalculatorWorkbookCoreTest {
    @Test fun recalculationReceivesPreviousOutputsInOrder() {
        val core = CalculatorWorkbookCore<Int> { expression, index, total, previous ->
            assertEquals(3, total)
            assertEquals(index, previous.size)
            ArithmeticResult((previous.lastOrNull()?.value ?: 0) + expression.toInt())
        }
        val result = core.recalculate(listOf(CalculationDraft("a", "1"), CalculationDraft("b", "2"), CalculationDraft("c", "3"))) { error("unused") }
        assertEquals(listOf(1, 3, 6), result.map { it.value })
        assertEquals(listOf("a", "b", "c"), result.map { it.item })
    }
    @Test fun emptyFactoryIsLazyAndLimitAppliesBeforeEvaluation() {
        var calls = 0
        val core = CalculatorWorkbookCore<Int> { _, index, total, _ -> assertEquals(1000, total); calls++; ArithmeticResult(index) }
        assertEquals(1000, core.recalculate(List(1001) { CalculationDraft(it, "") }) { error("unused") }.size)
        assertEquals(1000, calls)
        var factoryCalls = 0
        assertEquals(listOf("new"), CalculatorStateRules.calculationLines(emptyList()) { factoryCalls++; "new" })
        assertEquals(1, factoryCalls)
    }
    @Test fun selectionAndUnknownTabKeepFallbacks() {
        assertEquals(0, CalculatorStateRules.activeLine(-1, 10))
        assertEquals(9, CalculatorStateRules.activeLine(100, 10))
        assertEquals(CalculatorTab.CASH, CalculatorStateRules.tab("CASH"))
        assertEquals(CalculatorTab.CALCULATIONS, CalculatorStateRules.tab("cash"))
    }
    @Test fun booksAreLimitedBeforeNormalizationFilteringAndStableSort() {
        val books = listOf(" Z ", " ", " a ", "A") + List(196) { " " } + "outside limit"
        val result = CalculatorStateRules.cashBooks(books, { it.trim() }, { it })
        assertEquals(listOf("a", "A", "Z"), result)
    }
}
