package mg.hydria.app.volume

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class VolumeQrTest {
    private val invoice = JSONObject().put("id", "a").put("numero", "F-2026-3")
        .put("mois", "2026-09").put("ouvrage_id", "b")

    @Test fun acceptsPrintedQrAndManualNumber() {
        assertSame(invoice, VolumeQr.find("HYDRIA|FACTURE|a|F-2026-3|2026-09|b", listOf(invoice)))
        assertSame(invoice, VolumeQr.find(" F-2026-3 ", listOf(invoice)))
    }
    @Test fun rejectsAnotherWorkOrPeriodAndAmbiguousNumber() {
        assertNull(VolumeQr.find("HYDRIA|FACTURE|a|F-2026-3|2026-08|b", listOf(invoice)))
        assertNull(VolumeQr.find("HYDRIA|FACTURE|a|F-2026-3|2026-09|c", listOf(invoice)))
        assertNull(VolumeQr.find("F-2026-3", listOf(invoice, invoice)))
        assertNull(VolumeQr.find("https://example.com", listOf(invoice)))
    }
}
