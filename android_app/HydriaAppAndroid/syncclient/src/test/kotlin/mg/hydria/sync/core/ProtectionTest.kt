package mg.hydria.sync.core

import kotlinx.coroutines.runBlocking
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * Les permissions NTFS ne se testent que sur NTFS : ailleurs ces tests ne font rien. Les dossiers de test sont crees dans
 * le profil de l'utilisateur (comme le vrai dossier Hydria) : leurs droits heritent du controle total du profil, ce
 * qui compte (voir Protection). Ils sont supprimes a la fin de chaque test.
 */
class ProtectionTest {
    private lateinit var base: Path

    @BeforeTest
    fun preparer() {
        base = Files.createTempDirectory(Path.of(System.getProperty("user.home")), "hydria-protection-")
    }

    @AfterTest
    fun nettoyer() {
        Protection.leverTout(base)
        base.toFile().deleteRecursively()
    }

    private fun ntfs() = Protection.disponible(base)

    @Test
    fun `verrouiller est idempotent et se leve`() {
        if (!ntfs()) return
        val d = Files.createDirectories(base.resolve("Territoire/Ouvrage"))
        assertFalse(Protection.estVerrouille(d))
        assertTrue(Protection.verrouiller(d))
        assertTrue(Protection.verrouiller(d), "deuxieme pose sans effet")
        assertTrue(Protection.estVerrouille(d))
        assertTrue(Protection.deverrouiller(d))
        assertFalse(Protection.estVerrouille(d))
        assertFalse(Protection.deverrouiller(d), "rien a lever")
    }

    @Test
    fun `les dossiers verrouilles refusent suppression renommage et deplacement mais acceptent les fichiers`() {
        if (!ntfs()) return
        val racine = Files.createDirectories(base.resolve("Hydria"))
        val ouvrage = Files.createDirectories(racine.resolve("Territoire/Ouvrage"))
        val categorie = Files.createDirectories(ouvrage.resolve("Dossier technique"))
        val photos = Files.createDirectories(ouvrage.resolve("Photos"))
        val fiche = categorie.resolve("fiche.xlsx")
        Files.writeString(fiche, "v1")
        for (d in listOf(racine, racine.resolve("Territoire"), ouvrage, categorie, photos)) Protection.verrouiller(d)

        // dossiers : tout est refuse
        assertFailsWith<java.io.IOException>("supprimer un dossier vide") { Files.delete(photos) }
        assertFailsWith<java.io.IOException>("renommer un dossier") { Files.move(categorie, ouvrage.resolve("Dossier technique 2")) }
        assertFailsWith<java.io.IOException>("deplacer un dossier") { Files.move(photos, categorie.resolve("Photos")) }
        assertFailsWith<java.io.IOException>("renommer un dossier qui contient des dossiers") { Files.move(ouvrage, racine.resolve("Ouvrage 2")) }
        assertTrue(Files.isDirectory(categorie) && Files.isDirectory(photos) && Files.isDirectory(ouvrage))

        // fichiers : creer, modifier et enregistrer comme Word/Excel (temporaire renomme par-dessus) restent possibles
        Files.writeString(categorie.resolve("neuf.txt"), "n")
        Files.createDirectory(categorie.resolve("sous-dossier"))
        Files.writeString(fiche, "v2")
        val temporaire = categorie.resolve("~fiche.tmp")
        Files.writeString(temporaire, "v3")
        Files.move(temporaire, fiche, StandardCopyOption.REPLACE_EXISTING)
        assertEquals("v3", Files.readString(fiche))
        assertEquals("v3", Files.readString(fiche), "lecture toujours possible")
    }

    @Test
    fun `sansVerrou leve le verrou le temps du bloc puis le repose`() {
        if (!ntfs()) return
        val d = Files.createDirectories(base.resolve("A/B"))
        Protection.verrouiller(d)
        Protection.sansVerrou(d) {
            assertFalse(Protection.estVerrouille(d))
            Files.move(d, base.resolve("A/C"))
        }
        // le dossier a ete renomme pendant le bloc : l'ancien chemin n'existe plus, rien n'est reverrouille a tort
        assertFalse(Files.exists(d))
        val d2 = Files.createDirectories(base.resolve("A/D"))
        Protection.verrouiller(d2)
        Protection.sansVerrou(d2) { assertFalse(Protection.estVerrouille(d2)) }
        assertTrue(Protection.estVerrouille(d2))
    }

