package mg.hydria.sync.app

import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.ImageComposeScene
import androidx.compose.ui.unit.Density
import mg.hydria.sync.core.Config
import org.jetbrains.skia.EncodedImageFormat
import java.nio.file.Files
import java.nio.file.Path
import java.time.LocalDateTime
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Dessine les ecrans hors fenetre (ImageComposeScene) : verifie qu'ils se composent sans erreur et, si la
 * variable HYDRIA_CAPTURES est definie, ecrit des PNG pour un controle visuel.
 */
@OptIn(ExperimentalComposeUiApi::class)
class CapturesEcransTest {
    private val config = Config(
        baseUrl = "https://www.hydria.mg", root = "C:\\Users\\agent\\Hydria", username = "agent", refreshToken = "R",
    )
    private val sortie: Path = System.getenv("HYDRIA_CAPTURES")?.let { Path.of(it) } ?: Files.createTempDirectory("hydria-captures-")

    private fun controleur() = SyncController(dossierConfig = Files.createTempDirectory("hydria-cfg-"))

    private fun capturer(nom: String, largeur: Int = 980, hauteur: Int = 720, contenu: @androidx.compose.runtime.Composable () -> Unit) {
        val scene = ImageComposeScene(width = largeur, height = hauteur, density = Density(1f)) { contenu() }
        try {
            val image = scene.render()
            val png = image.encodeToData(EncodedImageFormat.PNG)!!.bytes
            Files.createDirectories(sortie)
            Files.write(sortie.resolve("$nom.png"), png)
            assertTrue(png.size > 5_000, "$nom : image vide ?")
        } finally {
            scene.close()
        }
    }

    private fun themed(contenu: @androidx.compose.runtime.Composable () -> Unit): @androidx.compose.runtime.Composable () -> Unit = {
        androidx.compose.material3.MaterialTheme(colorScheme = ThemeHydria) {
            androidx.compose.material3.Surface(color = androidx.compose.material3.MaterialTheme.colorScheme.background) { contenu() }
        }
    }

    @Test
    fun `ecran de connexion`() {
        val c = controleur()
        capturer("1-connexion", 980, 760, themed { EcranConnexion(EtatUi(), c, memorisee = null) })
    }

    @Test
    fun `ecran de connexion avec une erreur`() {
        val c = controleur()
        capturer("2-connexion-erreur", 980, 760, themed {
            EcranConnexion(EtatUi(message = "Connexion refusée : Identifiants invalides."), c, memorisee = config)
        })
    }

    @Test
    fun `ecran principal a jour`() {
        val c = controleur()
        val etat = EtatUi(
            config = config, derniereSynchro = LocalDateTime.of(2026, 10, 26, 14, 32, 5), auto = true, intervalleMinutes = 5,
            resume = ResumeUi(telecharges = 975, envoyes = 2, misAJour = 1, corbeille = 0),
            journal = listOf("14:32:05  ↓ Territoire/Analanjirofo/…/Ouvrage A/Dossier technique/Fiche A.xlsx", "14:32:04  Connecté en tant que agent."),
        )
        capturer("3-principal-a-jour", contenu = themed { EcranPrincipal(etat, c) })
    }

    @Test
    fun `ecran principal avec un conflit`() {
        val c = controleur()
        val etat = EtatUi(
            config = config, derniereSynchro = LocalDateTime.of(2026, 10, 26, 14, 40, 0), auto = true,
            resume = ResumeUi(1, 0, 0, 0),
            conflits = listOf(
                ConflitUi(
                    "id-1",
                    "Territoire/Analanjirofo/Soanierana/Ampasina/Fkt 1/Village 1/Ouvrage A/Dossier technique/Fiche A.xlsx",
                    "Territoire/Analanjirofo/Soanierana/Ampasina/Fkt 1/Village 1/Ouvrage A/Dossier technique/Fiche A (conflit serveur v2).xlsx",
                ),
            ),
        )
        capturer("4-principal-conflit", contenu = themed { EcranPrincipal(etat, c) })
    }

    @Test
    fun `ecran principal en cours et en erreur`() {
        val c = controleur()
        capturer("5-principal-en-cours", contenu = themed { EcranPrincipal(EtatUi(config = config, enCours = true, auto = true), c) })
        val etat = EtatUi(
            config = config, derniereSynchro = LocalDateTime.of(2026, 10, 26, 14, 40, 0), message = "Serveur injoignable : connexion refusée",
            erreurs = listOf("Fiche B.xlsx : refusé par le serveur (TYPE_FICHIER_INCOHERENT)"),
            ignores = listOf("brouillon.txt : emplacement non reconnu, non synchronisé."),
        )
        capturer("6-principal-erreur", contenu = themed { EcranPrincipal(etat, c) })
    }
}
