package mg.hydria.app.calculator

import mg.hydria.shared.calculator.DecimalExpressionParser
import mg.hydria.shared.calculator.ExpressionError
import mg.hydria.shared.calculator.ExpressionResult
import org.junit.Assert.*
import org.junit.Test
import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode
import kotlin.random.Random

class ExpressionMigrationCompatibilityTest {
    private fun compare(expression: String, context: MathContext, previous: List<ExpressionResult> = emptyList(), current: Int = 0, count: Int = 1) {
        val expected = LegacyDecimalExpressionParser(context).evaluate(expression, current, count, previous)
        val actual = DecimalExpressionParser(context).evaluate(expression, current, count, previous)
        assertEquals("error: $expression, $context", expected.error, actual.error)
        assertEquals("exact decimal: $expression, $context", expected.value, actual.value)
    }
    @Test fun exactResultsMatchOldParserAcrossExpressionsAndRoundingModes() {
        val random = Random(20260908)
        val generated = List(300) {
            val a = random.nextInt(-10000, 10000)
            val b = random.nextInt(1, 99)
            val c = random.nextInt(-100, 100)
            "($a/$b + $c,25) * 12.345678901234567890123456789%"
        }
        val cases = generated + listOf("0.1+0.2", "1/3", "1/7*7", "99999999999999999999999999+1", "100%%", "", "=", "(2+3", "L0", "Lx", "1/0", "1.2.3", "2+", "1E3", "9".repeat(110))
        for (context in listOf(MathContext(24, RoundingMode.HALF_UP), MathContext.DECIMAL64, MathContext(8, RoundingMode.DOWN), MathContext.UNLIMITED))
            cases.forEach { compare(it, context) }
    }
    @Test fun lineReferenceResultsAndErrorsMatchOldParser() {
        val previous = listOf(ExpressionResult(BigDecimal("123.4500")), ExpressionResult(error = ExpressionError.DIVISION_BY_ZERO), ExpressionResult())
        for (expression in listOf("L1", "l1*2", "L2", "L3", "L4", "L5", "L9999999999999999999", "L1+L2"))
            compare(expression, MathContext(24, RoundingMode.HALF_UP), previous, 3, 4)
    }
}
