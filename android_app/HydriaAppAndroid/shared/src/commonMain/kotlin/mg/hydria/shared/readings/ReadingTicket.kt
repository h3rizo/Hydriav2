package mg.hydria.shared.readings

import kotlin.math.abs
import kotlin.math.round

data class TicketOrganisation(
    val name: String, val address: String? = null, val locality: String? = null, val province: String? = null,
    val phone: String? = null, val nif: String? = null, val stat: String? = null,
)

data class TicketUnpaid(val date: String, val volume: Double, val amount: Double)

/** Données d'un ticket de facture 80 mm : relevé enregistré + calcul tarifaire serveur. */
data class ReadingTicket(
    val organisation: TicketOrganisation?,
    val invoiceNumber: String,
    val date: String,
    val pointName: String,
    val pointCode: String,
    val pointType: String?,
    val oldIndex: Double,
    val newIndex: Double,
    val consumption: Double,
    val socialCardsVolume: Double,
    val nonBillable: Double,
    val billedVolume: Double,
    val subscription: Double,
    val volumeAmount: Double,
    val total: Double,
    val unpaid: List<TicketUnpaid> = emptyList(),
    val unpaidTotal: Double = 0.0,
)

enum class TicketStyle { NORMAL, SMALL, BOLD, TITLE, TOTAL }
enum class TicketAlign { LEFT, CENTER }

sealed class TicketLine {
    data class Text(val text: String, val style: TicketStyle = TicketStyle.NORMAL, val align: TicketAlign = TicketAlign.LEFT) : TicketLine()

    /** Ligne à 2 ou 3 colonnes ; [middle] aligné à droite à 62 % de la largeur. */
    data class Row(val left: String, val middle: String?, val right: String, val style: TicketStyle = TicketStyle.NORMAL) : TicketLine()

    data class Rule(val dashed: Boolean = true) : TicketLine()
    data object Gap : TicketLine()
}

object ReadingTicketFormat {
    /** Volume en m³ avec 2 décimales, comme le ticket web (toFixed(2)). */
    fun quantity(value: Double): String {
        val hundredths = round(abs(value) * 100).toLong()
        val sign = if (value < 0 && hundredths != 0L) "-" else ""
        return "$sign${hundredths / 100}.${(hundredths % 100).toString().padStart(2, '0')}"
    }

    /** Ariary entier, milliers séparés par une espace (1 500). */
    fun amount(value: Double): String {
        val rounded = round(value).toLong()
        val digits = abs(rounded).toString()
        val grouped = digits.reversed().chunked(3).joinToString(" ").reversed()
        return if (rounded < 0) "-$grouped" else grouped
    }

}

