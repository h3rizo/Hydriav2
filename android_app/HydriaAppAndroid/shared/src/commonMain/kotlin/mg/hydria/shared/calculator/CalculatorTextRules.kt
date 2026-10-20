package mg.hydria.shared.calculator

object CalculatorTextRules {
    fun decimalText(value: String): String? {
        val normalized = value.trim().replace(" ", "").replace('\u00a0'.toString(), "").replace(',', '.')
        if (normalized.isBlank()) return "0"
        return normalized.takeIf { it.matches(Regex("[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)")) }
    }
    fun matches(designation: String, date: String, expectedDesignation: String, expectedDate: String, contains: Boolean): Boolean {
        val expected = expectedDesignation.trim().lowercase()
        val actual = designation.trim().lowercase()
        val designationMatches = expected.isBlank() || if (contains) actual.contains(expected) else actual == expected
        return designationMatches && (expectedDate.isBlank() || date.trim() == expectedDate.trim())
    }
    fun bookName(value: String, limit: Int): String = value.trim().replace(Regex("\\s+"), " ").take(limit)
}
