package mg.hydria.app.calculator

import mg.hydria.shared.calculator.CalculatorEngine
import mg.hydria.shared.calculator.ExpressionResult
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class CalculatorWorkbookCompatibilityTest {
    @Test fun chainedReferencesAndErrorsMatchLegacyRecalculation() {
        val source = List(1005) { i -> CalculationLine(localId = "line-$i", expression = when (i) {
            0 -> "0.1"
            10 -> "1/0"
            11 -> "L11"
            12 -> "L9999"
            13 -> "0.1"
            else -> "L$i+0.1"
        }) }
        val outputs = mutableListOf<ExpressionResult>()
        val bounded = source.take(1000)
        val legacy = LegacyDecimalExpressionParser()
        val expected = bounded.mapIndexed { index, line ->
            val output = legacy.evaluate(line.expression, index, bounded.size, outputs)
            outputs += output
            line.copy(result = output.value, error = output.error)
        }
        assertEquals(expected, CalculatorEngine.recalculate(source))
    }
    @Test fun storedDraftsIdsAndSchemaSurviveRoundTrip() {
        val state = CalculatorState(selectedTab = CalculatorTab.CASH, activeCalculationLine = 900,
            calculationLines = listOf(CalculationLine(localId = "calc", expression = "1,25+2")),
            quoteLines = listOf(QuoteLine(localId = "quote", quantity = "2", unitPrice = "3,5")),
            totalLines = listOf(TotalLine(localId = "total", amountInput = "9")),
            cashLines = listOf(CashLine(localId = "cash", entryInput = "10", exitInput = "1")),
            namedCashBooks = listOf(NamedCashBook(localId = "book", name = " Nord ", updatedAt = 123,
                lines = listOf(CashLine(localId = "book-line", entryInput = "4")), criteria = emptyList())),
            salaryDraft = SalaryDraft(target = "123456.789"), gpsDraft = GpsDraft(latitude = "-18.12345678", longitude = "47.12345678"))
        val normalized = state.normalized()
        val json = normalized.toJson()
        assertEquals(2, json.getInt("schema_version"))
        val restored = CalculatorState.fromJson(JSONObject(json.toString()))
        assertEquals(normalized, restored)
        assertEquals("book", restored.namedCashBooks.single().localId)
        assertEquals("Nord", restored.namedCashBooks.single().name)
        assertEquals(0, restored.activeCalculationLine)
        assertEquals("3.25", restored.calculationLines.single().result!!.toPlainString())
    }
    @Test fun malformedSavedSelectionUsesDefaultTabAndEditableLine() {
        val state = CalculatorState.fromJson(JSONObject("""{"selected_tab":"unknown","active_calculation_line":-8,"calculation_lines":[null,"bad"]}"""))
        assertEquals(CalculatorTab.CALCULATIONS, state.selectedTab)
        assertEquals(0, state.activeCalculationLine)
        assertEquals(1, state.calculationLines.size)
        assertTrue(state.calculationLines.single().localId.isNotBlank())
    }
}
