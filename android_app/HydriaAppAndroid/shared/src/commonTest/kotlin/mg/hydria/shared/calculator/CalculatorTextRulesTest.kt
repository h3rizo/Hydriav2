package mg.hydria.shared.calculator

import kotlin.test.*

class CalculatorTextRulesTest {
    @Test fun decimalNormalizationPreservesAcceptedFormats() {
        assertEquals("1234.50", CalculatorTextRules.decimalText(" 1\u00a0234,50 "))
        assertEquals("0", CalculatorTextRules.decimalText(" \t"))
        assertEquals("-.5", CalculatorTextRules.decimalText("-,5"))
        for (input in listOf("1e3", "1.2.3", "NaN", "1+2")) assertNull(CalculatorTextRules.decimalText(input))
    }
    @Test fun filtersCombineDateAndDesignation() {
        assertTrue(CalculatorTextRules.matches(" Achat TUYAU ", " 2026-09-08 ", "tuyau", "2026-09-08", true))
        assertFalse(CalculatorTextRules.matches("Achat tuyau", "2026-09-08", "tuyau", "", false))
        assertFalse(CalculatorTextRules.matches("Tuyau", "2026-09-09", "tuyau", "2026-09-08", false))
        assertTrue(CalculatorTextRules.matches("Tuyau", "", " TUYAU ", "", false))
    }
    @Test fun bookNamesNormalizeWhitespaceAndLimitLength() {
        assertEquals("Caisse Nord", CalculatorTextRules.bookName(" Caisse\n  Nord ", 80))
        assertEquals("Caisse", CalculatorTextRules.bookName("Caisse Nord", 6))
    }
}
