package mg.hydria.sync.app

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.ImageComposeScene
import androidx.compose.ui.unit.Density
import mg.hydria.sync.core.Config
import org.jetbrains.skia.EncodedImageFormat
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.file.Files
import java.nio.file.Path
import java.time.LocalDateTime
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PreferencesTest {
    private val dossier: Path = Files.createTempDirectory("hydria-prefs-")

    @Test
    fun `sans fichier les reglages sont vides`() {
        assertEquals(Preferences(), Preferences.charger(dossier))
        assertNull(Preferences.charger(dossier).sombre)
    }

    @Test
    fun `les reglages sont conserves`() {
        Preferences(sombre = true, demarrageWindows = false).enregistrer(dossier)
        val relus = Preferences.charger(dossier)
        assertEquals(true, relus.sombre)
        assertEquals(false, relus.demarrageWindows)
    }

    @Test
    fun `un fichier abime ne bloque pas le demarrage`() {
        Files.writeString(dossier.resolve("preferences.json"), "{ pas du json")
        assertEquals(Preferences(), Preferences.charger(dossier))
    }

    @Test
    fun `le theme de Windows est lu dans la sortie de reg`() {
        val sombre = "HKEY_CURRENT_USER\\...\\Personalize\n    AppsUseLightTheme    REG_DWORD    0x0\n"
        val clair = "HKEY_CURRENT_USER\\...\\Personalize\n    AppsUseLightTheme    REG_DWORD    0x1\n"
        assertTrue(ThemeSysteme.sombreDepuis(sombre))
        assertFalse(ThemeSysteme.sombreDepuis(clair))
        assertFalse(ThemeSysteme.sombreDepuis("ERREUR : introuvable"))
    }
}

class DemarrageWindowsTest {
    private val windows = System.getProperty("os.name").startsWith("Windows")
    // Cle de test : le vrai demarrage de l'utilisateur n'est jamais touche.
    private val cle = "HKCU\\Software\\HydriaSyncTest"
    private val nom = "EssaiDemarrage"

    @Test
    fun `la commande enregistree protege les espaces du chemin`() {
        assertEquals("\"C:\\Users\\Dir Soakoja\\AppData\\Local\\Programs\\HydriaSync\\HydriaSync.exe\" --minimise",
            DemarrageWindows.commande("C:\\Users\\Dir Soakoja\\AppData\\Local\\Programs\\HydriaSync\\HydriaSync.exe"))
    }

    @Test
    fun `activer puis desactiver dans le registre`() {
        if (!windows) return
        val exe = "C:\\Users\\Dir Soakoja\\AppData\\Local\\Programs\\HydriaSync\\HydriaSync.exe"
        try {
            assertFalse(DemarrageWindows.estActif(cle, nom))
            assertTrue(DemarrageWindows.activer(exe, cle, nom))
            assertTrue(DemarrageWindows.estActif(cle, nom))
            assertEquals(DemarrageWindows.commande(exe), DemarrageWindows.valeur(cle, nom))
            assertTrue(DemarrageWindows.desactiver(cle, nom))
            assertFalse(DemarrageWindows.estActif(cle, nom))
        } finally {
            ProcessBuilder("reg", "delete", cle, "/f").redirectErrorStream(true).start().also { it.inputStream.readBytes() }.waitFor()
        }
    }

    @Test
    fun `desactiver sans entree reussit`() {
        if (!windows) return
        assertTrue(DemarrageWindows.desactiver(cle, "N-existe-pas"))
    }

    @Test
    fun `hors de l'application installee le reglage est indisponible`() {
        // Les tests tournent sous java.exe, pas sous HydriaSync.exe.
        assertNull(DemarrageWindows.cheminExecutable())
    }
}

class InstanceUniqueTest {
    private val dossier: Path = Files.createTempDirectory("hydria-instance-")

    @Test
    fun `une seconde instance est refusee puis acceptee apres liberation`() {
        assertTrue(InstanceUnique.obtenir(dossier))
        try {
            assertFalse(InstanceUnique.obtenir(dossier), "la seconde instance doit se fermer")
        } finally {
            InstanceUnique.liberer()
        }
        assertTrue(InstanceUnique.obtenir(dossier), "le verrou est reutilisable une fois libere")
        InstanceUnique.liberer()
    }

    @Test
    fun `la demande d'ouverture est consommee une seule fois`() {
        assertFalse(InstanceUnique.ouvertureDemandee(dossier))
        InstanceUnique.demanderOuverture(dossier)
        assertTrue(InstanceUnique.ouvertureDemandee(dossier))
        assertFalse(InstanceUnique.ouvertureDemandee(dossier))
    }
}

class IconeHydriaTest {
    @Test
    fun `l'icone est dessinee et tourne`() {
        val a = IconeHydria.dessiner(64, IconeHydria.Etat.EN_COURS, 0.0)
        val b = IconeHydria.dessiner(64, IconeHydria.Etat.EN_COURS, 30.0)
        assertEquals(64, a.width)
        assertEquals(0, a.getRGB(0, 0) ushr 24, "les coins sont transparents (disque)")
        assertNotEquals(a.getRGB(20, 20), 0)
        val different = (0 until 64).any { x -> (0 until 64).any { y -> a.getRGB(x, y) != b.getRGB(x, y) } }
        assertTrue(different, "deux angles donnent deux images")
    }

