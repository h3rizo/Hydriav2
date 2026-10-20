package mg.hydria.shared.calculator

import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal
import java.util.UUID


data class CalculationLine(
    val localId: String = UUID.randomUUID().toString(),
    val label: String = "",
    val expression: String = "",
    val result: BigDecimal? = null,
    val error: ExpressionError? = null,
)

data class CalculatorState(
    val selectedTab: CalculatorTab = CalculatorTab.CALCULATIONS,
    val activeCalculationLine: Int = 0,
    val calculationLines: List<CalculationLine> = listOf(CalculationLine()),
    val quoteLines: List<QuoteLine> = listOf(QuoteLine()),
    val totalLines: List<TotalLine> = listOf(TotalLine()),
    val totalCriteria: List<FilterCriterion> = emptyList(),
    val cashLines: List<CashLine> = listOf(CashLine()),
    val cashCriteria: List<FilterCriterion> = emptyList(),
    val namedCashBooks: List<NamedCashBook> = emptyList(),
    val salaryDraft: SalaryDraft = SalaryDraft(),
    val gpsDraft: GpsDraft = GpsDraft(),
) {
    fun normalized(): CalculatorState {
        val lines = CalculatorStateRules.calculationLines(calculationLines) { CalculationLine() }
        return copy(
            activeCalculationLine = CalculatorStateRules.activeLine(activeCalculationLine, lines.size),
            calculationLines = CalculatorEngine.recalculate(lines),
            quoteLines = QuoteCalculator.recalculate(quoteLines),
            totalLines = TotalCalculator.recalculate(totalLines),
            totalCriteria = totalCriteria.take(TotalCalculator.MAX_CRITERIA),
            cashLines = CashCalculator.recalculate(cashLines),
            cashCriteria = cashCriteria.take(CashCalculator.MAX_CRITERIA),
            namedCashBooks = CalculatorStateRules.cashBooks(namedCashBooks, normalize = { book ->
                book.copy(
                    name = CashCalculator.normalizeBookName(book.name),
                    lines = CashCalculator.recalculate(book.lines),
                    criteria = book.criteria.take(CashCalculator.MAX_CRITERIA),
                )
            }, name = { it.name }),
        )
    }

    fun toJson(): JSONObject = JSONObject()
        .put("schema_version", SCHEMA_VERSION)
        .put("selected_tab", selectedTab.name)
        .put("active_calculation_line", activeCalculationLine)
        .put("calculation_lines", JSONArray().apply {
            calculationLines.take(MAX_CALCULATION_LINES).forEach { line ->
                put(JSONObject()
                    .put("local_id", line.localId)
                    .put("label", line.label.take(200))
                    .put("expression", line.expression.take(MAX_EXPRESSION_LENGTH)))
            }
        })
        .put("quote_lines", JSONArray().apply { quoteLines.take(QuoteCalculator.MAX_LINES).forEach { put(it.toJson()) } })
        .put("total_lines", JSONArray().apply { totalLines.take(TotalCalculator.MAX_LINES).forEach { put(it.toJson()) } })
        .put("total_criteria", JSONArray().apply { totalCriteria.take(TotalCalculator.MAX_CRITERIA).forEach { put(it.toJson()) } })
        .put("cash_lines", JSONArray().apply { cashLines.take(CashCalculator.MAX_LINES).forEach { put(it.toJson()) } })
        .put("cash_criteria", JSONArray().apply { cashCriteria.take(CashCalculator.MAX_CRITERIA).forEach { put(it.toJson()) } })
        .put("named_cash_books", JSONArray().apply {
            namedCashBooks.take(CashCalculator.MAX_BOOKS).forEach { book ->
                put(JSONObject()
                    .put("local_id", book.localId)
                    .put("name", book.name)
                    .put("updated_at", book.updatedAt)
                    .put("lines", JSONArray().apply { book.lines.take(CashCalculator.MAX_LINES).forEach { put(it.toJson()) } })
                    .put("criteria", JSONArray().apply { book.criteria.take(CashCalculator.MAX_CRITERIA).forEach { put(it.toJson()) } }))
            }
        })
        .put("salary_draft", salaryDraft.toJson())
        .put("gps_draft", gpsDraft.toJson())

    companion object {
        const val SCHEMA_VERSION = 2
        const val MAX_CALCULATION_LINES = CalculatorStateRules.MAX_CALCULATION_LINES
        const val MAX_EXPRESSION_LENGTH = CalculatorStateRules.MAX_EXPRESSION_LENGTH

        fun fromJson(json: JSONObject?): CalculatorState {
            if (json == null) return CalculatorState()
            val rows = json.optJSONArray("calculation_lines") ?: JSONArray()
            val lines = buildList {
                for (index in 0 until minOf(rows.length(), MAX_CALCULATION_LINES)) {
                    val row = rows.optJSONObject(index) ?: continue
                    add(CalculationLine(
                        localId = row.optString("local_id").ifBlank { UUID.randomUUID().toString() },
                        label = row.optString("label").take(200),
                        expression = row.optString("expression").take(MAX_EXPRESSION_LENGTH),
                    ))
                }
            }
            return CalculatorState(
                selectedTab = CalculatorStateRules.tab(json.optString("selected_tab")),
                activeCalculationLine = json.optInt("active_calculation_line", 0),
                calculationLines = lines,
                quoteLines = json.optJSONArray("quote_lines").quoteLines(),
                totalLines = json.optJSONArray("total_lines").totalLines(),
                totalCriteria = json.optJSONArray("total_criteria").criteria(TotalCalculator.MAX_CRITERIA),
                cashLines = json.optJSONArray("cash_lines").cashLines(),
                cashCriteria = json.optJSONArray("cash_criteria").criteria(CashCalculator.MAX_CRITERIA),
                namedCashBooks = json.optJSONArray("named_cash_books").cashBooks(),
                salaryDraft = json.optJSONObject("salary_draft").salaryDraft(),
                gpsDraft = json.optJSONObject("gps_draft").gpsDraft(),
            ).normalized()
        }

        private fun QuoteLine.toJson() = JSONObject()
            .put("local_id", localId).put("designation", designation).put("quantity", quantity).put("unit_price", unitPrice)

        private fun TotalLine.toJson() = JSONObject()
            .put("local_id", localId).put("date", date).put("designation", designation).put("amount", amountInput)

        private fun CashLine.toJson() = JSONObject()
            .put("local_id", localId).put("date", date).put("designation", designation)
            .put("entry", entryInput).put("exit", exitInput).put("reference", reference)

        private fun FilterCriterion.toJson() = JSONObject()
            .put("local_id", localId).put("mode", mode.name).put("designation", designation).put("date", date)

        private fun SalaryDraft.toJson() = JSONObject()
            .put("basis", basis.name).put("mode", mode.name).put("target", target).put("dependents", dependents).put("days", days)
            .put("night_hours", nightHours).put("sunday_hours", sundayHours).put("official_holiday_hours", officialHolidayHours)
            .put("decree_paid_holiday_hours", decreePaidHolidayHours).put("may_first_hours", mayFirstHours)
            .put("replacement_hours", replacementHours).put("ordinary_replacement_hours", ordinaryReplacementHours)

        private fun GpsDraft.toJson() = JSONObject()
            .put("dms_input", dmsInput).put("latitude_input", latitudeInput).put("longitude_input", longitudeInput)
            .put("latitude", latitude).put("longitude", longitude).put("updated_at", updatedAt)

        private fun JSONArray?.quoteLines(): List<QuoteLine> = objects(QuoteCalculator.MAX_LINES) { row ->
            QuoteLine(row.id(), row.optString("designation"), row.optString("quantity"), row.optString("unit_price"))
        }

        private fun JSONArray?.totalLines(): List<TotalLine> = objects(TotalCalculator.MAX_LINES) { row ->
            TotalLine(row.id(), row.optString("date"), row.optString("designation"), row.optString("amount"))
        }

        private fun JSONArray?.cashLines(): List<CashLine> = objects(CashCalculator.MAX_LINES) { row ->
            CashLine(row.id(), row.optString("date"), row.optString("designation"), row.optString("entry"), row.optString("exit"), row.optString("reference"))
        }

        private fun JSONArray?.criteria(maximum: Int): List<FilterCriterion> = objects(maximum) { row ->
            FilterCriterion(
                row.id(),
                runCatching { ComparisonMode.valueOf(row.optString("mode")) }.getOrDefault(ComparisonMode.CONTAINS),
                row.optString("designation"),
                row.optString("date"),
            )
        }

        private fun JSONArray?.cashBooks(): List<NamedCashBook> = objects(CashCalculator.MAX_BOOKS) { row ->
            NamedCashBook(
                localId = row.id(),
                name = row.optString("name"),
                updatedAt = row.optLong("updated_at"),
                lines = row.optJSONArray("lines").cashLines(),
                criteria = row.optJSONArray("criteria").criteria(CashCalculator.MAX_CRITERIA),
            )
        }

        private fun JSONObject?.salaryDraft(): SalaryDraft {
            if (this == null) return SalaryDraft()
            return SalaryDraft(
                basis = runCatching { SalaryBasis.valueOf(optString("basis")) }.getOrDefault(SalaryBasis.NET),
                mode = runCatching { SalaryMode.valueOf(optString("mode")) }.getOrDefault(SalaryMode.STANDARD),
                target = optString("target"), dependents = optString("dependents", "0"), days = optString("days"),
                nightHours = optString("night_hours", "56"), sundayHours = optString("sunday_hours"),
                officialHolidayHours = optString("official_holiday_hours"), decreePaidHolidayHours = optString("decree_paid_holiday_hours"),
                mayFirstHours = optString("may_first_hours"), replacementHours = optString("replacement_hours"),
                ordinaryReplacementHours = optString("ordinary_replacement_hours"),
            )
        }

        private fun JSONObject?.gpsDraft(): GpsDraft {
            if (this == null) return GpsDraft()
            return GpsDraft(
                dmsInput = optString("dms_input"), latitudeInput = optString("latitude_input"), longitudeInput = optString("longitude_input"),
                latitude = optString("latitude"), longitude = optString("longitude"), updatedAt = optLong("updated_at"),
            )
        }

        private fun JSONObject.id() = optString("local_id").ifBlank { UUID.randomUUID().toString() }

        private fun <T> JSONArray?.objects(maximum: Int, transform: (JSONObject) -> T): List<T> {
            if (this == null) return emptyList()
            return buildList {
                for (index in 0 until minOf(length(), maximum)) optJSONObject(index)?.let { add(transform(it)) }
            }
        }
    }
}

object CalculatorEngine {
    private val parser = DecimalExpressionParser()
    private val workbook = CalculatorWorkbookCore<BigDecimal>(parser::evaluateCommon)
    fun recalculate(lines: List<CalculationLine>): List<CalculationLine> = workbook.recalculate(
        lines.map { CalculationDraft(it, it.expression) },
        emptyLine = { CalculationLine().let { CalculationDraft(it, it.expression) } }
    ).map { it.item.copy(result = it.value, error = it.error) }
}
