package mg.hydria.app.search

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SearchDetailActivityTest {
    @Test
    fun technicalUuid_isHiddenRegardlessOfCaseOrWhitespace() {
        assertTrue(isTechnicalUuid("65d2fc9d-172d-447d-a1f4-cea9dbd4ad41"))
        assertTrue(isTechnicalUuid(" 65D2FC9D-172D-447D-A1F4-CEA9DBD4AD41 "))
        assertTrue(isTechnicalUuid("0198f780-1234-7abc-9def-0123456789ab"))
    }

    @Test
    fun usefulBusinessValues_remainVisible() {
        assertFalse(isTechnicalUuid("PE-AMB-001"))
        assertFalse(isTechnicalUuid("Paiement confirme"))
        assertFalse(isTechnicalUuid("2026-08-31"))
        assertFalse(isTechnicalUuid(null))
    }
}
