package mg.hydria.sync.app

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.runBlocking
import mg.hydria.sync.core.Config
import mg.hydria.sync.core.DOSSIER_OUVRAGE
import mg.hydria.sync.core.FauxServeur
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.FileTime
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class SyncControllerTest {
    private lateinit var dossierConfig: Path
    private lateinit var racine: Path
    private lateinit var serveur: FauxServeur
    private lateinit var controleur: SyncController
    private val fiche get() = "$DOSSIER_OUVRAGE/Dossier technique/Fiche A.xlsx"
    private val copie get() = "$DOSSIER_OUVRAGE/Dossier technique/Fiche A (conflit serveur v2).xlsx"
    private val mdp = "mot-de-passe-secret-de-test"

    @BeforeTest
    fun preparer() {
        dossierConfig = Files.createTempDirectory("hydria-config-test-")
        racine = Files.createTempDirectory("hydria-racine-test-")
        serveur = FauxServeur()
        controleur = nouveauControleur()
    }

    private fun nouveauControleur() = SyncController(
        dossierConfig = dossierConfig, creerClient = { serveur.client },
        scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined),
    )

    @AfterTest
    fun nettoyer() {
        controleur.arreter()
        dossierConfig.toFile().deleteRecursively()
        racine.toFile().deleteRecursively()
    }

    private fun connecter() = runBlocking {
        controleur.seConnecterEtAttendre("https://hydria.test/", racine.toString(), "agent", mdp, null)
    }

    private fun synchroniser() = runBlocking { controleur.synchroniserEtAttendre() }

    private fun ecrireModifie(rel: String, contenu: String) {
        val p = racine.resolve(rel)
        Files.writeString(p, contenu)
        Files.setLastModifiedTime(p, FileTime.fromMillis(System.currentTimeMillis() + 5_000))
    }

    private fun provoquerConflit() {
        val f = serveur.nouveau("Fiche A.xlsx", "v1".toByteArray(), "dossier_technique", "ouvrage", "o1")
        connecter(); synchroniser()
        ecrireModifie(fiche, "ma version locale")
        serveur.modifier(f.id, "version du serveur".toByteArray())
        synchroniser()
    }

    // ------------------------------------------------------------------ connexion

    @Test
    fun `une connexion refusee affiche un message et ne connecte pas`() {
        serveur.refuserConnexion = true
        connecter()
        assertFalse(controleur.etat.value.connecte)
        assertTrue(controleur.etat.value.message!!.contains("Identifiants invalides"), controleur.etat.value.message)
        assertNull(Config.charger(dossierConfig))
    }

    @Test
    fun `des champs vides sont refuses sans appeler le serveur`() {
        runBlocking { controleur.seConnecterEtAttendre("", "", "", "", null) }
        assertFalse(controleur.etat.value.connecte)
        assertNotNull(controleur.etat.value.message)
        assertTrue(serveur.requetes.isEmpty())
    }

    @Test
    fun `une connexion reussie enregistre la configuration sans le mot de passe`() {
        connecter()
        val etat = controleur.etat.value
        assertTrue(etat.connecte)
        assertEquals("https://hydria.test", etat.config!!.baseUrl, "l'adresse est normalisee")
        val fichier = Files.readString(dossierConfig.resolve("config.json"))
        assertTrue("R1" in fichier, "le jeton de renouvellement est conserve")
        assertFalse(mdp in fichier, "le mot de passe n'est jamais ecrit sur le disque")
        assertEquals("R1", Config.charger(dossierConfig)!!.refreshToken)
    }

    @Test
    fun `un jeton renouvele est enregistre sur le disque et reutilisable`() {
        connecter()
        assertEquals("R1", Config.charger(dossierConfig)!!.refreshToken)
        synchroniser() // premier appel : pas de jeton d'acces en memoire, donc renouvellement R1 -> R2
        assertEquals("R2", Config.charger(dossierConfig)!!.refreshToken, "le nouveau jeton doit etre conserve")
        assertTrue(serveur.requetes.contains("POST /api/sync/auth/refresh"))
    }

    @Test
    fun `un nouveau controleur retrouve la session enregistree`() {
        connecter()
        val relance = nouveauControleur()
        assertTrue(relance.etat.value.connecte)
        assertEquals("agent", relance.etat.value.config!!.username)
        relance.arreter()
    }

    @Test
    fun `se deconnecter oublie le jeton`() {
        connecter()
        controleur.deconnecter()
        assertFalse(controleur.etat.value.connecte)
        assertNull(Config.charger(dossierConfig)!!.refreshToken)
    }

    // ------------------------------------------------------------------ synchronisation

    @Test
    fun `une synchronisation met a jour l'etat, le resume et le journal`() {
        serveur.nouveau("Fiche A.xlsx", "AAA".toByteArray(), "dossier_technique", "ouvrage", "o1")
        connecter()
        assertNull(controleur.etat.value.derniereSynchro)

        synchroniser()

        val etat = controleur.etat.value
        assertFalse(etat.enCours)
        assertNotNull(etat.derniereSynchro)
        assertEquals(1, etat.resume!!.telecharges)
        assertTrue(etat.erreurs.isEmpty() && etat.conflits.isEmpty())
        assertTrue(etat.journal.any { "Fiche A.xlsx" in it }, etat.journal.toString())
        assertEquals("AAA", Files.readString(racine.resolve(fiche)))
    }

    @Test
    fun `un serveur injoignable donne un message sans deconnecter`() {
        connecter()
        serveur.jetonValide = "inconnu"
        serveur.refuserRenouvellement = false
        // le renouvellement reussit puis les appels passent : on simule la panne en retirant le serveur
        controleur.arreter()
        val panne = SyncController(
            dossierConfig = dossierConfig,
            creerClient = {
                io.ktor.client.HttpClient(io.ktor.client.engine.mock.MockEngine { throw java.io.IOException("connexion refusee") })
            },
            scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined),
        )
        runBlocking { panne.synchroniserEtAttendre() }
        assertTrue(panne.etat.value.connecte, "une panne reseau ne deconnecte pas")
        assertTrue(panne.etat.value.message!!.contains("injoignable"), panne.etat.value.message)
        assertFalse(panne.etat.value.enCours)
        panne.arreter()
    }

    @Test
    fun `une session expiree ramene a l'ecran de connexion avec un message`() {
        connecter()
        serveur.jetonValide = "autre"
        serveur.refuserRenouvellement = true
        synchroniser()
        val etat = controleur.etat.value
        assertFalse(etat.connecte)
        assertTrue(etat.message!!.contains("Session expirée"), etat.message)
        assertNull(Config.charger(dossierConfig)!!.refreshToken)
    }

    @Test
    fun `la synchronisation automatique repete et s'arrete`() {
        serveur.nouveau("Fiche A.xlsx", "AAA".toByteArray(), "dossier_technique", "ouvrage", "o1")
        connecter()
        controleur.basculerAuto(true)
        assertTrue(controleur.etat.value.auto)
        // la premiere passe part tout de suite mais s'execute en arriere-plan : on l'attend (5 s au plus)
        val limite = System.currentTimeMillis() + 5_000
        while (controleur.etat.value.derniereSynchro == null && System.currentTimeMillis() < limite) Thread.sleep(25)
        assertNotNull(controleur.etat.value.derniereSynchro)
        controleur.basculerAuto(false)
        assertFalse(controleur.etat.value.auto)
    }

    // ------------------------------------------------------------------ conflits

    @Test
    fun `un conflit apparait dans la liste avec sa copie`() {
        provoquerConflit()
        val conflits = controleur.etat.value.conflits
        assertEquals(1, conflits.size)
        assertEquals(fiche, conflits[0].relPath)
        assertEquals(copie, conflits[0].copie)
        assertEquals("version du serveur", Files.readString(racine.resolve(copie)))
        assertEquals("ma version locale", Files.readString(racine.resolve(fiche)), "le local n'est jamais ecrase")
    }

    @Test
    fun `garder ma version envoie mon fichier et vide la liste des conflits`() {
        provoquerConflit()
        val id = controleur.etat.value.conflits.single().id

        runBlocking { controleur.garderMaVersionEtAttendre(id) }

        assertTrue(controleur.etat.value.conflits.isEmpty())
        assertContentEquals("ma version locale".toByteArray(), serveur.contenus.getValue(id))
        assertFalse(Files.exists(racine.resolve(copie)))
        assertEquals(listOf("2"), serveur.ifMatchRecus)
    }

    @Test
    fun `prendre celle du serveur remplace mon fichier sans rien envoyer`() {
        provoquerConflit()
        val id = controleur.etat.value.conflits.single().id

        runBlocking { controleur.prendreVersionServeurEtAttendre(id) }

        assertTrue(controleur.etat.value.conflits.isEmpty())
        assertEquals("version du serveur", Files.readString(racine.resolve(fiche)))
        assertFalse(Files.exists(racine.resolve(copie)))
        assertTrue(serveur.requetes.none { it.startsWith("PATCH") })
    }
}
