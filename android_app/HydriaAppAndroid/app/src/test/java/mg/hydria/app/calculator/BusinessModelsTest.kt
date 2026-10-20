package mg.hydria.app.calculator

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.math.BigDecimal

class BusinessModelsTest {
    @Test fun quoteUsesPreciseDecimalsAndComputesTotal() {
        val lines = QuoteCalculator.recalculate(listOf(
            QuoteLine(quantity = "2,5", unitPrice = "1 200"),
            QuoteLine(quantity = "3", unitPrice = "400.50"),
        ))
        decimal("3000", lines[0].amount)
        decimal("1201.50", lines[1].amount)
        decimal("4201.50", QuoteCalculator.total(lines))
        assertNull(QuoteCalculator.recalculate(listOf(QuoteLine(quantity = "abc", unitPrice = "2")))[0].amount)
    }

    @Test fun totalCriteriaSupportContainsEqualsCaseAndExactDate() {
        val lines = TotalCalculator.recalculate(listOf(
            TotalLine(date = "2026-08-01", designation = "Achat carburant", amountInput = "1 000"),
            TotalLine(date = "2026-08-02", designation = "achat pièces", amountInput = "500"),
            TotalLine(date = "2026-08-01", designation = "Carburant", amountInput = "250"),
        ))
        decimal("1750", TotalCalculator.total(lines))
        decimal("1500", TotalCalculator.result(lines, FilterCriterion(designation = " ACHAT ")).subtotal)
        decimal("250", TotalCalculator.result(lines, FilterCriterion(mode = ComparisonMode.EQUALS, designation = "carburant")).subtotal)
        decimal("1000", TotalCalculator.result(lines, FilterCriterion(designation = "achat", date = "2026-08-01")).subtotal)
        decimal("1750", TotalCalculator.result(lines, FilterCriterion()).subtotal)
    }

    @Test fun cashBalanceCascadesAfterIntermediateDeletion() {
        val lines = CashCalculator.recalculate(listOf(
            CashLine(entryInput = "1000"),
            CashLine(exitInput = "250"),
            CashLine(entryInput = "10,5"),
        ))
        decimal("1000", lines[0].balance)
        decimal("750", lines[1].balance)
        decimal("760.5", lines[2].balance)
        val afterDeletion = CashCalculator.recalculate(listOf(lines[0], lines[2]))
        decimal("1010.5", afterDeletion[1].balance)
    }

    @Test fun cashCriteriaAndBookNameRulesAreApplied() {
        val lines = CashCalculator.recalculate(listOf(
            CashLine(date = "2026-08-01", designation = "Vente eau", entryInput = "500"),
            CashLine(date = "2026-08-01", designation = "Achat eau", exitInput = "125"),
        ))
        val result = CashCalculator.result(lines, FilterCriterion(designation = "eau", date = "2026-08-01"))
        decimal("500", result.entries)
        decimal("125", result.exits)
        decimal("375", result.net)
        assertEquals("Caisse août 2026", CashCalculator.normalizeBookName("  Caisse   août  2026 "))
        assertEquals(80, CashCalculator.normalizeBookName("x".repeat(100)).length)
    }

    @Test fun businessLineLimitsAndMinimumLineAreApplied() {
        assertEquals(QuoteCalculator.MAX_LINES, QuoteCalculator.recalculate(List(505) { QuoteLine() }).size)
        assertEquals(1, TotalCalculator.recalculate(emptyList()).size)
        assertEquals(CashCalculator.MAX_LINES, CashCalculator.recalculate(List(1005) { CashLine() }).size)
    }

    private fun decimal(expected: String, actual: BigDecimal?) =
        assertEquals(0, BigDecimal(expected).compareTo(requireNotNull(actual)))
}
