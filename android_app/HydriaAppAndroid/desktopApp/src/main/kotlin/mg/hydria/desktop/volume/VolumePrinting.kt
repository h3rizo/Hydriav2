package mg.hydria.desktop.volume

import org.json.JSONObject
import java.awt.Color
import java.awt.Font
import java.awt.Graphics
import java.awt.Graphics2D
import java.awt.RenderingHints
import java.awt.image.BufferedImage
import java.awt.print.PageFormat
import java.awt.print.Pageable
import java.awt.print.Paper
import java.awt.print.Printable
import java.awt.print.PrinterJob
import javax.print.attribute.HashPrintRequestAttributeSet
import javax.print.attribute.standard.Chromaticity
import javax.print.attribute.standard.JobName
import javax.print.attribute.standard.MediaSizeName

/**
 * Impression A4 Desktop du recapitulatif d'encaissement, portage de
 * `VolumeRecapPrinter` (Android PdfDocument) vers Java2D. Les FACTURES, elles,
 * utilisent le gabarit de la page web (voir [WebInvoicePrint]).
 * Memes coordonnees (points A4 595x842), memes textes, meme grille IDXLS.
 * Le dialogue systeme permet d'imprimer ou d'enregistrer en PDF
 * (« Microsoft Print to PDF »).
 */
object VolumePrinting {
    private const val W = 595.0
    private const val H = 842.0

    private sealed interface Op
    private data class TextOp(val x: Float, val y: Float, val text: String, val font: Font, val color: Color = Color.BLACK) : Op
    private data class RectOp(val x: Float, val y: Float, val w: Float, val h: Float) : Op

    private val metrics = BufferedImage(1, 1, BufferedImage.TYPE_INT_RGB).createGraphics()
    private fun font(size: Float, bold: Boolean = false) = Font(Font.SANS_SERIF, if (bold) Font.BOLD else Font.PLAIN, 1).deriveFont(size)

    private fun wrap(value: String, width: Float, font: Font): List<String> {
        val fm = metrics.getFontMetrics(font)
        var remaining = value
        return buildList {
            do {
                var n = remaining.length
                while (n > 1 && fm.stringWidth(remaining.take(n)) > width) n--
                add(remaining.take(n)); remaining = remaining.drop(n)
            } while (remaining.isNotEmpty())
        }
    }