    @Test
    fun `leverTout deverrouille tout l'arbre et compte les dossiers`() {
        if (!ntfs()) return
        val dossiers = listOf("A", "A/B", "A/B/C", "D").map { Files.createDirectories(base.resolve(it)) }
        dossiers.forEach { Protection.verrouiller(it) }
        assertEquals(4, Protection.leverTout(base))
        assertTrue(dossiers.none { Protection.estVerrouille(it) })
        assertEquals(0, Protection.leverTout(base), "deuxieme passe : rien a lever")
    }

    @Test
    fun `la commande icacls du README leve les verrous quand l'application n'est plus la`() {
        if (!ntfs()) return
        val dossiers = listOf("A", "A/B", "A/B/C").map { Files.createDirectories(base.resolve(it)) }
        dossiers.forEach { Protection.verrouiller(it) }
        assertTrue(dossiers.all { Protection.estVerrouille(it) })

        // commande de secours documentee : icacls "<dossier>" /remove:d "<utilisateur>" /t /c
        val processus = ProcessBuilder("icacls", base.toString(), "/remove:d", System.getProperty("user.name"), "/t", "/c")
            .redirectErrorStream(true).start()
        processus.inputStream.readBytes()
        assertEquals(0, processus.waitFor())

        assertTrue(dossiers.none { Protection.estVerrouille(it) }, "les refus ont ete retires")
        Files.delete(dossiers.last()) // et le dossier se supprime de nouveau
    }

    @Test
    fun `un dossier absent ou un fichier n'est pas verrouillable`() {
        if (!ntfs()) return
        val fichier = base.resolve("f.txt").also { Files.writeString(it, "x") }
        assertFalse(Protection.verrouiller(fichier), "les fichiers restent libres (enregistrement Office)")
        assertFalse(Protection.verrouiller(base.resolve("absent")))
        assertEquals(0, Protection.leverTout(base.resolve("absent")))
    }

    @Test
    fun `verrouiller beaucoup de dossiers reste rapide`() {
        if (!ntfs()) return
        val dossiers = (1..2000).map { Files.createDirectories(base.resolve("o$it/Dossier technique")) }
        val debut = System.currentTimeMillis()
        dossiers.forEach { Protection.verrouiller(it) }
        val verrouille = System.currentTimeMillis() - debut
        val debut2 = System.currentTimeMillis()
        dossiers.forEach { Protection.verrouiller(it) } // relecture seule
        val relecture = System.currentTimeMillis() - debut2
        println("[perf] 2000 dossiers : pose $verrouille ms, relecture $relecture ms")
        assertTrue(verrouille < 60_000, "pose trop lente : $verrouille ms")
        assertEquals(2000, Protection.leverTout(base))
    }
}

class ProtectionMoteurTest {
    private lateinit var racine: Path
    private lateinit var serveur: FauxServeur
    private val protege = Config(baseUrl = "https://hydria.test", root = "", username = "agent", deviceLabel = "PC test")
    private val libre = protege.copy(protegerArborescence = false)
    private val dossier get() = racine.resolve("$DOSSIER_OUVRAGE/Dossier technique")
    private val fiche get() = "$DOSSIER_OUVRAGE/Dossier technique/Fiche A.xlsx"

    @BeforeTest
    fun preparer() {
        racine = Files.createTempDirectory(Path.of(System.getProperty("user.home")), "hydria-protection-moteur-")
        serveur = FauxServeur()
    }

    @AfterTest
    fun nettoyer() {
        Protection.leverTout(racine)
        racine.toFile().deleteRecursively()
    }

    private fun synchroniser(cfg: Config = protege): Rapport = runBlocking { SyncEngine(serveur.api(), racine, cfg).synchroniser() }
    private fun lire(rel: String) = Files.readString(racine.resolve(rel))
    private fun existe(rel: String) = Files.exists(racine.resolve(rel))
    private fun ntfs() = Protection.disponible(racine.also { Files.createDirectories(it) })
    private fun ajouter(contenu: String = "AAA", nom: String = "Fiche A.xlsx") =
        serveur.nouveau(nom, contenu.toByteArray(), "dossier_technique", "ouvrage", "o1")

    // ------------------------------------------------------------------ verrou

