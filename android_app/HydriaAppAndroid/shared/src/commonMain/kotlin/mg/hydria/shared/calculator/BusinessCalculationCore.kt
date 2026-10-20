package mg.hydria.shared.calculator

/** Opérations exactes, sans le contexte d'arrondi du parseur d'expressions. */
interface BusinessArithmetic<N> {
    val zero: N
    fun parse(text: String): N?
    fun add(left: N, right: N): N
    fun subtract(left: N, right: N): N
    fun multiply(left: N, right: N): N
}
data class QuoteDraft<T>(val item: T, val quantity: String, val price: String)
data class AmountDraft<T>(val item: T, val input: String)
data class ComputedAmount<T, N>(val item: T, val amount: N?)
data class CashDraft<T>(val item: T, val entry: String, val exit: String)
data class ComputedCash<T, N>(val item: T, val entry: N?, val exit: N?, val balance: N)
data class BusinessFilterRow<T>(val item: T, val designation: String, val date: String)

class BusinessCalculationCore<N>(private val arithmetic: BusinessArithmetic<N>) {
    fun <T> quotes(lines: List<QuoteDraft<T>>): List<ComputedAmount<T, N>> = lines.take(MAX_QUOTE_LINES).map {
        val quantity = arithmetic.parse(it.quantity)
        val price = arithmetic.parse(it.price)
        ComputedAmount(it.item, if (quantity != null && price != null) arithmetic.multiply(quantity, price) else null)
    }
    fun <T> amounts(lines: List<AmountDraft<T>>): List<ComputedAmount<T, N>> =
        lines.take(MAX_TOTAL_LINES).map { ComputedAmount(it.item, arithmetic.parse(it.input)) }
    fun total(amounts: List<N?>): N = amounts.fold(arithmetic.zero) { total, value -> arithmetic.add(total, value ?: arithmetic.zero) }
    fun <T> cash(lines: List<CashDraft<T>>): List<ComputedCash<T, N>> {
        var balance = arithmetic.zero
        return lines.take(MAX_CASH_LINES).map {
            val entry = arithmetic.parse(it.entry)
            val exit = arithmetic.parse(it.exit)
            if (entry != null && exit != null) balance = arithmetic.subtract(arithmetic.add(balance, entry), exit)
            ComputedCash(it.item, entry, exit, balance)
        }
    }
    fun <T> matching(rows: List<BusinessFilterRow<T>>, designation: String, date: String, contains: Boolean): List<T> =
        rows.filter { CalculatorTextRules.matches(it.designation, it.date, designation, date, contains) }.map { it.item }

    companion object {
        const val MAX_QUOTE_LINES = 500
        const val MAX_TOTAL_LINES = 500
        const val MAX_CASH_LINES = 1000
        const val MAX_CRITERIA = 100
        const val MAX_BOOKS = 200
        const val MAX_NAME_LENGTH = 80
    }
}
