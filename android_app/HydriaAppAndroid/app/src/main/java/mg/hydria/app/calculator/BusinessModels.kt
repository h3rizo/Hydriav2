package mg.hydria.app.calculator

import java.math.BigDecimal

/**
 * Relais fin vers le module partage `shared` (Phase 1 de la migration KMP).
 * Le code reel a demenage vers
 * shared/src/jvmCommonMain/kotlin/mg/hydria/shared/calculator/BusinessModels.kt.
 */
typealias QuoteLine = mg.hydria.shared.calculator.QuoteLine
typealias ComparisonMode = mg.hydria.shared.calculator.ComparisonMode
typealias TotalLine = mg.hydria.shared.calculator.TotalLine
typealias FilterCriterion = mg.hydria.shared.calculator.FilterCriterion
typealias TotalCriterionResult = mg.hydria.shared.calculator.TotalCriterionResult
typealias CashLine = mg.hydria.shared.calculator.CashLine
typealias CashCriterionResult = mg.hydria.shared.calculator.CashCriterionResult
typealias NamedCashBook = mg.hydria.shared.calculator.NamedCashBook

object DecimalInput {
    fun parse(value: String): BigDecimal? = mg.hydria.shared.calculator.DecimalInput.parse(value)
}

object QuoteCalculator {
    val MAX_LINES = mg.hydria.shared.calculator.QuoteCalculator.MAX_LINES
    fun recalculate(lines: List<QuoteLine>): List<QuoteLine> = mg.hydria.shared.calculator.QuoteCalculator.recalculate(lines)
    fun total(lines: List<QuoteLine>): BigDecimal = mg.hydria.shared.calculator.QuoteCalculator.total(lines)
}

object TotalCalculator {
    val MAX_LINES = mg.hydria.shared.calculator.TotalCalculator.MAX_LINES
    val MAX_CRITERIA = mg.hydria.shared.calculator.TotalCalculator.MAX_CRITERIA
    fun recalculate(lines: List<TotalLine>): List<TotalLine> = mg.hydria.shared.calculator.TotalCalculator.recalculate(lines)
    fun total(lines: List<TotalLine>): BigDecimal = mg.hydria.shared.calculator.TotalCalculator.total(lines)
    fun result(lines: List<TotalLine>, criterion: FilterCriterion): TotalCriterionResult =
        mg.hydria.shared.calculator.TotalCalculator.result(lines, criterion)
}

object CashCalculator {
    val MAX_LINES = mg.hydria.shared.calculator.CashCalculator.MAX_LINES
    val MAX_CRITERIA = mg.hydria.shared.calculator.CashCalculator.MAX_CRITERIA
    val MAX_BOOKS = mg.hydria.shared.calculator.CashCalculator.MAX_BOOKS
    val MAX_NAME_LENGTH = mg.hydria.shared.calculator.CashCalculator.MAX_NAME_LENGTH
    fun recalculate(lines: List<CashLine>): List<CashLine> = mg.hydria.shared.calculator.CashCalculator.recalculate(lines)
    fun result(lines: List<CashLine>, criterion: FilterCriterion): CashCriterionResult =
        mg.hydria.shared.calculator.CashCalculator.result(lines, criterion)
    fun normalizeBookName(value: String): String = mg.hydria.shared.calculator.CashCalculator.normalizeBookName(value)
}