    @Test
    fun `apres la synchronisation les dossiers de l'arborescence sont verrouilles`() {
        if (!ntfs()) return
        ajouter()
        synchroniser()
        assertTrue(Protection.estVerrouille(dossier), "dossier de categorie")
        assertTrue(Protection.estVerrouille(racine.resolve(DOSSIER_OUVRAGE)), "dossier d'ouvrage")
        assertTrue(Protection.estVerrouille(racine), "racine")
        assertFailsWith<java.io.IOException> { Files.move(dossier, dossier.resolveSibling("Renomme")) }
        assertFalse(Protection.estVerrouille(racine.resolve(".hydria-sync")), "le dossier interne de l'application reste libre")
    }

    @Test
    fun `le serveur peut modifier renommer et supprimer malgre le verrou`() {
        if (!ntfs()) return
        val f = ajouter("v1")
        synchroniser()
        serveur.modifier(f.id, "v2".toByteArray())
        assertEquals(1, synchroniser().telecharges)
        assertEquals("v2", lire(fiche))

        serveur.modifier(f.id, null, nom = "Fiche B.xlsx")
        synchroniser()
        assertEquals("v2", lire("$DOSSIER_OUVRAGE/Dossier technique/Fiche B.xlsx"))
        assertFalse(existe(fiche))

        serveur.supprimer(f.id)
        assertEquals(1, synchroniser().corbeille)
        assertTrue(Protection.estVerrouille(dossier), "le dossier reste verrouille")
    }

    // ------------------------------------------------------------------ retablissement

    @Test
    fun `un fichier supprime est retelecharge`() {
        ajouter("contenu serveur")
        synchroniser()
        Files.delete(racine.resolve(fiche))
        val avant = serveur.telechargements()

        val rapport = synchroniser()

        assertEquals("contenu serveur", lire(fiche))
        assertEquals(1, rapport.retablis)
        assertEquals(avant + 1, serveur.telechargements())
        assertTrue(rapport.ignores.none { "supprimé ici" in it }, rapport.ignores.toString())
        assertTrue(rapport.propre, rapport.erreurs.toString())
        assertEquals(0, synchroniser().retablis, "stable : plus rien a retablir")
    }

    @Test
    fun `un fichier deplace est remis a sa place sans etre retelecharge ni envoye`() {
        ajouter("contenu")
        synchroniser()
        val ailleurs = racine.resolve("Mes documents/Fiche A.xlsx")
        Files.createDirectories(ailleurs.parent)
        Files.move(racine.resolve(fiche), ailleurs)
        val avant = serveur.telechargements()

        val rapport = synchroniser()

        assertEquals("contenu", lire(fiche))
        assertFalse(Files.exists(ailleurs))
        assertEquals(1, rapport.retablis)
        assertEquals(avant, serveur.telechargements(), "reconnu par son empreinte : aucun telechargement")
        assertEquals(0, rapport.envoyes, "rien n'est envoye au serveur")
    }

    @Test
    fun `un fichier renomme retrouve son nom`() {
        ajouter("contenu")
        synchroniser()
        Files.move(racine.resolve(fiche), dossier.resolve("mon nom a moi.xlsx"))

        val rapport = synchroniser()

        assertEquals("contenu", lire(fiche))
        assertFalse(Files.exists(dossier.resolve("mon nom a moi.xlsx")))
        assertEquals(1, rapport.retablis)
        assertEquals(0, rapport.envoyes)
    }

    @Test
    fun `un fichier modifie puis deplace laisse la version du serveur en place sans envoyer la copie`() {
        ajouter("version du serveur")
        synchroniser()
        val ailleurs = racine.resolve("Bureau/Fiche A.xlsx")
        Files.createDirectories(ailleurs.parent)
        Files.move(racine.resolve(fiche), ailleurs)
        Files.writeString(ailleurs, "ma version modifiee")

        val rapport = synchroniser()

        assertEquals("version du serveur", lire(fiche), "l'original est retabli depuis le serveur")
        assertEquals("ma version modifiee", Files.readString(ailleurs), "la copie modifiee de l'utilisateur n'est pas touchee")
        assertEquals(0, rapport.envoyes)
        assertEquals(1, rapport.retablis)
    }

    @Test
    fun `un dossier renomme est remis en ordre et l'ancien nom disparait`() {
        if (!ntfs()) return
        ajouter("contenu")
        synchroniser()
        // un administrateur leve le verrou puis renomme le dossier
        Protection.deverrouiller(dossier)
        val renomme = dossier.resolveSibling("Dossier technique 2")
        Files.move(dossier, renomme)

        val rapport = synchroniser()

        assertEquals("contenu", lire(fiche))
        assertFalse(Files.exists(renomme), "l'ancien nom (vide) est supprime")
        assertEquals(1, rapport.retablis)
        assertTrue(Protection.estVerrouille(dossier), "le verrou est repose")
    }

