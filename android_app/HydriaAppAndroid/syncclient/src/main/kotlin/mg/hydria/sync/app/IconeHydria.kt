package mg.hydria.sync.app

import java.awt.BasicStroke
import java.awt.Color
import java.awt.RenderingHints
import java.awt.geom.Arc2D
import java.awt.geom.Ellipse2D
import java.awt.geom.Path2D
import java.awt.image.BufferedImage
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.nio.file.Files
import java.nio.file.Path
import javax.imageio.ImageIO
import kotlin.math.cos
import kotlin.math.sin

/**
 * Icone de l'application dessinee par code (aucun fichier image a maintenir) : un disque avec deux fleches
 * circulaires de synchronisation. La couleur du disque dit l'etat, l'angle des fleches permet de la faire tourner
 * pendant une synchronisation. Sert pour la zone de notification, la fenetre et le fichier `.ico` de l'installateur.
 */
object IconeHydria {
    enum class Etat(val fond: Color) {
        OK(Color(0xFF0B6FA4.toInt())),
        EN_COURS(Color(0xFF0B6FA4.toInt())),
        ATTENTION(Color(0xFFE65100.toInt())),
        ERREUR(Color(0xFFC62828.toInt())),
    }

    /** Nombre d'images d'un tour complet (tour de 360 degres pendant une synchronisation). */
    const val IMAGES_PAR_TOUR = 12

    fun dessiner(taille: Int, etat: Etat = Etat.OK, angleDegres: Double = 0.0): BufferedImage {
        val image = BufferedImage(taille, taille, BufferedImage.TYPE_INT_ARGB)
        val g = image.createGraphics()
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g.setRenderingHint(RenderingHints.KEY_STROKE_CONTROL, RenderingHints.VALUE_STROKE_PURE)
        val t = taille.toDouble()

        g.color = etat.fond
        g.fill(Ellipse2D.Double(t * 0.03, t * 0.03, t * 0.94, t * 0.94))

        val c = t / 2
        val rayon = t * 0.27
        g.rotate(Math.toRadians(angleDegres), c, c)
        g.color = Color.WHITE
        g.stroke = BasicStroke((t * 0.095).toFloat(), BasicStroke.CAP_BUTT, BasicStroke.JOIN_ROUND)
        for (depart in listOf(25.0, 205.0)) {
            val etendue = 125.0
            g.draw(Arc2D.Double(c - rayon, c - rayon, rayon * 2, rayon * 2, depart, etendue, Arc2D.OPEN))
            fleche(g, c, rayon, Math.toRadians(depart + etendue), t)
        }
        g.dispose()
        return image
    }

    /** Pointe de fleche au bout d'un arc parcouru dans le sens trigonometrique. */
    private fun fleche(g: java.awt.Graphics2D, c: Double, rayon: Double, theta: Double, t: Double) {
        val px = c + rayon * cos(theta)
        val py = c - rayon * sin(theta)
        val dx = -sin(theta)
        val dy = -cos(theta)
        val longueur = t * 0.17
        val demiLargeur = t * 0.12
        val triangle = Path2D.Double().apply {
            moveTo(px + dx * longueur, py + dy * longueur)
            lineTo(px - dy * demiLargeur, py + dx * demiLargeur)
            lineTo(px + dy * demiLargeur, py - dx * demiLargeur)
            closePath()
        }
        g.fill(triangle)
    }

    /** Fichier `.ico` multi-tailles (images PNG integrees, lues par Windows depuis Vista). */
    fun ecrireIco(destination: Path, tailles: List<Int> = listOf(16, 24, 32, 48, 64, 128, 256)) {
        val images = tailles.map { taille ->
            ByteArrayOutputStream().also { ImageIO.write(dessiner(taille), "png", it) }.toByteArray()
        }
        val sortie = ByteArrayOutputStream()
        DataOutputStream(sortie).use { out ->
            fun mot(v: Int) { out.writeByte(v and 0xFF); out.writeByte((v shr 8) and 0xFF) }
            fun double(v: Int) { mot(v and 0xFFFF); mot((v shr 16) and 0xFFFF) }
            mot(0); mot(1); mot(tailles.size)
            var decalage = 6 + 16 * tailles.size
            tailles.forEachIndexed { i, taille ->
                out.writeByte(if (taille >= 256) 0 else taille); out.writeByte(if (taille >= 256) 0 else taille)
                out.writeByte(0); out.writeByte(0)
                mot(1); mot(32)
                double(images[i].size); double(decalage)
                decalage += images[i].size
            }
            images.forEach { out.write(it) }
        }
        destination.parent?.let { Files.createDirectories(it) }
        Files.write(destination, sortie.toByteArray())
    }
}

/** `gradlew :syncclient:genererIcone` : (re)cree `packaging/hydria-sync.ico` utilise par l'installateur. */
object GenererIcone {
    @JvmStatic
    fun main(args: Array<String>) {
        val cible = Path.of(args.firstOrNull() ?: "packaging/hydria-sync.ico")
        IconeHydria.ecrireIco(cible)
        println("Icone ecrite : ${cible.toAbsolutePath()}")
    }
}
