package mg.hydria.app.calculator

import org.junit.Assert.*
import org.junit.Test

class BusinessMigrationCompatibilityTest {
    private val inputs = listOf("", "0", "-2", "1,25", "1 234.50", "0.0000000000000000000000001", "999999999999999999999999999999.99", "invalid", "1e3")
    @Test fun quoteRowsAndExactTotalsMatchOldImplementation() {
        val source = List(520) { i -> QuoteLine(localId = "q$i", designation = "Item $i", quantity = inputs[i % inputs.size], unitPrice = inputs[(i / inputs.size) % inputs.size]) }
        val expected = LegacyQuoteCalculator.recalculate(source)
        val actual = QuoteCalculator.recalculate(source)
        assertEquals(expected, actual)
        assertEquals(LegacyQuoteCalculator.total(expected), QuoteCalculator.total(actual))
    }
    @Test fun totalRowsAndFilteredSubtotalsMatchOldImplementation() {
        val source = List(520) { i -> TotalLine(localId = "t$i", date = "2026-09-${if (i % 2 == 0) "08" else "09"}", designation = if (i % 3 == 0) "Achat Tuyau" else "Tuyau", amountInput = inputs[i % inputs.size]) }
        val expected = LegacyTotalCalculator.recalculate(source)
        val actual = TotalCalculator.recalculate(source)
        assertEquals(expected, actual)
        for (mode in ComparisonMode.entries) for (name in listOf("", " TUYAU ", "achat")) for (date in listOf("", "2026-09-08", "missing")) {
            val criterion = FilterCriterion(localId = "filter", mode = mode, designation = name, date = date)
            assertEquals(LegacyTotalCalculator.result(expected, criterion), TotalCalculator.result(actual, criterion))
        }
    }
    @Test fun cashBalancesAndIndependentFilteredEntriesMatchOldImplementation() {
        val source = List(1020) { i -> CashLine(localId = "c$i", date = "2026-09-08", designation = if (i % 2 == 0) "Recette" else "Achat", entryInput = inputs[i % inputs.size], exitInput = inputs[(i + 2) % inputs.size]) }
        val expected = LegacyCashCalculator.recalculate(source)
        val actual = CashCalculator.recalculate(source)
        assertEquals(expected, actual)
        for (name in listOf("", "recette", "ACHAT", "missing")) {
            val criterion = FilterCriterion(localId = "filter", designation = name)
            val oldResult = LegacyCashCalculator.result(expected, criterion)
            val newResult = CashCalculator.result(actual, criterion)
            assertEquals(oldResult, newResult)
            assertEquals(oldResult.net, newResult.net)
        }
    }
    @Test fun emptyInputStillCreatesOneEditableZeroLine() {
        val quote = QuoteCalculator.recalculate(emptyList()).single()
        val total = TotalCalculator.recalculate(emptyList()).single()
        val cash = CashCalculator.recalculate(emptyList()).single()
        assertTrue(quote.localId.isNotBlank())
        assertTrue(total.localId.isNotBlank())
        assertTrue(cash.localId.isNotBlank())
        assertEquals(0, quote.amount!!.signum())
        assertEquals(0, total.amount!!.signum())
        assertEquals(0, cash.balance.signum())
    }
}