    @Test
    fun `un dossier renomme qui contient un fichier de l'utilisateur est conserve`() {
        if (!ntfs()) return
        ajouter("contenu")
        synchroniser()
        Protection.deverrouiller(dossier)
        val renomme = dossier.resolveSibling("Dossier technique 2")
        Files.move(dossier, renomme)
        Files.writeString(renomme.resolve("mes notes.txt"), "a moi")

        synchroniser()

        assertEquals("contenu", lire(fiche))
        assertEquals("a moi", Files.readString(renomme.resolve("mes notes.txt")), "un fichier de l'utilisateur n'est jamais supprime")
    }

    @Test
    fun `un dossier supprime est recree avec ses fichiers`() {
        if (!ntfs()) return
        ajouter("contenu")
        synchroniser()
        Protection.deverrouiller(dossier)
        Files.delete(racine.resolve(fiche))
        Files.delete(dossier)

        val rapport = synchroniser()

        assertEquals("contenu", lire(fiche))
        assertEquals(1, rapport.retablis)
        assertTrue(Protection.estVerrouille(dossier))
    }

    @Test
    fun `tout le dossier supprime est reconstruit et retelecharge`() {
        ajouter("un")
        ajouter("deux", "Fiche B.xlsx")
        synchroniser()
        Protection.leverTout(racine)
        racine.toFile().deleteRecursively()

        val rapport = synchroniser()

        assertEquals("un", lire(fiche))
        assertEquals("deux", lire("$DOSSIER_OUVRAGE/Dossier technique/Fiche B.xlsx"))
        // l'etat de l'application vivait dans ce dossier : tout est retelecharge, comme a une premiere installation
        assertEquals(2, rapport.telecharges)
    }

    @Test
    fun `un fichier de l'utilisateur ajoute est envoye puis protege comme les autres`() {
        ajouter()
        synchroniser()
        Files.writeString(dossier.resolve("Nouveau.xlsx"), "du nouveau")
        assertEquals(1, synchroniser().envoyes)

        Files.delete(dossier.resolve("Nouveau.xlsx"))
        val rapport = synchroniser()

        assertEquals("du nouveau", Files.readString(dossier.resolve("Nouveau.xlsx")), "devenu un fichier suivi : il est retabli")
        assertEquals(1, rapport.retablis)
    }

    // ------------------------------------------------------------------ reglage

    @Test
    fun `sans protection rien n'est verrouille ni retabli`() {
        ajouter()
        synchroniser(libre)
        assertFalse(Protection.estVerrouille(dossier))
        Files.delete(racine.resolve(fiche))

        val rapport = synchroniser(libre)

        assertFalse(existe(fiche), "comportement de base : supprime ici, conserve sur le serveur")
        assertEquals(0, rapport.retablis)
        assertTrue(rapport.ignores.any { "supprimé ici" in it })
    }

    @Test
    fun `desactiver la protection deverrouille les dossiers et la reactiver les reverrouille`() {
        if (!ntfs()) return
        ajouter()
        synchroniser()
        assertTrue(Protection.estVerrouille(dossier))

        synchroniser(libre)
        assertFalse(Protection.estVerrouille(dossier), "desactivee : dossiers rendus")
        assertFalse(Protection.estVerrouille(racine))
        assertFalse(Etat.charger(racine).protection)

        synchroniser(protege)
        assertTrue(Protection.estVerrouille(dossier), "reactivee : verrous reposes")
        assertTrue(Protection.estVerrouille(racine))
        assertTrue(Etat.charger(racine).protection)
    }

    @Test
    fun `un echec de retablissement n'est pas pris pour une suppression voulue`() {
        ajouter("contenu")
        synchroniser()
        Files.delete(racine.resolve(fiche))
        serveur.refuserTelechargements = true

        val rapport = synchroniser()

        assertFalse(existe(fiche))
        assertTrue(rapport.erreurs.any { "rétablir" in it }, rapport.erreurs.toString())
        assertFalse(Etat.charger(racine).fichiers.values.any { it.supprimeLocalement }, "pas marque « supprime ici »")

        serveur.refuserTelechargements = false
        assertEquals(1, synchroniser().retablis, "retente a la synchronisation suivante")
        assertNotNull(lire(fiche))
    }
}
