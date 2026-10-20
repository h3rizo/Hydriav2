package mg.hydria.shared.calculator

import kotlin.test.*

/** Small numeric adapter for grammar tests; production continues to use BigDecimal. */
class ExpressionCoreTest {
    private val core = ExpressionCore(object : DecimalArithmetic<Double> {
        override val hundred = 100.0
        override fun parse(value: String) = value.toDoubleOrNull()
        override fun add(left: Double, right: Double) = left + right
        override fun subtract(left: Double, right: Double) = left - right
        override fun multiply(left: Double, right: Double) = left * right
        override fun divide(left: Double, right: Double) = left / right
        override fun negate(value: Double) = -value
        override fun isZero(value: Double) = value == 0.0
        override fun exceedsLimit(value: Double) = kotlin.math.abs(value) > 1e100
        override fun normalize(value: Double) = value
    })
    private fun eval(text: String) = core.evaluate(text, 0, 1, emptyList())
    @Test fun operatorsPercentAndParentheses() {
        assertEquals(14.0, eval("2+3×4").value)
        assertEquals(10.0, eval("=(2+3)*200%").value)
        assertEquals(-0.5, eval("−,5").value)
        assertNull(eval(" ").value)
    }
    @Test fun percentAfterPlusOrMinusIsAShareOfTheLeftOperand() {
        // CALC_VOL-06 : « A + B% » = A × (1 + B/100), « A − B% » = A × (1 − B/100).
        assertEquals(300.0, eval("200 + 50%").value)
        assertEquals(150.0, eval("200 − 25%").value)
        assertEquals(150.0, eval("200 - 25%").value)
        assertEquals(120.0, eval("=80+50%").value)
        assertEquals(300.0, eval("(100+100)+50%").value)
        // Enchaînement lu de gauche à droite, comme sur une calculette : (200 + 50%) − 50% = 300 × 0,5.
        assertEquals(150.0, eval("200 + 50% − 50%").value)
        // Un pourcentage signé à droite reste un pourcentage de l'opérande gauche.
        assertEquals(100.0, eval("200 + -50%").value)
        assertEquals(300.0, eval("200 − -50%").value)
        // Avec une ligne de référence : L1 = 3 → 3 + 100% = 6.
        assertEquals(6.0, core.evaluate("L1 + 100%", 1, 2, listOf(ArithmeticResult(3.0))).value)
    }
    @Test fun percentKeepsItsMeaningOutsideAdditionAndSubtraction() {
        assertEquals(30.0, eval("200 × 15%").value!!, 1e-9)
        assertEquals(0.5, eval("50%").value)
        assertEquals(0.25, eval("25%").value)
        assertEquals(10.0, eval("(2+3)*200%").value)
        // Un pourcentage multiplié, ou à gauche d'un +, n'est pas un pourcentage de l'opérande gauche.
        assertEquals(100.5, eval("100 + 50% × 1").value)
        assertEquals(100.5, eval("50% + 100").value)
    }
    @Test fun grammarReportsPreciseErrors() {
        assertEquals(ExpressionError.DIVISION_BY_ZERO, eval("1÷0").error)
        assertEquals(ExpressionError.MISSING_CLOSING_PARENTHESIS, eval("(1+2").error)
        assertEquals(ExpressionError.INVALID_NUMBER, eval("1,2.3").error)
        assertEquals(ExpressionError.FORBIDDEN_CHARACTER, eval("print(1)").error)
        assertEquals(ExpressionError.INCOMPLETE_EXPRESSION, eval("2+").error)
    }
    @Test fun lineReferencesValidateOrderAndPreviousErrors() {
        assertEquals(6.0, core.evaluate("L1*2", 1, 2, listOf(ArithmeticResult(3.0))).value)
        assertEquals(ExpressionError.CURRENT_OR_FUTURE_REFERENCE, core.evaluate("L2", 1, 2, emptyList()).error)
        assertEquals(ExpressionError.MISSING_LINE, core.evaluate("L3", 1, 2, emptyList()).error)
        assertEquals(ExpressionError.LINE_HAS_ERROR, core.evaluate("L1", 1, 2, listOf(ArithmeticResult(error = ExpressionError.INVALID_NUMBER))).error)
        assertEquals(ExpressionError.LINE_NO_RESULT, core.evaluate("L1", 1, 2, listOf(ArithmeticResult())).error)
    }
}
