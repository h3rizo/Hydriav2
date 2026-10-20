package mg.hydria.shared.calculator

enum class ExpressionError {
    INVALID_REFERENCE, MISSING_LINE, CURRENT_OR_FUTURE_REFERENCE, LINE_HAS_ERROR,
    LINE_NO_RESULT, DIVISION_BY_ZERO, NON_NUMERIC, INCOMPLETE_EXPRESSION,
    MISSING_CLOSING_PARENTHESIS, INVALID_NUMBER, FORBIDDEN_CHARACTER, RESULT_TOO_LARGE,
}

data class ArithmeticResult<N>(val value: N? = null, val error: ExpressionError? = null)

/** L'adaptateur fournit les opérations avec leur précision et leur arrondi. */
interface DecimalArithmetic<N> {
    val hundred: N
    fun parse(value: String): N?
    fun add(left: N, right: N): N
    fun subtract(left: N, right: N): N
    fun multiply(left: N, right: N): N
    fun divide(left: N, right: N): N
    fun negate(value: N): N
    fun isZero(value: N): Boolean
    fun exceedsLimit(value: N): Boolean
    fun normalize(value: N): N
}

/** Parseur arithmetique ferme. Il n'execute jamais de code arbitraire. */
class ExpressionCore<N>(private val arithmetic: DecimalArithmetic<N>) {
    fun evaluate(
        expression: String,
        currentLineIndex: Int,
        totalLineCount: Int,
        previousResults: List<ArithmeticResult<N>>,
    ): ArithmeticResult<N> {
        val source = expression.trim().removePrefix("=").trim()
        if (source.isEmpty()) return ArithmeticResult()
        return try {
            val parser = Parser(source, currentLineIndex, totalLineCount, previousResults)
            val value = parser.parseExpression()
            parser.skipSpaces()
            if (!parser.isAtEnd()) parser.fail(ExpressionError.FORBIDDEN_CHARACTER)
            if (arithmetic.exceedsLimit(value)) parser.fail(ExpressionError.RESULT_TOO_LARGE)
            ArithmeticResult(arithmetic.normalize(value))
        } catch (error: ParseFailure) {
            ArithmeticResult(error = error.error)
        } catch (_: ArithmeticException) {
            ArithmeticResult(error = ExpressionError.NON_NUMERIC)
        }
    }

    private inner class Parser(
        private val source: String,
        private val currentLineIndex: Int,
        private val totalLineCount: Int,
        private val previousResults: List<ArithmeticResult<N>>,
    ) {
        private var position = 0

        fun parseExpression(): N {
            var value = parseTerm().value
            while (true) {
                skipSpaces()
                value = when {
                    take('+') -> addPart(value, parseTerm(), subtract = false)
                    take('-') || take('−') -> addPart(value, parseTerm(), subtract = true)
                    else -> return value
                }
            }
        }

        /**
         * « A + B% » vaut A × (1 + B/100) et « A − B% » vaut A × (1 − B/100) (CALC_VOL-06) : c'est la
         * lecture d'une calculette. Seul un pourcentage pur à droite d'un + ou d'un − est concerné ;
         * ailleurs « % » garde son sens (« 200 × 15% » = 30, « 50% » seul = 0,5).
         */
        private fun addPart(left: N, right: Operand<N>, subtract: Boolean): N {
            val part = if (right.percent) arithmetic.multiply(left, right.value) else right.value
            return if (subtract) arithmetic.subtract(left, part) else arithmetic.add(left, part)
        }

        private fun parseTerm(): Operand<N> {
            var operand = parseUnary()
            while (true) {
                skipSpaces()
                operand = when {
                    take('*') || take('×') -> Operand(arithmetic.multiply(operand.value, parseUnary().value))
                    take('/') || take('÷') -> {
                        val divisor = parseUnary().value
                        if (arithmetic.isZero(divisor)) fail(ExpressionError.DIVISION_BY_ZERO)
                        Operand(arithmetic.divide(operand.value, divisor))
                    }
                    else -> return operand
                }
            }
        }

        private fun parseUnary(): Operand<N> {
            skipSpaces()
            return when {
                take('+') -> parseUnary()
                take('-') || take('−') -> parseUnary().let { Operand(arithmetic.negate(it.value), it.percent) }
                else -> parsePostfix()
            }
        }

        private fun parsePostfix(): Operand<N> {
            var value = parsePrimary()
            var percent = false
            skipSpaces()
            while (take('%')) {
                value = arithmetic.divide(value, arithmetic.hundred)
                percent = true
                skipSpaces()
            }
            return Operand(value, percent)
        }

        private fun parsePrimary(): N {
            skipSpaces()
            if (isAtEnd()) fail(ExpressionError.INCOMPLETE_EXPRESSION)
            if (take('(')) {
                val value = parseExpression()
                skipSpaces()
                if (!take(')')) fail(ExpressionError.MISSING_CLOSING_PARENTHESIS)
                return value
            }
            if (peek().equals('L', ignoreCase = true)) return parseReference()
            if (peek().isDigit() || peek() == '.' || peek() == ',') return parseNumber()
            fail(ExpressionError.FORBIDDEN_CHARACTER)
        }

        private fun parseNumber(): N {
            val start = position
            var separatorSeen = false
            var digitSeen = false
            while (!isAtEnd()) {
                val char = peek()
                when {
                    char.isDigit() -> { digitSeen = true; position++ }
                    char == '.' || char == ',' -> {
                        if (separatorSeen) fail(ExpressionError.INVALID_NUMBER)
                        separatorSeen = true
                        position++
                    }
                    else -> break
                }
            }
            if (!digitSeen) fail(ExpressionError.INVALID_NUMBER)
            val normalized = source.substring(start, position).replace(',', '.')
            return arithmetic.parse(normalized) ?: fail(ExpressionError.INVALID_NUMBER)
        }

        private fun parseReference(): N {
            position++
            val start = position
            while (!isAtEnd() && peek().isDigit()) position++
            if (start == position) fail(ExpressionError.INVALID_REFERENCE)
            val lineNumber = source.substring(start, position).toIntOrNull()
                ?: fail(ExpressionError.INVALID_REFERENCE)
            if (lineNumber <= 0) fail(ExpressionError.INVALID_REFERENCE)
            val referencedIndex = lineNumber - 1
            if (referencedIndex >= totalLineCount) fail(ExpressionError.MISSING_LINE)
            if (referencedIndex >= currentLineIndex) fail(ExpressionError.CURRENT_OR_FUTURE_REFERENCE)
            val result = previousResults.getOrNull(referencedIndex)
                ?: fail(ExpressionError.LINE_NO_RESULT)
            if (result.error != null) fail(ExpressionError.LINE_HAS_ERROR)
            return result.value ?: fail(ExpressionError.LINE_NO_RESULT)
        }

        fun skipSpaces() { while (!isAtEnd() && peek().isWhitespace()) position++ }
        fun isAtEnd() = position >= source.length
        private fun peek() = source[position]
        private fun take(expected: Char): Boolean {
            if (!isAtEnd() && source[position] == expected) { position++; return true }
            return false
        }
        fun fail(error: ExpressionError): Nothing = throw ParseFailure(error)
    }

    private class ParseFailure(val error: ExpressionError) : RuntimeException(error.name)

    /** Valeur d'un opérande ; [percent] = il se termine par « % » (valeur déjà divisée par 100) sans autre opération. */
    private class Operand<N>(val value: N, val percent: Boolean = false)

}
