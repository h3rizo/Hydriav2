package mg.hydria.shared.calculator

enum class CalculatorTab { CALCULATIONS, SALARY, QUOTE, TOTAL, CASH, GPS }
data class CalculationDraft<T>(val item: T, val expression: String)
data class ComputedCalculation<T, N>(val item: T, val value: N?, val error: ExpressionError?)

object CalculatorStateRules {
    const val MAX_CALCULATION_LINES = 1000
    const val MAX_EXPRESSION_LENGTH = 2000
    fun tab(name: String): CalculatorTab = CalculatorTab.entries.firstOrNull { it.name == name } ?: CalculatorTab.CALCULATIONS
    fun activeLine(index: Int, count: Int): Int = index.coerceIn(0, (count - 1).coerceAtLeast(0))
    fun <T> calculationLines(lines: List<T>, emptyLine: () -> T): List<T> =
        lines.take(MAX_CALCULATION_LINES).ifEmpty { listOf(emptyLine()) }
    fun <T> cashBooks(books: List<T>, normalize: (T) -> T, name: (T) -> String): List<T> =
        books.take(BusinessCalculationCore.MAX_BOOKS).map(normalize)
            .filter { name(it).isNotBlank() }.sortedBy { name(it).lowercase() }
}

/** Recalcule les lignes dans l'ordre ; seules les lignes précédentes sont accessibles. */
class CalculatorWorkbookCore<N>(private val evaluate: (String, Int, Int, List<ArithmeticResult<N>>) -> ArithmeticResult<N>) {
    fun <T> recalculate(lines: List<CalculationDraft<T>>, emptyLine: () -> CalculationDraft<T>): List<ComputedCalculation<T, N>> {
        val bounded = CalculatorStateRules.calculationLines(lines, emptyLine)
        val outputs = mutableListOf<ArithmeticResult<N>>()
        return bounded.mapIndexed { index, line ->
            val output = evaluate(line.expression, index, bounded.size, outputs)
            outputs += output
            ComputedCalculation(line.item, output.value, output.error)
        }
    }
}
