package mg.hydria.app.readings

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import android.os.Bundle
import android.os.CancellationSignal
import android.os.ParcelFileDescriptor
import android.print.PageRange
import android.print.PrintAttributes
import android.print.PrintDocumentAdapter
import android.print.PrintDocumentInfo
import android.print.PrintManager
import mg.hydria.shared.readings.ReadingTicket
import mg.hydria.shared.readings.ReadingTicketLayout
import mg.hydria.shared.readings.TicketAlign
import mg.hydria.shared.readings.TicketLine
import mg.hydria.shared.readings.TicketStyle
import java.io.FileOutputStream
import kotlin.math.ceil

/**
 * Ticket de facture 80 mm généré sur l'appareil (PDF d'une page de 80 mm de large,
 * hauteur ajustée au contenu) et remis au service d'impression Android : une
 * imprimante portable Bluetooth/USB 80 mm doit exposer son service (plugin du
 * fabricant, RawBT...). Mise en page : [ReadingTicketLayout], identique au ticket web.
 */
object ReadingTicketPrinter {
    private const val PAGE_WIDTH_PT = 227 // 80 mm = 226,8 pt

    fun print(context: Context, ticket: ReadingTicket) {
        val lines = ReadingTicketLayout.lines(ticket)
        val height = ceil(TicketRenderer(PAGE_WIDTH_PT.toFloat()).render(lines, null)).toInt().coerceAtLeast(120)
        val fileName = "Hydria-ticket-${ticket.invoiceNumber.ifBlank { "facture" }}.pdf"
        val adapter = object : PrintDocumentAdapter() {
            override fun onLayout(old: PrintAttributes?, attributes: PrintAttributes, cancellation: CancellationSignal,
                                  callback: LayoutResultCallback, extras: Bundle?) {
                if (cancellation.isCanceled) callback.onLayoutCancelled()
                else callback.onLayoutFinished(PrintDocumentInfo.Builder(fileName)
                    .setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount(1).build(), true)
            }

            override fun onWrite(ranges: Array<out PageRange>, destination: ParcelFileDescriptor,
                                 cancellation: CancellationSignal, callback: WriteResultCallback) {
                val document = PdfDocument()
                try {
                    val page = document.startPage(PdfDocument.PageInfo.Builder(PAGE_WIDTH_PT, height, 1).create())
                    TicketRenderer(PAGE_WIDTH_PT.toFloat()).render(lines, page.canvas)
                    document.finishPage(page)
                    FileOutputStream(destination.fileDescriptor).use(document::writeTo)
                    callback.onWriteFinished(arrayOf(PageRange(0, 0)))
                } catch (error: Exception) {
                    callback.onWriteFailed(error.message ?: "Impression impossible")
                } finally { document.close() }
            }
        }
        val mediaSize = PrintAttributes.MediaSize("HYDRIA_80MM", "Ticket 80 mm", 3150, height * 1000 / 72)
        (context.getSystemService(Context.PRINT_SERVICE) as PrintManager).print(
            "Facture Hydria", adapter,
            PrintAttributes.Builder().setMediaSize(mediaSize)
                .setMinMargins(PrintAttributes.Margins.NO_MARGINS)
                .setColorMode(PrintAttributes.COLOR_MODE_MONOCHROME).build(),
        )
    }

    /** Dessine (ou mesure si [canvas] est nul) les lignes du ticket ; retourne la hauteur utilisée. */
    private class TicketRenderer(private val width: Float) {
        private val margin = 10f
        private val contentWidth = width - 2 * margin
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK }

        fun render(lines: List<TicketLine>, canvas: Canvas?): Float {
            var y = margin
            for (line in lines) {
                when (line) {
                    TicketLine.Gap -> y += 6f
                    is TicketLine.Rule -> {
                        y += 3f
                        paint.strokeWidth = if (line.dashed) 1f else 1.6f
                        paint.pathEffect = if (line.dashed) DashPathEffect(floatArrayOf(4f, 3f), 0f) else null
                        canvas?.drawLine(margin, y, width - margin, y, paint)
                        paint.pathEffect = null
                        y += 5f
                    }
                    is TicketLine.Text -> {
                        applyStyle(line.style)
                        wrap(line.text, contentWidth).forEach { part ->
                            val x = if (line.align == TicketAlign.CENTER) (width - paint.measureText(part)) / 2 else margin
                            y += paint.textSize
                            canvas?.drawText(part, x, y, paint)
                            y += 3f
                        }
                    }
                    is TicketLine.Row -> {
                        applyStyle(line.style)
                        val rightX = width - margin
                        val middleX = margin + contentWidth * 0.66f
                        val reserved = if (line.middle != null) {
                            // Le texte de gauche s'arrête avant la colonne du milieu.
                            contentWidth - (rightX - (middleX - paint.measureText(line.middle)))
                        } else contentWidth - paint.measureText(line.right) - 6f
                        val leftParts = wrap(line.left, reserved.coerceAtLeast(40f))
                        leftParts.forEachIndexed { index, part ->
                            y += paint.textSize
                            canvas?.drawText(part, margin, y, paint)
                            if (index == 0) {
                                line.middle?.let { canvas?.drawText(it, middleX - paint.measureText(it), y, paint) }
                                canvas?.drawText(line.right, rightX - paint.measureText(line.right), y, paint)
                            }
                            y += 3f
                        }
                    }
                }
            }
            return y + margin
        }

        private fun applyStyle(style: TicketStyle) {
            paint.typeface = Typeface.create(Typeface.MONOSPACE, if (style == TicketStyle.NORMAL || style == TicketStyle.SMALL) Typeface.NORMAL else Typeface.BOLD)
            paint.textSize = when (style) {
                TicketStyle.TITLE -> 13f
                TicketStyle.TOTAL -> 11f
                TicketStyle.SMALL -> 8f
                else -> 9f
            }
        }

        private fun wrap(value: String, maxWidth: Float): List<String> {
            var remaining = value
            val parts = mutableListOf<String>()
            do {
                val count = paint.breakText(remaining, true, maxWidth, null).coerceAtLeast(1).coerceAtMost(remaining.length)
                // Coupe sur une espace quand c'est possible plutôt qu'au milieu d'un mot.
                val cut = if (count < remaining.length) remaining.lastIndexOf(' ', count).takeIf { it > 0 } ?: count else count
                parts.add(remaining.take(cut).trimEnd())
                remaining = remaining.drop(cut).trimStart()
            } while (remaining.isNotEmpty())
            return parts
        }
    }
}
