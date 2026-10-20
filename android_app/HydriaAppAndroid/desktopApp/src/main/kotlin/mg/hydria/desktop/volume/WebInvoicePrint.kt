package mg.hydria.desktop.volume

import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import mg.hydria.shared.volume.VolumeCacheGateway
import org.json.JSONArray
import org.json.JSONObject
import java.awt.Desktop
import java.awt.image.BufferedImage
import javax.imageio.ImageIO
import java.io.ByteArrayOutputStream
import java.io.File
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.security.MessageDigest
import java.time.Duration
import java.util.Base64

/**
 * Impression des factures Desktop avec le gabarit EXACT de la page web
 * Facturation (`backend/static/js/print_factures_a4.js`, embarque tel quel a
 * chaque build). On lui donne les memes donnees que `api_calculer_factures`
 * (bloc `impression` du bootstrap mobile) et on ouvre le resultat dans le
 * navigateur par defaut, avec sa barre « Imprimer / Fermer ».
 *
 * Seule adaptation, a l'exterieur du gabarit : `window.open` est redirige vers
 * la page courante (pas de popup depuis un fichier local), et les images
 * distantes (QR api.qrserver.com, logo MVola, logo organisation) sont
 * remplacees par des copies locales identiques pour fonctionner hors ligne.
 */
object WebInvoicePrint {
    private const val QR_PREFIX = "https://api.qrserver.com/v1/create-qr-code/?size=140x140&margin=0&data="

    private fun resource(name: String): ByteArray =
        WebInvoicePrint::class.java.getResourceAsStream("/web-invoice/$name")?.use { it.readBytes() }
            ?: error("Gabarit de facture web absent de l'application ($name)")

    /** Objet `releve` au format attendu par renderInvoice() (cf. api_calculer_factures). */
    fun webReleve(invoice: JSONObject): JSONObject {
        val print = invoice.optJSONObject("impression")
            ?: error("Actualisez cette période : données d'impression absentes du cache")
        return JSONObject(print.toString())
            .put("detail_calcul", invoice.optJSONObject("detail") ?: JSONObject())
            .put("montant_calcule", invoice.optString("montant").toDoubleOrNull() ?: 0.0)
            .put("facture_imprimee", invoice.optBoolean("imprimee"))
            .put("date_facture", invoice.optString("mois") + "-01")
    }

    fun open(invoices: List<JSONObject>, ouvrageNom: String, organisation: JSONObject?, workDir: File) {
        workDir.mkdirs()
        val html = buildHtml(invoices, ouvrageNom, organisation, workDir)
        val file = File(workDir, "factures-${System.currentTimeMillis()}.html")
        file.writeText(html, Charsets.UTF_8)
        workDir.listFiles { f -> f.name.startsWith("factures-") && f != file && f.lastModified() < System.currentTimeMillis() - 86_400_000 }
            ?.forEach { it.delete() }
        check(Desktop.isDesktopSupported() && Desktop.getDesktop().isSupported(Desktop.Action.BROWSE)) {
            "Aucun navigateur disponible. Fichier : ${file.absolutePath}"
        }
        Desktop.getDesktop().browse(file.toURI())
    }

