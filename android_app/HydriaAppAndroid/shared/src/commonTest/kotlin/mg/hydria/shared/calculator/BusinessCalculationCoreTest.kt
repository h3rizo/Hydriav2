package mg.hydria.shared.calculator

import kotlin.test.*

class BusinessCalculationCoreTest {
    private val core = BusinessCalculationCore(object : BusinessArithmetic<Long> {
        override val zero = 0L
        override fun parse(text: String): Long? = if (text.isBlank()) 0L else text.toLongOrNull()
        override fun add(left: Long, right: Long) = left + right
        override fun subtract(left: Long, right: Long) = left - right
        override fun multiply(left: Long, right: Long) = left * right
    })
    @Test fun quoteKeepsInvalidAmountAndTotalsOnlyValidValues() {
        val rows = core.quotes(listOf(QuoteDraft("a", "3", "5"), QuoteDraft("b", "bad", "7"), QuoteDraft("c", "", "8")))
        assertEquals(listOf(15L, null, 0L), rows.map { it.amount })
        assertEquals(15L, core.total(rows.map { it.amount }))
    }
    @Test fun cashInvalidLineDoesNotChangeRunningBalance() {
        val rows = core.cash(listOf(CashDraft("a", "10", "2"), CashDraft("b", "5", "bad"), CashDraft("c", "1", "3")))
        assertEquals(listOf(8L, 8L, 6L), rows.map { it.balance })
        assertEquals(5L, rows[1].entry)
        assertNull(rows[1].exit)
    }
    @Test fun limitsAndOrderArePreserved() {
        assertEquals(500, core.quotes(List(501) { QuoteDraft(it, "1", "2") }).size)
        assertEquals(500, core.amounts(List(501) { AmountDraft(it, "1") }).size)
        val cash = core.cash(List(1001) { CashDraft(it, "1", "") })
        assertEquals(1000, cash.size)
        assertEquals(999, cash.last().item)
        assertEquals(1000L, cash.last().balance)
    }
    @Test fun filtersCombineDesignationAndDateWithoutReordering() {
        val rows = listOf(BusinessFilterRow(1, "Achat tuyau", "2026-09-08"), BusinessFilterRow(2, "Tuyau", "2026-09-09"))
        assertEquals(listOf(1), core.matching(rows, "TUYAU", "2026-09-08", true))
        assertEquals(listOf(2), core.matching(rows, "tuyau", "", false))
        assertEquals(listOf(1, 2), core.matching(rows, "", "", false))
    }
    @Test fun emptyAndInvalidTotalsRemainZero() {
        assertEquals(0L, core.total(emptyList()))
        assertEquals(0L, core.total(listOf(null, null)))
    }
}
