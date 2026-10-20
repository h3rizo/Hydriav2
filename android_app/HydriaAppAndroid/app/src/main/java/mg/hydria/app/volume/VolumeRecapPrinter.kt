package mg.hydria.app.volume

import android.content.Context
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import android.os.Bundle
import android.os.CancellationSignal
import android.os.ParcelFileDescriptor
import android.print.*
import org.json.JSONObject
import java.io.FileOutputStream

/** Paginated native A4 recap: metadata, invoices and the website's IDXLS grid. */
object VolumeRecapPrinter {
    fun print(context: Context, source: JSONObject) {
        val recap = JSONObject(source.toString())
        val adapter = object : PrintDocumentAdapter() {
            override fun onLayout(oldAttributes: PrintAttributes?, newAttributes: PrintAttributes,
                                  cancellationSignal: CancellationSignal, callback: LayoutResultCallback, extras: Bundle?) {
                if (cancellationSignal.isCanceled) callback.onLayoutCancelled()
                else callback.onLayoutFinished(PrintDocumentInfo.Builder("Hydria-recap-encaissement.pdf")
                    .setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount(PrintDocumentInfo.PAGE_COUNT_UNKNOWN).build(), true)
            }
            override fun onWrite(ranges: Array<out PageRange>, destination: ParcelFileDescriptor,
                                 cancellation: CancellationSignal, callback: WriteResultCallback) {
                val document = PdfDocument()
                var page: PdfDocument.Page? = null
                var pageIndex = -1
                val written = mutableListOf<PageRange>()
                val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 10f; color = Color.BLACK }
                var y = 42f
                fun nextPage() {
                    page?.let { document.finishPage(it); written.add(PageRange(pageIndex, pageIndex)) }
                    pageIndex++
                    page = if (ranges.any { pageIndex in it.start..it.end }) document.startPage(PdfDocument.PageInfo.Builder(595, 842, pageIndex + 1).create()) else null
                    y = 42f
                    paint.textSize = 10f; paint.color = Color.BLACK
                    page?.canvas?.drawText("HYDRIA · Récapitulatif d'encaissement · ${recap.optString("mois")}", 38f, y, paint)
                    page?.canvas?.drawText("${pageIndex + 1}", 545f, 808f, paint)
                    y += 24f
                }
                fun wrap(value: String, width: Float): List<String> {
                    var remaining = value
                    return buildList {
                        do {
                            val n = paint.breakText(remaining, true, width, null).coerceAtLeast(1).coerceAtMost(remaining.length)
                            add(remaining.take(n)); remaining = remaining.drop(n)
                        } while (remaining.isNotEmpty())
                    }
                }
                fun line(value: String, bold: Boolean = false) {
                    paint.typeface = Typeface.create("sans-serif", if (bold) Typeface.BOLD else Typeface.NORMAL)
                    wrap(value, 515f).forEach { text ->
                        if (y + 16 > 780) nextPage()
                        page?.canvas?.drawText(text, 38f, y, paint); y += 16f
                    }
                }
                fun cells(values: List<String>, widths: List<Float>, grey: Set<Int> = emptySet()) {
                    paint.typeface = Typeface.create("sans-serif", Typeface.NORMAL)
                    val lines = values.mapIndexed { i, value -> wrap(value, widths[i] - 8) }
                    val height = lines.maxOf { it.size } * 13f + 8f
                    if (y + height > 780) nextPage()
                    var x = 38f
                    values.indices.forEach { i ->
                        paint.color = Color.LTGRAY; paint.style = Paint.Style.STROKE
                        page?.canvas?.drawRect(x, y, x + widths[i], y + height, paint)
                        paint.style = Paint.Style.FILL; paint.color = if (i in grey) Color.GRAY else Color.BLACK
                        lines[i].forEachIndexed { j, text -> page?.canvas?.drawText(text, x + 4f, y + 14f + j * 13f, paint) }
                        x += widths[i]
                    }
                    paint.color = Color.BLACK; y += height
                }
                try {
                    nextPage()
                    line("Ouvrage : ${recap.getString("ouvrage")}", true)
                    line("Date : ${recap.getString("date")} · Journal : ${recap.getString("journal")}")
                    val invoices = recap.getJSONArray("factures")
                    line("${invoices.length()} factures · Montant total : ${recap.getString("total")} Ar", true)
                    line("Référence : ${recap.getString("local_uuid")}")
                    line("Généré le : ${recap.optString("generated_at")}")
                    when (recap.optString("etat")) {
                        "synchronisee" -> line("Ligne DiameX temporaire créée : ${recap.optString("diamex_temporaire_id")}", true)
                        "refusee" -> { line("ENCAISSEMENT REFUSÉ PAR LE SERVEUR · À VÉRIFIER", true); line(recap.optString("erreur")) }
                        "verification_manuelle" -> { line("CLÔTURE APRÈS VÉRIFICATION MANUELLE", true); line(recap.optString("note")) }
                        else -> line("ENCAISSEMENT LOCAL · SYNCHRONISATION EN ATTENTE", true)
                    }
                    line("Paiement au volume ${recap.getString("ouvrage")} · ${recap.getString("mois")} · ${recap.getString("total")} Ar")
                    y += 8f
                    val widths = listOf(45f, 184f, 72f, 119f, 99f)
                    cells(listOf("IDXLS", "Abonné / facture", "Mois", "Type point d'eau", "Montant Ar"), widths)
                    for (i in 0 until invoices.length()) {
                        if (cancellation.isCanceled) throw InterruptedException()
                        val row = invoices.getJSONObject(i)
                        cells(listOf(row.optString("idxls"), "${row.optString("abonne")} / ${row.optString("numero")}", row.optString("mois"), row.optString("type_pe"), row.optString("montant")), widths)
                    }
                    y += 16f
                    line("Grille IDXLS · contrôle des écarts de versement", true)
                    line("Noir : factures de ce récap. Gris : déjà pointées DiameX lors de la préparation.")
                    val black = (0 until invoices.length()).mapNotNull { invoices.getJSONObject(it).optString("idxls").toLongOrNull() }.filter { it >= 0 }.toSet()
                    val pointed = recap.optJSONArray("idxls_pointes")
                    val grey = (0 until (pointed?.length() ?: 0)).mapNotNull { pointed!!.optString(it).toLongOrNull() }.filter { it >= 0 }.toSet() - black
                    val occupiedRows = (black + grey).map { it / 10 }.distinct().sorted()
                    val gridWidths = List(11) { 519f / 11 }
                    cells(listOf("Dizaines") + (0..9).map(Int::toString), gridWidths)
                    // Sparse rows avoid thousands of blank pages for large IDXLS.
                    occupiedRows.forEach { row ->
                        if (cancellation.isCanceled) throw InterruptedException()
                        val values = listOf(row.toString()) + (0..9).map { unit ->
                            val n = row * 10 + unit
                            if (n in black || n in grey) n.toString() else ""
                        }
                        cells(values, gridWidths, (0..9).filter { row * 10 + it in grey }.map { it + 1 }.toSet())
                    }
                    page?.let { document.finishPage(it); written.add(PageRange(pageIndex, pageIndex)); page = null }
                    if (cancellation.isCanceled) throw InterruptedException()
                    FileOutputStream(destination.fileDescriptor).use { document.writeTo(it) }
                    callback.onWriteFinished(written.toTypedArray())
                } catch (_: InterruptedException) { callback.onWriteCancelled() }
                catch (e: Exception) { callback.onWriteFailed(e.message) }
                finally { page?.let { document.finishPage(it) }; document.close() }
            }
        }
        (context.getSystemService(Context.PRINT_SERVICE) as PrintManager).print("Récap encaissement Hydria", adapter,
            PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).setColorMode(PrintAttributes.COLOR_MODE_MONOCHROME).build())
    }
}