    /** Page autonome : gabarit web + donnees + images locales. */
    fun buildHtml(invoices: List<JSONObject>, ouvrageNom: String, organisation: JSONObject?, workDir: File): String {
        workDir.mkdirs()
        val releves = JSONArray(VolumeCacheGateway.printOrder(invoices).map(::webReleve))
        val org = JSONObject((organisation ?: JSONObject().put("nom", "HYDRIA")).toString())
        val qr = JSONObject()
        for (i in 0 until releves.length()) {
            val payload = releves.getJSONObject(i).optString("qr_payload").trim()
            if (payload.isNotEmpty()) qr.put(payload, qrDataUri(payload))
        }
        val mvola = "data:image/svg+xml;base64," + Base64.getEncoder().encodeToString(resource("mvola-logo.svg"))
        val logoUrl = org.optString("logo_url").trim()
        val logoLocal = if (logoUrl.isNotEmpty()) cachedLogo(logoUrl, workDir) else null

        val template = String(resource("print_factures_a4.js"), Charsets.UTF_8)
        return """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>Factures</title></head><body>
<script>
${template.replace("</script", "<\\/script")}
</script>
<script>
const RELEVES = ${js(releves.toString())};
const ORGANISATION = ${js(org.toString())};
const OUVRAGE = ${js(JSONObject.quote(ouvrageNom))};
const QR = ${js(qr.toString())};
const MVOLA = ${js(JSONObject.quote(mvola))};
const LOGO = ${js(JSONObject().put("from", logoUrl).put("to", logoLocal ?: logoUrl).toString())};
const QR_PREFIX = ${js(JSONObject.quote(QR_PREFIX))};


// Meme echappement que escapeHtml() du gabarit (valeurs d'attribut src).
function attr(value) {
    return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function localise(html) {
    html = html.split('/static/images/mvola-logo.svg').join(MVOLA);
    for (const [payload, uri] of Object.entries(QR)) {
        html = html.split(attr(QR_PREFIX + encodeURIComponent(payload))).join(uri);
    }
    if (LOGO.from && LOGO.to !== LOGO.from) html = html.split(attr(LOGO.from)).join(LOGO.to);
    return html;
}
let buffer = '';
window.open = function () {
    return { document: {
        open() { buffer = ''; },
        write(chunk) { buffer += chunk; },
        close() { document.open(); document.write(localise(buffer)); document.close(); },
    } };
};
window.addEventListener('load', () => imprimerFacturesCompactesA4(RELEVES, OUVRAGE, ORGANISATION));
</script>
</body></html>"""
    }

    /** JSON injecte dans un <script> : neutralise « </ ». */
    private fun js(json: String) = json.replace("</", "<\\/")

    /** Meme QR que api.qrserver.com (140x140, marge 0), genere localement. */
    private fun qrDataUri(payload: String): String {
        val matrix = QRCodeWriter().encode(payload, BarcodeFormat.QR_CODE, 140, 140, mapOf(EncodeHintType.MARGIN to 0))
        val image = BufferedImage(matrix.width, matrix.height, BufferedImage.TYPE_INT_RGB)
        for (x in 0 until matrix.width) for (y in 0 until matrix.height) image.setRGB(x, y, if (matrix[x, y]) 0x000000 else 0xFFFFFF)
        val out = ByteArrayOutputStream()
        ImageIO.write(image, "PNG", out)
        return "data:image/png;base64," + Base64.getEncoder().encodeToString(out.toByteArray())
    }

    /** Logo de l'organisation : telecharge une fois, puis reutilise hors ligne. */
    private fun cachedLogo(url: String, workDir: File): String? {
        val key = MessageDigest.getInstance("SHA-256").digest(url.toByteArray()).joinToString("") { "%02x".format(it) }.take(16)
        val cache = File(workDir, "logo-$key.bin")
        val mimeFile = File(workDir, "logo-$key.mime")
        runCatching {
            val response = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(4)).build()
                .send(HttpRequest.newBuilder(URI(url)).timeout(Duration.ofSeconds(6)).build(), HttpResponse.BodyHandlers.ofByteArray())
            if (response.statusCode() in 200..299 && response.body().isNotEmpty()) {
                cache.writeBytes(response.body())
                mimeFile.writeText(response.headers().firstValue("Content-Type").orElse("image/png").substringBefore(';'))
            }
        }
        if (!cache.isFile) return null
        val mime = mimeFile.takeIf { it.isFile }?.readText()?.ifBlank { null } ?: "image/png"
        return "data:$mime;base64," + Base64.getEncoder().encodeToString(cache.readBytes())
    }
}
