package mg.hydria.shared.calculator

import java.math.BigDecimal
import java.util.UUID

object DecimalInput {
    fun parse(value: String): BigDecimal? {
        val normalized = CalculatorTextRules.decimalText(value) ?: return null
        return runCatching { BigDecimal(normalized) }.getOrNull()
    }
}

private val businessCore = BusinessCalculationCore(object : BusinessArithmetic<BigDecimal> {
    override val zero = BigDecimal.ZERO
    override fun parse(text: String) = DecimalInput.parse(text)
    override fun add(left: BigDecimal, right: BigDecimal) = left.add(right)
    override fun subtract(left: BigDecimal, right: BigDecimal) = left.subtract(right)
    override fun multiply(left: BigDecimal, right: BigDecimal) = left.multiply(right)
})

data class QuoteLine(
    val localId: String = UUID.randomUUID().toString(),
    val designation: String = "",
    val quantity: String = "",
    val unitPrice: String = "",
    val amount: BigDecimal? = null,
)

object QuoteCalculator {
    const val MAX_LINES = BusinessCalculationCore.MAX_QUOTE_LINES
    fun recalculate(lines: List<QuoteLine>): List<QuoteLine> = businessCore.quotes(
        lines.ifEmpty { listOf(QuoteLine()) }.map { QuoteDraft(it, it.quantity, it.unitPrice) }
    ).map { it.item.copy(amount = it.amount) }
    fun total(lines: List<QuoteLine>): BigDecimal = businessCore.total(lines.map { it.amount })
}

enum class ComparisonMode { CONTAINS, EQUALS }

data class TotalLine(
    val localId: String = UUID.randomUUID().toString(),
    val date: String = "",
    val designation: String = "",
    val amountInput: String = "",
    val amount: BigDecimal? = null,
)

data class FilterCriterion(
    val localId: String = UUID.randomUUID().toString(),
    val mode: ComparisonMode = ComparisonMode.CONTAINS,
    val designation: String = "",
    val date: String = "",
)

data class TotalCriterionResult(val criterion: FilterCriterion, val subtotal: BigDecimal)

object TotalCalculator {
    const val MAX_LINES = BusinessCalculationCore.MAX_TOTAL_LINES
    const val MAX_CRITERIA = BusinessCalculationCore.MAX_CRITERIA
    fun recalculate(lines: List<TotalLine>): List<TotalLine> = businessCore.amounts(
        lines.ifEmpty { listOf(TotalLine()) }.map { AmountDraft(it, it.amountInput) }
    ).map { it.item.copy(amount = it.amount) }
    fun total(lines: List<TotalLine>): BigDecimal = businessCore.total(lines.map { it.amount })
    fun result(lines: List<TotalLine>, criterion: FilterCriterion): TotalCriterionResult {
        val matching = businessCore.matching(lines.map { BusinessFilterRow(it, it.designation, it.date) },
            criterion.designation, criterion.date, criterion.mode == ComparisonMode.CONTAINS)
        return TotalCriterionResult(criterion, total(matching))
    }
    internal fun matches(designation: String, date: String, criterion: FilterCriterion): Boolean =
        CalculatorTextRules.matches(designation, date, criterion.designation, criterion.date, criterion.mode == ComparisonMode.CONTAINS)
}

data class CashLine(
    val localId: String = UUID.randomUUID().toString(),
    val date: String = "",
    val designation: String = "",
    val entryInput: String = "",
    val exitInput: String = "",
    val reference: String = "",
    val entry: BigDecimal? = null,
    val exit: BigDecimal? = null,
    val balance: BigDecimal = BigDecimal.ZERO,
)

data class CashCriterionResult(
    val criterion: FilterCriterion,
    val entries: BigDecimal,
    val exits: BigDecimal,
) {
    val net: BigDecimal get() = entries.subtract(exits)
}

data class NamedCashBook(
    val localId: String = UUID.randomUUID().toString(),
    val name: String,
    val updatedAt: Long,
    val lines: List<CashLine>,
    val criteria: List<FilterCriterion>,
)

object CashCalculator {
    const val MAX_LINES = BusinessCalculationCore.MAX_CASH_LINES
    const val MAX_CRITERIA = BusinessCalculationCore.MAX_CRITERIA
    const val MAX_BOOKS = BusinessCalculationCore.MAX_BOOKS
    const val MAX_NAME_LENGTH = BusinessCalculationCore.MAX_NAME_LENGTH
    fun recalculate(lines: List<CashLine>): List<CashLine> = businessCore.cash(
        lines.ifEmpty { listOf(CashLine()) }.map { CashDraft(it, it.entryInput, it.exitInput) }
    ).map { it.item.copy(entry = it.entry, exit = it.exit, balance = it.balance) }
    fun result(lines: List<CashLine>, criterion: FilterCriterion): CashCriterionResult {
        val matching = businessCore.matching(lines.map { BusinessFilterRow(it, it.designation, it.date) },
            criterion.designation, criterion.date, criterion.mode == ComparisonMode.CONTAINS)
        return CashCriterionResult(criterion, businessCore.total(matching.map { it.entry }), businessCore.total(matching.map { it.exit }))
    }
    fun normalizeBookName(value: String): String = CalculatorTextRules.bookName(value, MAX_NAME_LENGTH)
}
