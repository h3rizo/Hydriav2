package mg.hydria.app.volume

import android.content.Context
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import android.os.Bundle
import android.os.CancellationSignal
import android.os.ParcelFileDescriptor
import android.print.*
import com.google.zxing.BarcodeFormat
import com.journeyapps.barcodescanner.BarcodeEncoder
import org.json.JSONObject
import java.io.FileOutputStream

/** A4 generated entirely on device; no WebView, network font or remote QR. */
object VolumePrinter {
    fun print(context: Context, invoices: List<JSONObject>) {
        val frozen = mg.hydria.shared.volume.VolumeCacheGateway.printOrder(invoices).map { JSONObject(it.toString()) }
        val adapter = object : PrintDocumentAdapter() {
            override fun onLayout(old: PrintAttributes?, attributes: PrintAttributes,
                                  cancellation: CancellationSignal, callback: LayoutResultCallback, extras: Bundle?) {
                if (cancellation.isCanceled) { callback.onLayoutCancelled(); return }
                callback.onLayoutFinished(PrintDocumentInfo.Builder("Hydria-factures.pdf")
                    .setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount(frozen.size).build(), true)
            }

            override fun onWrite(ranges: Array<out PageRange>, destination: ParcelFileDescriptor,
                                 cancellation: CancellationSignal, callback: WriteResultCallback) {
                try {
                    val document = PdfDocument()
                    try {
                        val written = mutableListOf<PageRange>()
                        frozen.forEachIndexed { index, invoice ->
                            if (cancellation.isCanceled) { callback.onWriteCancelled(); return }
                            if (ranges.none { index in it.start..it.end }) return@forEachIndexed
                            val page = document.startPage(PdfDocument.PageInfo.Builder(595, 842, index + 1).create())
                            val canvas = page.canvas
                            val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; textSize = 12f }
                            var y = 52f
                            fun line(value: String, bold: Boolean = false, size: Float = 12f) {
                                paint.textSize = size
                                paint.typeface = if (bold) Typeface.create("sans-serif", Typeface.BOLD) else Typeface.create("sans-serif", Typeface.NORMAL)
                                // Wrap long names and references rather than clipping invoice content.
                                var remaining = value
                                do {
                                    val count = paint.breakText(remaining, true, 491f, null).coerceAtLeast(1).coerceAtMost(remaining.length)
                                    canvas.drawText(remaining.take(count), 52f, y, paint)
                                    y += size + 8f
                                    remaining = remaining.drop(count)
                                } while (remaining.isNotEmpty())
                            }
                            line("HYDRIA", true, 24f)
                            line("FACTURE D'EAU · ${invoice.getString("mois")}", true, 16f)
                            if (!invoice.optBoolean("validee")) line("VALIDATION HORS LIGNE · EN ATTENTE DE SYNCHRONISATION", true, 10f)
                            line("N° ${invoice.getString("numero")}")
                            line("Ouvrage : ${invoice.getString("ouvrage")}")
                            line("Abonné : ${invoice.getString("abonne")}", true)
                            line("Relevé du ${invoice.getString("date_releve")}")
                            y += 12f
                            line("Ancien index : ${invoice.getString("ancien_index")} m³")
                            line("Nouvel index : ${invoice.getString("nouvel_index")} m³")
                            val detail = invoice.optJSONObject("detail") ?: JSONObject()
                            line("Volume facturé : ${detail.optString("volume_calcule", "—")} m³")
                            line("Abonnement : ${detail.optString("abonnement", "—")} Ar")
                            line("Consommation : ${detail.optString("montant_volume", "—")} Ar")
                            line("Montant avant arrondi : ${detail.optString("montant_ht", "—")} Ar")
                            y += 16f
                            line("À PAYER : ${invoice.getString("montant")} Ar", true, 22f)
                            line("Montant de cette facture uniquement.", false, 10f)
                            line("Taxe communale indicative : ${detail.optString("taxe_communale", "—")} Ar", false, 10f)
                            val bitmap = BarcodeEncoder().encodeBitmap(invoice.getString("qr"), BarcodeFormat.QR_CODE, 400, 400)
                            canvas.drawBitmap(bitmap, null, RectF(52f, 628f, 190f, 766f), paint)
                            bitmap.recycle()
                            paint.textSize = 10f
                            canvas.drawText("Scanner ce code pour retrouver la facture.", 205f, 689f, paint)
                            canvas.drawText("Une facture imprimée n'est pas une preuve de paiement.", 52f, 797f, paint)
                            document.finishPage(page)
                            written.add(PageRange(index, index))
                        }
                        FileOutputStream(destination.fileDescriptor).use(document::writeTo)
                        callback.onWriteFinished(written.toTypedArray())
                    } finally { document.close() }
                } catch (error: Exception) { callback.onWriteFailed(error.message ?: "Impression impossible") }
            }
        }
        (context.getSystemService(Context.PRINT_SERVICE) as PrintManager).print("Factures Hydria", adapter,
            PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4)
                .setColorMode(PrintAttributes.COLOR_MODE_MONOCHROME).build())
    }
}
