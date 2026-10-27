package mg.hydria.sync.core

import kotlinx.coroutines.runBlocking
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ProgressionTest {
    private fun reception(fait: Long, total: Long, debut: Long = 0, maintenant: Long = 0) =
        Progression(Phase.RECEPTION, fait = 1, total = 2, octetsFaits = fait, octetsTotal = total, debutMs = debut, maintenantMs = maintenant)

    @Test
    fun `la fraction suit les octets et reste entre 0 et 1`() {
        assertEquals(0.25f, reception(25, 100).fraction)
        assertEquals(1f, reception(150, 100).fraction)
        assertNull(reception(0, 0).fraction, "pas de total : indetermine")
        assertNull(Progression(Phase.ENVOI, envoyes = 3).fraction)
        assertEquals(25, reception(25, 100).pourcentage)
    }

    @Test
    fun `le temps restant vient de la vitesse moyenne et attend un peu de recul`() {
        // 100 octets en 10 s, il en reste 300 : 30 s
        assertEquals(30L, reception(100, 400, debut = 0, maintenant = 10_000).restantSecondes)
        assertNull(reception(100, 400, debut = 0, maintenant = 1_000).restantSecondes, "moins de 3 s : estimation peu fiable")
        assertNull(reception(0, 400, debut = 0, maintenant = 10_000).restantSecondes, "rien recu encore")
        assertNull(Progression(Phase.ENVOI).restantSecondes)
    }

    @Test
    fun `les octets et les durees sont lisibles`() {
        assertEquals("12 octets", formaterOctets(12))
        assertEquals("12 Ko", formaterOctets(12 * 1024))
        assertEquals("1,5 Mo", formaterOctets(1_572_864))
        assertEquals("657 Mo", formaterOctets(657L * 1024 * 1024))
        assertEquals("1,4 Go", formaterOctets((1.4 * 1024 * 1024 * 1024).toLong()))
        assertEquals("moins d'une minute", formaterDuree(40))
        assertEquals("12 min", formaterDuree(12 * 60))
        assertEquals("1 h 05", formaterDuree(3900))
    }

    @Test
    fun `le libelle dit ou on en est`() {
        assertEquals("Recherche des changements…", Progression(Phase.PREPARATION).libelle())
        assertEquals("Réception : 340 sur 1052 fichiers (32 %)",
            Progression(Phase.RECEPTION, fait = 340, total = 1052, octetsFaits = 32, octetsTotal = 100).libelle())
        assertEquals("Envoi : 1 fichier", Progression(Phase.ENVOI, envoyes = 1).libelle())
        assertEquals("Envoi : 3 fichiers", Progression(Phase.ENVOI, envoyes = 3).libelle())
    }
}

class ProgressionMoteurTest {
    private lateinit var racine: Path
    private lateinit var serveur: FauxServeur
    private val config = Config(baseUrl = "https://hydria.test", root = "", username = "agent", deviceLabel = "PC test", protegerArborescence = false)

    @BeforeTest
    fun preparer() {
        racine = Files.createTempDirectory("hydria-progression-")
        serveur = FauxServeur()
    }

    @AfterTest
    fun nettoyer() {
        racine.toFile().deleteRecursively()
    }

    private fun synchroniser(): List<Progression> {
        val vues = mutableListOf<Progression>()
        runBlocking { SyncEngine(serveur.api(), racine, config, progression = { vues += it }).synchroniser() }
        return vues
    }

    @Test
    fun `le total est annonce avant le premier telechargement puis chaque fichier avance`() {
        serveur.nouveau("A.xlsx", "aaaa".toByteArray(), "dossier_technique", "ouvrage", "o1")
        serveur.nouveau("B.xlsx", "bbbbbbbb".toByteArray(), "dossier_technique", "ouvrage", "o1")
        serveur.nouveau("C.xlsx", "cc".toByteArray(), "dossier_technique", "ouvrage", "o1")

        val vues = synchroniser()

        assertEquals(Phase.PREPARATION, vues.first().phase)
        val receptions = vues.filter { it.phase == Phase.RECEPTION }
        val annonce = receptions.first()
        assertEquals(3, annonce.total, "le nombre de fichiers est connu des le debut")
        assertEquals(14L, annonce.octetsTotal)
        assertEquals(0, annonce.fait)
        val derniere = receptions.last()
        assertEquals(3, derniere.fait)
        assertEquals(14L, derniere.octetsFaits)
        assertEquals(1f, derniere.fraction)
        assertTrue(receptions.map { it.fait }.zipWithNext().all { (a, b) -> b >= a }, "le compteur ne recule jamais")
        assertNotNull(receptions.firstOrNull { it.courant == "A.xlsx" || it.courant == "B.xlsx" || it.courant == "C.xlsx" })
    }

    @Test
    fun `une deuxieme synchronisation annonce zero fichier a recevoir`() {
        serveur.nouveau("A.xlsx", "aaaa".toByteArray(), "dossier_technique", "ouvrage", "o1")
        synchroniser()

        val annonce = synchroniser().first { it.phase == Phase.RECEPTION }

        assertEquals(0, annonce.total)
        assertNull(annonce.fraction)
    }
}