    /** Recapitulatif d'encaissement pagine + grille IDXLS (cf. VolumeRecapPrinter Android). */
    fun printRecap(source: JSONObject) {
        val recap = JSONObject(source.toString())
        val pages = mutableListOf<MutableList<Op>>()
        var y = 42f
        fun current() = pages.last()
        fun nextPage() {
            pages += mutableListOf<Op>()
            y = 42f
            current() += TextOp(38f, y, "HYDRIA · Récapitulatif d'encaissement · ${recap.optString("mois")}", font(10f))
            current() += TextOp(545f, 808f, "${pages.size}", font(10f))
            y += 24f
        }
        fun line(value: String, bold: Boolean = false) {
            val f = font(10f, bold)
            wrap(value, 515f, f).forEach { text ->
                if (y + 16 > 780) nextPage()
                current() += TextOp(38f, y, text, f); y += 16f
            }
        }
        fun cells(values: List<String>, widths: List<Float>, grey: Set<Int> = emptySet()) {
            val f = font(10f)
            val lines = values.mapIndexed { i, value -> wrap(value, widths[i] - 8, f) }
            val height = lines.maxOf { it.size } * 13f + 8f
            if (y + height > 780) nextPage()
            var x = 38f
            values.indices.forEach { i ->
                current() += RectOp(x, y, widths[i], height)
                lines[i].forEachIndexed { j, text ->
                    current() += TextOp(x + 4f, y + 14f + j * 13f, text, f, if (i in grey) Color.GRAY else Color.BLACK)
                }
                x += widths[i]
            }
            y += height
        }
        nextPage()
        line("Ouvrage : ${recap.optString("ouvrage")}", true)
        line("Date : ${recap.optString("date")} · Journal : ${recap.optString("journal")}")
        val invoices = recap.getJSONArray("factures")
        line("${invoices.length()} factures · Montant total : ${recap.optString("total")} Ar", true)
        line("Référence : ${recap.optString("local_uuid")}")
        line("Généré le : ${recap.optString("generated_at")}")
        when (recap.optString("etat")) {
            "synchronisee" -> line("Ligne DiameX temporaire créée : ${recap.optString("diamex_temporaire_id")}", true)
            "refusee" -> { line("ENCAISSEMENT REFUSÉ PAR LE SERVEUR · À VÉRIFIER", true); line(recap.optString("erreur")) }
            "verification_manuelle" -> { line("CLÔTURE APRÈS VÉRIFICATION MANUELLE", true); line(recap.optString("note")) }
            else -> line("ENCAISSEMENT LOCAL · SYNCHRONISATION EN ATTENTE", true)
        }
        line("Paiement au volume ${recap.optString("ouvrage")} · ${recap.optString("mois")} · ${recap.optString("total")} Ar")
        y += 8f
        val widths = listOf(45f, 184f, 72f, 119f, 99f)
        cells(listOf("IDXLS", "Abonné / facture", "Mois", "Type point d'eau", "Montant Ar"), widths)
        for (i in 0 until invoices.length()) {
            val row = invoices.getJSONObject(i)
            cells(listOf(row.optString("idxls"), "${row.optString("abonne")} / ${row.optString("numero")}",
                row.optString("mois"), row.optString("type_pe"), row.optString("montant")), widths)
        }
        y += 16f
        line("Grille IDXLS · contrôle des écarts de versement", true)
        line("Noir : factures de ce récap. Gris : déjà pointées DiameX lors de la préparation.")
        val black = (0 until invoices.length()).mapNotNull { invoices.getJSONObject(it).optString("idxls").toLongOrNull() }.filter { it >= 0 }.toSet()
        val pointed = recap.optJSONArray("idxls_pointes")
        val grey = (0 until (pointed?.length() ?: 0)).mapNotNull { pointed!!.optString(it).toLongOrNull() }.filter { it >= 0 }.toSet() - black
        val gridWidths = List(11) { 519f / 11 }
        cells(listOf("Dizaines") + (0..9).map(Int::toString), gridWidths)
        // Lignes creuses : pas de milliers de pages vides pour de grands IDXLS.
        (black + grey).map { it / 10 }.distinct().sorted().forEach { row ->
            val values = listOf(row.toString()) + (0..9).map { unit ->
                val n = row * 10 + unit
                if (n in black || n in grey) n.toString() else ""
            }
            cells(values, gridWidths, (0..9).filter { row * 10 + it in grey }.map { it + 1 }.toSet())
        }
        print("Récap encaissement Hydria", pages)
    }

    private fun print(jobName: String, pages: List<List<Op>>) {
        require(pages.isNotEmpty()) { "Aucune page à imprimer" }
        val format = PageFormat().apply {
            paper = Paper().apply { setSize(W, H); setImageableArea(0.0, 0.0, W, H) }
        }
        val printable = Printable { graphics: Graphics, _: PageFormat, index: Int ->
            if (index >= pages.size) return@Printable Printable.NO_SUCH_PAGE
            val g = graphics as Graphics2D
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            pages[index].forEach { op ->
                when (op) {
                    is TextOp -> { g.font = op.font; g.color = op.color; g.drawString(op.text, op.x, op.y) }
                    is RectOp -> { g.color = Color.LIGHT_GRAY; g.draw(java.awt.geom.Rectangle2D.Float(op.x, op.y, op.w, op.h)) }
                }
            }
            Printable.PAGE_EXISTS
        }
        val job = PrinterJob.getPrinterJob()
        job.jobName = jobName
        job.setPageable(object : Pageable {
            override fun getNumberOfPages() = pages.size
            override fun getPageFormat(pageIndex: Int) = format
            override fun getPrintable(pageIndex: Int) = printable
        })
        val attributes = HashPrintRequestAttributeSet().apply {
            add(MediaSizeName.ISO_A4); add(Chromaticity.MONOCHROME); add(JobName(jobName, null))
        }
        if (job.printDialog(attributes)) job.print(attributes)
    }
}
