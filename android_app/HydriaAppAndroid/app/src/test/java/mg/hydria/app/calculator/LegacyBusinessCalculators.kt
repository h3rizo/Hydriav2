package mg.hydria.app.calculator

import mg.hydria.shared.calculator.*

import java.math.BigDecimal
import java.util.UUID

object LegacyDecimalInput {
    fun parse(value: String): BigDecimal? {
        val normalized = CalculatorTextRules.decimalText(value) ?: return null
        return runCatching { BigDecimal(normalized) }.getOrNull()
    }
}

object LegacyQuoteCalculator {
    const val MAX_LINES = 500

    fun recalculate(lines: List<QuoteLine>): List<QuoteLine> =
        lines.take(MAX_LINES).ifEmpty { listOf(QuoteLine()) }.map { line ->
            val quantity = LegacyDecimalInput.parse(line.quantity)
            val unitPrice = LegacyDecimalInput.parse(line.unitPrice)
            line.copy(amount = if (quantity != null && unitPrice != null) quantity.multiply(unitPrice) else null)
        }

    fun total(lines: List<QuoteLine>): BigDecimal = lines.fold(BigDecimal.ZERO) { total, line ->
        total.add(line.amount ?: BigDecimal.ZERO)
    }
}

object LegacyTotalCalculator {
    const val MAX_LINES = 500
    const val MAX_CRITERIA = 100

    fun recalculate(lines: List<TotalLine>): List<TotalLine> =
        lines.take(MAX_LINES).ifEmpty { listOf(TotalLine()) }.map { it.copy(amount = LegacyDecimalInput.parse(it.amountInput)) }

    fun total(lines: List<TotalLine>): BigDecimal = lines.fold(BigDecimal.ZERO) { result, line ->
        result.add(line.amount ?: BigDecimal.ZERO)
    }

    fun result(lines: List<TotalLine>, criterion: FilterCriterion): TotalCriterionResult {
        val matching = if (criterion.designation.isBlank() && criterion.date.isBlank()) lines else lines.filter { line ->
            matches(line.designation, line.date, criterion)
        }
        return TotalCriterionResult(criterion, total(matching))
    }

    internal fun matches(designation: String, date: String, criterion: FilterCriterion): Boolean =
        CalculatorTextRules.matches(designation, date, criterion.designation, criterion.date, criterion.mode == ComparisonMode.CONTAINS)

}

object LegacyCashCalculator {
    const val MAX_LINES = 1_000
    const val MAX_CRITERIA = 100
    const val MAX_BOOKS = 200
    const val MAX_NAME_LENGTH = 80

    fun recalculate(lines: List<CashLine>): List<CashLine> {
        var balance = BigDecimal.ZERO
        return lines.take(MAX_LINES).ifEmpty { listOf(CashLine()) }.map { line ->
            val entry = LegacyDecimalInput.parse(line.entryInput)
            val exit = LegacyDecimalInput.parse(line.exitInput)
            if (entry != null && exit != null) balance = balance.add(entry).subtract(exit)
            line.copy(entry = entry, exit = exit, balance = balance)
        }
    }

    fun result(lines: List<CashLine>, criterion: FilterCriterion): CashCriterionResult {
        val matching = if (criterion.designation.isBlank() && criterion.date.isBlank()) lines else lines.filter { line ->
            LegacyTotalCalculator.matches(line.designation, line.date, criterion)
        }
        val entries = matching.fold(BigDecimal.ZERO) { total, line -> total.add(line.entry ?: BigDecimal.ZERO) }
        val exits = matching.fold(BigDecimal.ZERO) { total, line -> total.add(line.exit ?: BigDecimal.ZERO) }
        return CashCriterionResult(criterion, entries, exits)
    }

    fun normalizeBookName(value: String): String = CalculatorTextRules.bookName(value, MAX_NAME_LENGTH)
}
