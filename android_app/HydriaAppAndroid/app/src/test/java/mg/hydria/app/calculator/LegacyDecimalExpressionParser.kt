package mg.hydria.app.calculator

import mg.hydria.shared.calculator.ExpressionError
import mg.hydria.shared.calculator.ExpressionResult

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode

/** Parseur arithmetique ferme. Il n'execute jamais de code arbitraire. */
internal class LegacyDecimalExpressionParser(
    private val mathContext: MathContext = MathContext(24, RoundingMode.HALF_UP),
) {
    fun evaluate(
        expression: String,
        currentLineIndex: Int,
        totalLineCount: Int,
        previousResults: List<ExpressionResult>,
    ): ExpressionResult {
        val source = expression.trim().removePrefix("=").trim()
        if (source.isEmpty()) return ExpressionResult()
        return try {
            val parser = Parser(source, currentLineIndex, totalLineCount, previousResults)
            val value = parser.parseExpression()
            parser.skipSpaces()
            if (!parser.isAtEnd()) parser.fail(ExpressionError.FORBIDDEN_CHARACTER)
            if (value.abs() > MAX_ABSOLUTE_RESULT) parser.fail(ExpressionError.RESULT_TOO_LARGE)
            ExpressionResult(value.stripTrailingZeros())
        } catch (error: ParseFailure) {
            ExpressionResult(error = error.error)
        } catch (_: ArithmeticException) {
            ExpressionResult(error = ExpressionError.NON_NUMERIC)
        }
    }

    private inner class Parser(
        private val source: String,
        private val currentLineIndex: Int,
        private val totalLineCount: Int,
        private val previousResults: List<ExpressionResult>,
    ) {
        private var position = 0

        fun parseExpression(): BigDecimal {
            var value = parseTerm()
            while (true) {
                skipSpaces()
                value = when {
                    take('+') -> value.add(parseTerm(), mathContext)
                    take('-') || take('−') -> value.subtract(parseTerm(), mathContext)
                    else -> return value
                }
            }
        }

        private fun parseTerm(): BigDecimal {
            var value = parseUnary()
            while (true) {
                skipSpaces()
                value = when {
                    take('*') || take('×') -> value.multiply(parseUnary(), mathContext)
                    take('/') || take('÷') -> {
                        val divisor = parseUnary()
                        if (divisor.compareTo(BigDecimal.ZERO) == 0) fail(ExpressionError.DIVISION_BY_ZERO)
                        value.divide(divisor, mathContext)
                    }
                    else -> return value
                }
            }
        }

        private fun parseUnary(): BigDecimal {
            skipSpaces()
            return when {
                take('+') -> parseUnary()
                take('-') || take('−') -> parseUnary().negate(mathContext)
                else -> parsePostfix()
            }
        }

        private fun parsePostfix(): BigDecimal {
            var value = parsePrimary()
            skipSpaces()
            while (take('%')) {
                value = value.divide(ONE_HUNDRED, mathContext)
                skipSpaces()
            }
            return value
        }

        private fun parsePrimary(): BigDecimal {
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

        private fun parseNumber(): BigDecimal {
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
            return normalized.toBigDecimalOrNull()?.round(mathContext) ?: fail(ExpressionError.INVALID_NUMBER)
        }

        private fun parseReference(): BigDecimal {
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

    companion object {
        private val ONE_HUNDRED = BigDecimal("100")
        private val MAX_ABSOLUTE_RESULT = BigDecimal("1E100")
    }
}
