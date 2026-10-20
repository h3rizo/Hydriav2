package mg.hydria.app.calculator

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class CalculatorStateTest {
    @Test fun persistedInputsAreRestoredAndDerivedResultsRecalculated() {
        val source = CalculatorState(
            selectedTab = CalculatorTab.TOTAL,
            activeCalculationLine = 1,
            calculationLines = listOf(
                CalculationLine(label = "Base", expression = "12500 × 3"),
                CalculationLine(label = "Avec marge", expression = "L1 + L1 × 10%"),
            ),
        )
        val restored = CalculatorState.fromJson(source.toJson())
        assertEquals(CalculatorTab.TOTAL, restored.selectedTab)
        assertEquals(1, restored.activeCalculationLine)
        assertEquals("Avec marge", restored.calculationLines[1].label)
        assertNotNull(restored.calculationLines[1].result)
        assertEquals(0, restored.calculationLines[1].result!!.compareTo("41250".toBigDecimal()))
    }

    @Test fun atLeastOneLineIsAlwaysRestored() {
        val state = CalculatorState(calculationLines = emptyList()).normalized()
        assertEquals(1, state.calculationLines.size)
        assertEquals(0, state.activeCalculationLine)
    }

    @Test fun namedCashBooksSurviveASerializationRoundTrip() {
        // Sérialisation d'un état réduit aux cahiers nommés. Le passage par « Tout effacer » (CALC_VOL-04) est
        // testé dans CalculatorRepositoryTest.
        val books = listOf(NamedCashBook(name = "Septembre 2026", updatedAt = 123L,
            lines = listOf(CashLine(entryInput = "500")), criteria = emptyList()))
        val cleared = CalculatorState.fromJson(CalculatorState(namedCashBooks = books).toJson())
        assertEquals("Septembre 2026", cleared.namedCashBooks.single().name)
        assertEquals(0, cleared.namedCashBooks.single().lines.single().balance.compareTo("500".toBigDecimal()))
        assertEquals(1, cleared.calculationLines.size)
        assertEquals("", cleared.calculationLines.single().expression)
    }

    @Test fun lineLimitIsAppliedDuringNormalization() {
        val rows = List(CalculatorState.MAX_CALCULATION_LINES + 5) { CalculationLine(expression = it.toString()) }
        assertEquals(CalculatorState.MAX_CALCULATION_LINES, CalculatorState(calculationLines = rows).normalized().calculationLines.size)
    }

    @Test fun businessDraftsAndNamedBooksAreRestoredFromInputs() {
        val state = CalculatorState(
            quoteLines = listOf(QuoteLine(designation = "Tube", quantity = "2", unitPrice = "1500")),
            totalLines = listOf(TotalLine(date = "2026-09-01", designation = "Essai", amountInput = "750")),
            totalCriteria = listOf(FilterCriterion(mode = ComparisonMode.EQUALS, designation = "Essai")),
            cashLines = listOf(CashLine(designation = "Entrée", entryInput = "1000"), CashLine(designation = "Sortie", exitInput = "250")),
            cashCriteria = listOf(FilterCriterion(designation = "Entrée")),
            namedCashBooks = listOf(NamedCashBook(name = "  Septembre   2026 ", updatedAt = 123L,
                lines = listOf(CashLine(entryInput = "500")), criteria = emptyList())),
            salaryDraft = SalaryDraft(basis = SalaryBasis.GROSS, mode = SalaryMode.GUARDIAN, target = "500000"),
            gpsDraft = GpsDraft(dmsInput = "S 17°01'19,4\" E049°28'45,5\"", latitude = "-17.02205556",
                longitude = "49.47930556", updatedAt = 456L),
        )
        val restored = CalculatorState.fromJson(state.toJson())
        assertEquals(0, restored.quoteLines.single().amount!!.compareTo("3000".toBigDecimal()))
        assertEquals(0, restored.totalLines.single().amount!!.compareTo("750".toBigDecimal()))
        assertEquals(ComparisonMode.EQUALS, restored.totalCriteria.single().mode)
        assertEquals(0, restored.cashLines.last().balance.compareTo("750".toBigDecimal()))
        assertEquals("Septembre 2026", restored.namedCashBooks.single().name)
        assertEquals(0, restored.namedCashBooks.single().lines.single().balance.compareTo("500".toBigDecimal()))
        assertEquals(SalaryMode.GUARDIAN, restored.salaryDraft.mode)
        assertEquals("500000", restored.salaryDraft.target)
        assertEquals("-17.02205556", restored.gpsDraft.latitude)
        assertEquals(456L, restored.gpsDraft.updatedAt)
    }
}
