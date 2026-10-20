package mg.hydria.app.calculator

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.math.BigDecimal

class DecimalExpressionParserTest {
    private val parser = DecimalExpressionParser()

    @Test fun decimalCommaAndMultiplicationAreSupported() {
        assertDecimal("37.5", parser.evaluate("12,5 × 3", 0, 1, emptyList()).value)
    }

    @Test fun precedenceParenthesesUnaryAndPercentageAreSupported() {
        assertDecimal("-18", parser.evaluate("-(2 + 3) * 4 + 10% × 20", 0, 1, emptyList()).value)
    }

    @Test fun percentAfterPlusOrMinusIsAShareOfTheLeftOperand() {
        // CALC_VOL-06 : avant, « 18500 + 7% » donnait 18 500,07.
        assertDecimal("19795", parser.evaluate("18500 + 7%", 0, 1, emptyList()).value)
        assertDecimal("5350", parser.evaluate("5000 + 7%", 0, 1, emptyList()).value)
        assertDecimal("108000", parser.evaluate("120000 − 10%", 0, 1, emptyList()).value)
        assertDecimal("108000", parser.evaluate("120000 - 10%", 0, 1, emptyList()).value)
        assertDecimal("11.25", parser.evaluate("10 + 12,5%", 0, 1, emptyList()).value)
    }

    @Test fun percentKeepsItsMeaningElsewhere() {
        assertDecimal("30", parser.evaluate("200 × 15%", 0, 1, emptyList()).value)
        assertDecimal("0.5", parser.evaluate("50%", 0, 1, emptyList()).value)
        assertDecimal("10", parser.evaluate("(2+3)*200%", 0, 1, emptyList()).value)
        assertDecimal("-18", parser.evaluate("-(2 + 3) * 4 + 10% × 20", 0, 1, emptyList()).value)
    }

    @Test fun previousLineReferencesCascade() {
        val rows = CalculatorEngine.recalculate(listOf(
            CalculationLine(expression = "12500 × 3"),
            CalculationLine(expression = "L1 + (L1 × 10%)"),
            CalculationLine(expression = "L2 - L1"),
        ))
        assertDecimal("37500", rows[0].result)
        assertDecimal("41250", rows[1].result)
        assertDecimal("3750", rows[2].result)
    }

    @Test fun editingPreviousLineRecalculatesFollowingLines() {
        val initial = CalculatorEngine.recalculate(listOf(
            CalculationLine(expression = "10"), CalculationLine(expression = "L1 × 2"),
        ))
        val changed = CalculatorEngine.recalculate(initial.mapIndexed { index, row -> if (index == 0) row.copy(expression = "12") else row })
        assertDecimal("24", changed[1].result)
    }

    @Test fun currentFutureAndMissingReferencesAreRejected() {
        assertEquals(ExpressionError.CURRENT_OR_FUTURE_REFERENCE, parser.evaluate("L1", 0, 2, emptyList()).error)
        assertEquals(ExpressionError.CURRENT_OR_FUTURE_REFERENCE, parser.evaluate("L2", 0, 2, emptyList()).error)
        assertEquals(ExpressionError.MISSING_LINE, parser.evaluate("L3", 1, 2, listOf(ExpressionResult(BigDecimal.ONE))).error)
    }

    @Test fun referencedErrorAndMissingResultAreRejected() {
        assertEquals(ExpressionError.LINE_HAS_ERROR, parser.evaluate("L1", 1, 2, listOf(ExpressionResult(error = ExpressionError.INVALID_NUMBER))).error)
        assertEquals(ExpressionError.LINE_NO_RESULT, parser.evaluate("L1", 1, 2, listOf(ExpressionResult())).error)
    }

    @Test fun unsafeAndIncompleteExpressionsAreRejected() {
        assertEquals(ExpressionError.DIVISION_BY_ZERO, parser.evaluate("10 / 0", 0, 1, emptyList()).error)
        assertEquals(ExpressionError.FORBIDDEN_CHARACTER, parser.evaluate("System.exit(0)", 0, 1, emptyList()).error)
        assertEquals(ExpressionError.INCOMPLETE_EXPRESSION, parser.evaluate("1 +", 0, 1, emptyList()).error)
        assertEquals(ExpressionError.MISSING_CLOSING_PARENTHESIS, parser.evaluate("(1 + 2", 0, 1, emptyList()).error)
    }

    @Test fun leadingEqualsIsIgnored() {
        val output = parser.evaluate("= 2 + 3", 0, 1, emptyList())
        assertNull(output.error)
        assertDecimal("5", output.value)
    }

    private fun assertDecimal(expected: String, actual: BigDecimal?) =
        assertEquals(0, BigDecimal(expected).compareTo(requireNotNull(actual)))
}
