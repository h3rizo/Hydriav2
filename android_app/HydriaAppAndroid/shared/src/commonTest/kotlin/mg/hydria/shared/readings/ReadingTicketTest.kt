package mg.hydria.shared.readings

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ReadingTicketTest {
    private fun ticket(
        organisation: TicketOrganisation? = TicketOrganisation("Soakoja", locality = "Ambanja", province = "Diana", phone = "034 00 000 00"),
        social: Double = 0.0, nonBillable: Double = 0.0,
        unpaid: List<TicketUnpaid> = emptyList(), unpaidTotal: Double = 0.0,
    ) = ReadingTicket(
        organisation = organisation, invoiceNumber = "FAC-001", date = "05/10/2026",
        pointName = "RAKOTO Jean", pointCode = "PE-12", pointType = "Kiosque",
        oldIndex = 100.0, newIndex = 112.5, consumption = 12.5,
        socialCardsVolume = social, nonBillable = nonBillable, billedVolume = 12.5 - social - nonBillable,
        subscription = 2000.0, volumeAmount = 41000.0, total = 43000.0,
        unpaid = unpaid, unpaidTotal = unpaidTotal,
    )

    private fun texts(lines: List<TicketLine>): List<String> = lines.flatMap {
        when (it) {
            is TicketLine.Text -> listOf(it.text)
            is TicketLine.Row -> listOfNotNull(it.left, it.middle, it.right)
            else -> emptyList()
        }
    }

    @Test fun formatsAmountsWithSpacesAndQuantitiesWithTwoDecimals() {
        assertEquals("1 234 567", ReadingTicketFormat.amount(1234567.0))
        assertEquals("500", ReadingTicketFormat.amount(500.0))
        assertEquals("0", ReadingTicketFormat.amount(0.0))
        assertEquals("12.50", ReadingTicketFormat.quantity(12.5))
        assertEquals("0.00", ReadingTicketFormat.quantity(-0.001))
        assertEquals("-3.05", ReadingTicketFormat.quantity(-3.05))
    }

    @Test fun headerUsesOrganisationOtherwiseHydriaDefault() {
        assertEquals("SOAKOJA", texts(ReadingTicketLayout.lines(ticket())).first())
        assertEquals("HYDRIA", texts(ReadingTicketLayout.lines(ticket(organisation = null))).first())
    }

    @Test fun totalIsPrintedAndNoReminderWithoutUnpaid() {
        val all = texts(ReadingTicketLayout.lines(ticket()))
        assertTrue("43 000 Ar" in all)
        assertFalse(all.any { it.contains("TROSA") })
    }

    @Test fun socialCardsAndNonBillableLinesOnlyWhenPresent() {
        assertFalse(texts(ReadingTicketLayout.lines(ticket())).any { it.contains("Karatra") || it.contains("Tsy voarakitra") })
        val all = texts(ReadingTicketLayout.lines(ticket(social = 0.4, nonBillable = 1.0)))
        assertTrue("- Karatra sosialy" in all)
        assertTrue("0.40 m3" in all)
        assertTrue("- Tsy voarakitra" in all)
    }

    @Test fun unpaidReminderIsSeparateFromTheAmountToPay() {
        val lines = ReadingTicketLayout.lines(ticket(unpaid = listOf(TicketUnpaid("01/09/2026", 8.0, 5500.0)), unpaidTotal = 5500.0))
        val all = texts(lines)
        assertTrue("TOTAL TROSA:" in all && "TROSA TALOHA:" in all)
        assertTrue("5 500 Ar" in all)
        val total = lines.filterIsInstance<TicketLine.Row>().single { it.left == "VOLA IRAY VOLANA:" }
        assertEquals("43 000 Ar", total.right)
    }
}
