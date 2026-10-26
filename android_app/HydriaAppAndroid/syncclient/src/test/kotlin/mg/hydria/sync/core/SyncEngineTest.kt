package mg.hydria.sync.core

import kotlinx.coroutines.runBlocking
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class SyncEngineTest {
    private lateinit var racine: Path
    private lateinit var serveur: FauxServeur
    private val config = Config(baseUrl = "https://hydria.test", root = "", username = "agent", deviceLabel = "PC test")

    @BeforeTest
    fun preparer() {
        racine = Files.createTempDirectory("hydria-sync-test-")
        serveur = FauxServeur()
    }

    @AfterTest
    fun nettoyer() {
        racine.toFile().deleteRecursively()
    }

    private fun synchroniser(cfg: Config = config, api: SyncApi = serveur.api()): Rapport =
        runBlocking { SyncEngine(api, racine, cfg).synchroniser() }

    private fun lire(rel: String): String = Files.readString(racine.resolve(rel))
    private fun ecrire(rel: String, contenu: String) {
        val p = racine.resolve(rel)
        Files.createDirectories(p.parent)
        Files.writeString(p, contenu)
        // un horodatage different suffit a prouver une modification (les tests vont plus vite que la milliseconde)
        Files.setLastModifiedTime(p, java.nio.file.attribute.FileTime.fromMillis(System.currentTimeMillis() + 5_000))
    }
    private fun existe(rel: String) = Files.exists(racine.resolve(rel))
    private val fiche = "$DOSSIER_OUVRAGE/Dossier technique/Fiche A.xlsx"

    private fun ajouterFicheOuvrage(contenu: String = "AAA") =
        serveur.nouveau("Fiche A.xlsx", contenu.toByteArray(), "dossier_technique", "ouvrage", "o1")

    // ------------------------------------------------------------------ serveur -> PC

    @Test
    fun `premiere synchronisation place les fichiers dans l'arborescence`() {
        ajouterFicheOuvrage("AAA")
        serveur.nouveau("proc.pdf", "PDF".toByteArray(), "procedure", domaine = "operationnel")

        val rapport = synchroniser()

        assertEquals(2, rapport.telecharges)
        assertEquals("AAA", lire(fiche))
        assertEquals("PDF", lire("Organisation/Opérationnel/Procédure/proc.pdf"))
        assertTrue(rapport.propre, rapport.erreurs.toString())
    }

    @Test
    fun `les dossiers de depot sont prepares et le domaine financier ferme n'est pas cree`() {
        synchroniser()
        assertTrue(existe("$DOSSIER_OUVRAGE/Dossier technique"))
        assertTrue(existe("Organisation/Opérationnel/Procédure"))
        assertFalse(existe("Organisation/Financier"), "domaine sans droit de lecture")
    }

    @Test
    fun `une deuxieme synchronisation ne retelecharge rien`() {
        ajouterFicheOuvrage()
        synchroniser()
        val avant = serveur.telechargements()
        val rapport = synchroniser()
        assertEquals(0, rapport.telecharges)
        assertEquals(avant, serveur.telechargements())
    }

    @Test
    fun `un SHA-256 incorrect est refuse puis le telechargement est repris`() {
        val f = serveur.nouveau("Fiche A.xlsx", "AAA".toByteArray(), "dossier_technique", "ouvrage", "o1", shaAnnonce = "0".repeat(64))
        val rapport = synchroniser()
        assertEquals(1, rapport.erreurs.size)
        assertFalse(existe(fiche), "un fichier corrompu n'est jamais place")
        assertTrue(Etat.charger(racine).enAttente.containsKey(f.id))

        serveur.fichiers[f.id] = f.copy(sha256 = sha256Hex("AAA".toByteArray()))
        val reprise = synchroniser()
        assertEquals("AAA", lire(fiche))
        assertTrue(reprise.propre, reprise.erreurs.toString())
        assertTrue(Etat.charger(racine).enAttente.isEmpty())
    }

    @Test
    fun `un fichier modifie sur le serveur est mis a jour localement`() {
        val f = ajouterFicheOuvrage("v1")
        synchroniser()
        serveur.modifier(f.id, "v2 plus long".toByteArray())
        val rapport = synchroniser()
        assertEquals(1, rapport.telecharges)
        assertEquals("v2 plus long", lire(fiche))
    }

    @Test
    fun `un fichier supprime sur le serveur part dans la corbeille locale`() {
        val f = ajouterFicheOuvrage()
        synchroniser()
        serveur.supprimer(f.id)
        val rapport = synchroniser()
        assertEquals(1, rapport.corbeille)
        assertFalse(existe(fiche))
        val corbeille = Files.walk(racine.resolve(".hydria-sync/corbeille")).use { flux -> flux.filter { p -> Files.isRegularFile(p) }.toList() }
        assertEquals(1, corbeille.size)
    }

    @Test
    fun `un renommage cote serveur renomme le fichier local`() {
        val f = ajouterFicheOuvrage()
        synchroniser()
        serveur.modifier(f.id, null, nom = "Fiche B.xlsx")
        synchroniser()
        assertFalse(existe(fiche))
        assertEquals("AAA", lire("$DOSSIER_OUVRAGE/Dossier technique/Fiche B.xlsx"))
    }

    // ------------------------------------------------------------------ PC -> serveur

    @Test
    fun `un fichier modifie localement envoie une nouvelle version avec If-Match`() {
        val f = ajouterFicheOuvrage("v1")
        synchroniser()
        ecrire(fiche, "contenu modifie ici")

        val rapport = synchroniser()

        assertEquals(1, rapport.misAJour)
        assertEquals(listOf("1"), serveur.ifMatchRecus)
        assertContentEquals("contenu modifie ici".toByteArray(), serveur.contenus.getValue(f.id))
        assertEquals(2, Etat.charger(racine).fichiers.getValue(f.id).version)
        assertEquals(0, synchroniser().misAJour, "rien a renvoyer a la synchronisation suivante")
    }

    @Test
    fun `un nouveau fichier est depose dans la bonne categorie`() {
        synchroniser()
        ecrire("$DOSSIER_OUVRAGE/Dossier technique/Nouveau plan.pdf", "PLAN")
        ecrire("Organisation/Opérationnel/Procédure/consigne.txt", "CONSIGNE")

        val rapport = synchroniser()

        assertEquals(2, rapport.envoyes, rapport.erreurs.toString())
        val plan: FichierDto = serveur.fichiers.values.first { it.nom == "Nouveau plan.pdf" }
        assertEquals("ouvrage", plan.entityType)
        assertEquals("o1", plan.entityId)
        assertEquals("dossier_technique", plan.categorie)
        val consigne: FichierDto = serveur.fichiers.values.first { it.nom == "consigne.txt" }
        assertEquals("operationnel", consigne.domaine)
        assertEquals("procedure", consigne.categorie)
        assertEquals(0, synchroniser().envoyes, "pas de renvoi")
    }

    @Test
    fun `un fichier hors des categories n'est pas envoye`() {
        synchroniser()
        ecrire("brouillon.txt", "x")
        ecrire("Organisation/Opérationnel/vrac.txt", "x")
        val rapport = synchroniser()
        assertEquals(0, rapport.envoyes)
        assertEquals(2, rapport.ignores.size)
        assertTrue(serveur.requetes.none { it.endsWith("/upload") })
    }

    @Test
    fun `les fichiers temporaires et la corbeille ne sont jamais envoyes`() {
        synchroniser()
        ecrire("$DOSSIER_OUVRAGE/Dossier technique/~\$Fiche.xlsx", "verrou office")
        ecrire("$DOSSIER_OUVRAGE/Dossier technique/brouillon.tmp", "x")
        assertEquals(0, synchroniser().envoyes)
    }

    @Test
    fun `un fichier refuse par le serveur n'est pas renvoye tant qu'il ne change pas`() {
        synchroniser()
        val rel = "$DOSSIER_OUVRAGE/Dossier technique/refuse.pdf"
        ecrire(rel, "v1")
        serveur.refuserDepots = true

        assertEquals(1, synchroniser().erreurs.size)
        val essais = serveur.requetes.count { it.endsWith("/upload") }
        synchroniser()
        assertEquals(essais, serveur.requetes.count { it.endsWith("/upload") }, "pas de nouvel essai avec le meme contenu")

        serveur.refuserDepots = false
        ecrire(rel, "v2 modifie")
        assertEquals(1, synchroniser().envoyes, "un contenu modifie est de nouveau propose")
    }

    // ------------------------------------------------------------------ suppressions

    @Test
    fun `une suppression locale n'est pas propagee par defaut`() {
        val f = ajouterFicheOuvrage()
        synchroniser()
        Files.delete(racine.resolve(fiche))

        val rapport = synchroniser()

        assertEquals(1, rapport.ignores.size)
        assertTrue(serveur.fichiers.getValue(f.id).deletedAt == null)
        assertTrue(serveur.requetes.none { it.startsWith("DELETE") })
        assertFalse(existe(fiche), "pas retelecharge tant que le serveur ne change pas")
        assertEquals(0, synchroniser().telecharges)
    }

    @Test
    fun `une suppression locale n'est propagee que si l'option est activee`() {
        val f = ajouterFicheOuvrage()
        val cfg = config.copy(propagerSuppressions = true)
        synchroniser(cfg)
        Files.delete(racine.resolve(fiche))
        synchroniser(cfg)
        assertNotNull(serveur.fichiers.getValue(f.id).deletedAt)
        assertEquals(listOf("1"), serveur.ifMatchRecus)
    }

    @Test
    fun `un fichier supprime localement mais modifie ensuite sur le serveur est restaure`() {
        val f = ajouterFicheOuvrage("v1")
        synchroniser()
        Files.delete(racine.resolve(fiche))
        synchroniser()
        serveur.modifier(f.id, "v2".toByteArray())
        synchroniser()
        assertEquals("v2", lire(fiche))
    }

    // ------------------------------------------------------------------ conflits

    private fun provoquerConflit(): FichierDto {
        val f = ajouterFicheOuvrage("v1")
        synchroniser()
        ecrire(fiche, "ma version locale")
        serveur.modifier(f.id, "version du serveur".toByteArray())
        return f
    }

    private val copieConflit = "$DOSSIER_OUVRAGE/Dossier technique/Fiche A (conflit serveur v2).xlsx"

    @Test
    fun `un conflit conserve la version locale et enregistre celle du serveur a cote`() {
        provoquerConflit()
        val rapport = synchroniser()

        assertEquals(1, rapport.conflits.size)
        assertEquals("ma version locale", lire(fiche), "le local n'est jamais ecrase")
        assertEquals("version du serveur", lire(copieConflit))
        assertTrue(serveur.requetes.none { it.startsWith("PATCH") }, "rien n'est envoye tant que le conflit n'est pas resolu")
        // tant que rien n'est decide, la situation reste signalee sans rien changer
        assertEquals(1, synchroniser().conflits.size)
        assertEquals("ma version locale", lire(fiche))
    }

    @Test
    fun `resoudre un conflit en supprimant la copie envoie ma version par-dessus`() {
        val f = provoquerConflit()
        synchroniser()
        Files.delete(racine.resolve(copieConflit))

        val rapport = synchroniser()

        assertTrue(rapport.conflits.isEmpty(), rapport.conflits.toString())
        assertEquals(listOf("2"), serveur.ifMatchRecus, "If-Match sur la version courante du serveur")
        assertContentEquals("ma version locale".toByteArray(), serveur.contenus.getValue(f.id))
        assertEquals(3, serveur.fichiers.getValue(f.id).version)
    }

    @Test
    fun `resoudre un conflit en adoptant la copie du serveur aligne le fichier sans rien envoyer`() {
        val f = provoquerConflit()
        synchroniser()
        Files.move(racine.resolve(copieConflit), racine.resolve(fiche), java.nio.file.StandardCopyOption.REPLACE_EXISTING)

        val rapport = synchroniser()

        assertTrue(rapport.conflits.isEmpty(), rapport.conflits.toString())
        assertTrue(serveur.requetes.none { it.startsWith("PATCH") })
        assertEquals("version du serveur", lire(fiche))
        val suivi = Etat.charger(racine).fichiers.getValue(f.id)
        assertFalse(suivi.conflit)
        assertEquals(2, suivi.version)
    }

    @Test
    fun `une copie de conflit n'est jamais envoyee comme nouveau fichier`() {
        provoquerConflit()
        synchroniser()
        assertTrue(serveur.requetes.none { it.endsWith("/upload") })
    }

    // ------------------------------------------------------------------ homonymes et jetons

    @Test
    fun `un jeton expire est renouvele automatiquement`() {
        ajouterFicheOuvrage()
        val api = serveur.api()
        runBlocking { api.connecter("agent", "mdp", "device", "PC") }
        serveur.jetonValide = "autre" // le serveur ne reconnait plus T1
        val rapport = synchroniser(api = api)
        assertEquals(1, rapport.telecharges)
        assertTrue(serveur.requetes.contains("POST /api/sync/auth/refresh"))
        assertEquals("R2", api.jetons.renouvellement)
    }

    @Test
    fun `l'ecriture de configuration se replie sur l'ecriture directe si le renommage echoue`() {
        val cible = racine.resolve("config.json")
        Files.createDirectories(racine.resolve("config.json.tmp")) // le nom du fichier temporaire est deja pris
        ecrireAtomique(cible, "{\"v\":1}", tentatives = 2, pauseMs = 1)
        assertEquals("{\"v\":1}", Files.readString(cible))
        ecrireAtomique(cible, "{\"v\":2}", tentatives = 2, pauseMs = 1)
        assertEquals("{\"v\":2}", Files.readString(cible), "meme sur un fichier existant")
    }

    @Test
    fun `une ecriture impossible leve une erreur qui nomme le fichier et le type d'exception`() {
        val cible = racine.resolve("dossier-absent").resolve("sous").resolve("config.json")
        val erreur = kotlin.runCatching { ecrireAtomique(cible, "x", tentatives = 1, pauseMs = 1) }.exceptionOrNull()
        assertNotNull(erreur)
        assertTrue("config.json" in erreur.message.orEmpty(), erreur.message)
        assertTrue("Exception" in erreur.message.orEmpty(), erreur.message)
    }
}