    @Test
    fun `chaque etat a sa couleur`() {
        val couleurs = IconeHydria.Etat.entries.map { IconeHydria.dessiner(32, it).getRGB(4, 16) }.toSet()
        assertTrue(couleurs.size >= 3, "OK/EN_COURS partagent le bleu, attention et erreur se distinguent")
    }

    @Test
    fun `le fichier ico est valide`() {
        val fichier = Files.createTempDirectory("hydria-ico-").resolve("hydria-sync.ico")
        IconeHydria.ecrireIco(fichier, listOf(16, 32, 256))
        val octets = ByteBuffer.wrap(Files.readAllBytes(fichier)).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(0, octets.getShort(0).toInt(), "reserve")
        assertEquals(1, octets.getShort(2).toInt(), "type icone")
        assertEquals(3, octets.getShort(4).toInt(), "nombre d'images")
        assertEquals(16, octets.get(6).toInt())
        assertEquals(0, octets.get(6 + 32).toInt(), "256 px s'ecrit 0")
        // chaque entree pointe sur une image PNG
        for (i in 0 until 3) {
            val taille = octets.getInt(6 + 16 * i + 8)
            val decalage = octets.getInt(6 + 16 * i + 12)
            assertEquals(0x89.toByte(), octets.get(decalage), "entree $i : signature PNG")
            assertEquals('P'.code.toByte(), octets.get(decalage + 1))
            assertTrue(taille > 100 && decalage + taille <= octets.limit())
        }
    }
}

/** Captures du mode sombre (et de l'icone) : verifie qu'ils se composent ; PNG ecrits si HYDRIA_CAPTURES est defini. */
@OptIn(ExperimentalComposeUiApi::class)
class CapturesModeSombreTest {
    private val config = Config(baseUrl = "https://www.hydria.mg", root = "C:\\Users\\agent\\Hydria", username = "agent", refreshToken = "R")
    private val sortie: Path = System.getenv("HYDRIA_CAPTURES")?.let { Path.of(it) } ?: Files.createTempDirectory("hydria-captures-")

    private fun capturer(nom: String, contenu: @androidx.compose.runtime.Composable () -> Unit) {
        val scene = ImageComposeScene(width = 980, height = 720, density = Density(1f)) { contenu() }
        try {
            val png = scene.render().encodeToData(EncodedImageFormat.PNG)!!.bytes
            Files.createDirectories(sortie)
            Files.write(sortie.resolve("$nom.png"), png)
            assertTrue(png.size > 5_000, "$nom : image vide ?")
        } finally {
            scene.close()
        }
    }

    private fun sombre(contenu: @androidx.compose.runtime.Composable () -> Unit): @androidx.compose.runtime.Composable () -> Unit = {
        CompositionLocalProvider(LocalSombre provides true) {
            androidx.compose.material3.MaterialTheme(colorScheme = ThemeHydriaSombre) {
                androidx.compose.material3.Surface(color = androidx.compose.material3.MaterialTheme.colorScheme.background) { contenu() }
            }
        }
    }

    private fun controleur() = SyncController(dossierConfig = Files.createTempDirectory("hydria-cfg-"))

    @Test
    fun `principal sombre avec conflit et option de demarrage`() {
        val c = controleur()
        val etat = EtatUi(
            config = config, derniereSynchro = LocalDateTime.of(2026, 10, 26, 14, 40, 0), auto = true,
            resume = ResumeUi(1, 0, 0, 0), message = "Serveur injoignable : connexion refusée",
            conflits = listOf(ConflitUi("id-1", "Territoire/Ouvrage A/Dossier technique/Fiche A.xlsx", "Territoire/Ouvrage A/Dossier technique/Fiche A (conflit serveur v2).xlsx")),
            erreurs = listOf("Fiche B.xlsx : refusé par le serveur"),
        )
        capturer("7-sombre-principal", sombre { EcranPrincipal(etat, c, OptionsUi(sombre = true, demarrageWindows = true)) })
    }

    @Test
    fun `connexion sombre`() {
        val c = controleur()
        capturer("8-sombre-connexion", sombre { EcranConnexion(EtatUi(message = "Connexion refusée : Identifiants invalides."), c, memorisee = null) })
    }

    @Test
    fun `planche des icones`() {
        val planche = java.awt.image.BufferedImage(4 * 72, 72, java.awt.image.BufferedImage.TYPE_INT_ARGB)
        val g = planche.createGraphics()
        g.color = java.awt.Color(0x20, 0x28, 0x30); g.fillRect(0, 0, planche.width, planche.height)
        listOf(IconeHydria.Etat.OK, IconeHydria.Etat.EN_COURS, IconeHydria.Etat.ATTENTION, IconeHydria.Etat.ERREUR).forEachIndexed { i, e ->
            g.drawImage(IconeHydria.dessiner(64, e, if (e == IconeHydria.Etat.EN_COURS) 40.0 else 0.0), 4 + i * 72, 4, null)
        }
        g.dispose()
        Files.createDirectories(sortie)
        javax.imageio.ImageIO.write(planche, "png", sortie.resolve("9-icones.png").toFile())
    }
}