/** Même forme que le ticket terrain web (imprimerTicketTerrain, releves_workflow.html). */
object ReadingTicketLayout {
    fun lines(ticket: ReadingTicket): List<TicketLine> = buildList {
        val org = ticket.organisation
        if (org != null && org.name.isNotBlank()) {
            add(TicketLine.Text(org.name.uppercase(), TicketStyle.TITLE, TicketAlign.CENTER))
            org.address?.takeIf { it.isNotBlank() }?.let { add(TicketLine.Text(it, TicketStyle.SMALL, TicketAlign.CENTER)) }
            org.locality?.takeIf { it.isNotBlank() }?.let { locality ->
                val province = org.province?.takeIf { it.isNotBlank() }?.let { " - $it" }.orEmpty()
                add(TicketLine.Text(locality + province, TicketStyle.SMALL, TicketAlign.CENTER))
            }
            org.phone?.takeIf { it.isNotBlank() }?.let { add(TicketLine.Text("Tel: $it", TicketStyle.SMALL, TicketAlign.CENTER)) }
            org.nif?.takeIf { it.isNotBlank() }?.let { add(TicketLine.Text("NIF: $it", TicketStyle.SMALL, TicketAlign.CENTER)) }
            org.stat?.takeIf { it.isNotBlank() }?.let { add(TicketLine.Text("STAT: $it", TicketStyle.SMALL, TicketAlign.CENTER)) }
        } else {
            add(TicketLine.Text("HYDRIA", TicketStyle.TITLE, TicketAlign.CENTER))
            add(TicketLine.Text("Facture d'eau", TicketStyle.SMALL, TicketAlign.CENTER))
        }
        add(TicketLine.Rule(dashed = true))

        add(TicketLine.Row("FAKTIORA LAHARANA:", null, ticket.invoiceNumber.ifBlank { "N/A" }, TicketStyle.BOLD))
        add(TicketLine.Row("Daty:", null, ticket.date, TicketStyle.BOLD))
        add(TicketLine.Gap)

        add(TicketLine.Text("MPANJIFA", TicketStyle.BOLD))
        add(TicketLine.Text(ticket.pointName))
        add(TicketLine.Text("Toerana: ${ticket.pointCode}"))
        ticket.pointType?.takeIf { it.isNotBlank() }?.let { add(TicketLine.Text("Karazana: $it")) }
        add(TicketLine.Gap)

        add(TicketLine.Text("FANJIFANA", TicketStyle.BOLD))
        add(TicketLine.Row("Antony", "Habetsaka", "Vola", TicketStyle.BOLD))
        add(TicketLine.Rule(dashed = false))
        add(TicketLine.Text("Index taloha: ${ReadingTicketFormat.quantity(ticket.oldIndex)} m3", TicketStyle.SMALL))
        add(TicketLine.Text("Index vaovao: ${ReadingTicketFormat.quantity(ticket.newIndex)} m3", TicketStyle.SMALL))
        add(TicketLine.Text("Rano lany: ${ReadingTicketFormat.quantity(ticket.consumption)} m3", TicketStyle.BOLD))
        if (ticket.socialCardsVolume > 0) {
            add(TicketLine.Row("- Karatra sosialy", "${ReadingTicketFormat.quantity(ticket.socialCardsVolume)} m3", "-"))
        }
        if (ticket.nonBillable != 0.0) {
            add(TicketLine.Row("- Tsy voarakitra", "${ReadingTicketFormat.quantity(ticket.nonBillable)} m3", "-"))
        }
        add(TicketLine.Rule(dashed = true))
        add(TicketLine.Row("Rano voarakitra", "${ReadingTicketFormat.quantity(ticket.billedVolume)} m3", "-", TicketStyle.BOLD))
        add(TicketLine.Row("Famandrihana", "-", ReadingTicketFormat.amount(ticket.subscription)))
        add(TicketLine.Row("Fanjifana", "${ReadingTicketFormat.quantity(ticket.billedVolume)} m3", ReadingTicketFormat.amount(ticket.volumeAmount)))
        add(TicketLine.Gap)

        if (ticket.unpaid.isNotEmpty()) {
            add(TicketLine.Rule(dashed = true))
            add(TicketLine.Text("FAMPAHAFANTARANA / RAPPEL", TicketStyle.BOLD, TicketAlign.CENTER))
            add(TicketLine.Text("Manana trosa tsy voaloa ianao / Vous avez des impayes", TicketStyle.SMALL, TicketAlign.CENTER))
            add(TicketLine.Row("Daty", "Rano (m3)", "Vola (Ar)", TicketStyle.SMALL))
            ticket.unpaid.forEach {
                add(TicketLine.Row(it.date, ReadingTicketFormat.quantity(it.volume), ReadingTicketFormat.amount(it.amount), TicketStyle.SMALL))
            }
            add(TicketLine.Row("TOTAL TROSA:", null, "${ReadingTicketFormat.amount(ticket.unpaidTotal)} Ar", TicketStyle.BOLD))
            add(TicketLine.Text("Tsy tafiditra amin'ny faktiora ankehitriny / Non inclus dans cette facture", TicketStyle.SMALL, TicketAlign.CENTER))
            add(TicketLine.Rule(dashed = true))
            add(TicketLine.Gap)
        }

        add(TicketLine.Rule(dashed = false))
        add(TicketLine.Row("VOLA IRAY VOLANA:", null, "${ReadingTicketFormat.amount(ticket.total)} Ar", TicketStyle.TOTAL))
        add(TicketLine.Rule(dashed = false))

        if (ticket.unpaidTotal > 0) {
            add(TicketLine.Gap)
            add(TicketLine.Rule(dashed = true))
            add(TicketLine.Text("FAMPAHAFANTARANA / RAPPEL", TicketStyle.BOLD, TicketAlign.CENTER))
            add(TicketLine.Text("Manana trosa tsy voaloa ianao / Vous avez des impayes anterieurs", TicketStyle.SMALL, TicketAlign.CENTER))
            add(TicketLine.Row("TROSA TALOHA:", null, "${ReadingTicketFormat.amount(ticket.unpaidTotal)} Ar", TicketStyle.BOLD))
            add(TicketLine.Text("Tsy tafiditra amin'ny faktiora ankehitriny / Non inclus dans cette facture", TicketStyle.SMALL, TicketAlign.CENTER))
            add(TicketLine.Rule(dashed = true))
        }

        add(TicketLine.Gap)
        add(TicketLine.Rule(dashed = true))
        add(TicketLine.Text("Misaotra anao", TicketStyle.SMALL, TicketAlign.CENTER))
        add(TicketLine.Text(org?.name?.takeIf { it.isNotBlank() } ?: "HYDRIA", TicketStyle.SMALL, TicketAlign.CENTER))
        add(TicketLine.Text("---------------------------", TicketStyle.SMALL, TicketAlign.CENTER))
    }
}
