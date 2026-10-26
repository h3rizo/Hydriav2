package mg.hydria.sync.app

import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import mg.hydria.sync.core.Config
import mg.hydria.sync.core.ErreurAuthentification
import mg.hydria.sync.core.ErreurReseau
import mg.hydria.sync.core.Etat
import mg.hydria.sync.core.Jetons
import mg.hydria.sync.core.Rapport
import mg.hydria.sync.core.SyncApi
import mg.hydria.sync.core.SyncEngine
import java.awt.Desktop
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

data class ConflitUi(val id: String, val relPath: String, val copie: String?)

data class ResumeUi(val telecharges: Int, val envoyes: Int, val misAJour: Int, val corbeille: Int)

/** Tout ce que la fenetre affiche. Immuable : l'interface ne lit que ceci. */
data class EtatUi(
    val config: Config? = null,
    val enCours: Boolean = false,
    val derniereSynchro: LocalDateTime? = null,
    val resume: ResumeUi? = null,
    val erreurs: List<String> = emptyList(),
    val ignores: List<String> = emptyList(),
    val conflits: List<ConflitUi> = emptyList(),
    val journal: List<String> = emptyList(),
    /** Message a montrer a l'utilisateur (connexion refusee, serveur injoignable...). */
    val message: String? = null,
    val auto: Boolean = false,
    val intervalleMinutes: Int = 1,
) {
    val connecte: Boolean get() = config != null
}

/**
 * Cerveau de la fenetre : connexion, synchronisation (manuelle ou automatique), resolution des conflits.
 * Aucune dependance a Compose : testable avec un faux serveur.
 */
class SyncController(
    private val dossierConfig: Path = Config.dossierParDefaut(),
    private val creerClient: () -> HttpClient = { HttpClient(CIO) { engine { requestTimeout = 180_000 } } },
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO),
) {
    private val _etat = MutableStateFlow(EtatUi(config = Config.charger(dossierConfig)))
    val etat: StateFlow<EtatUi> = _etat.asStateFlow()

    private val verrou = Mutex()
    private var client: HttpClient? = null
    private var api: SyncApi? = null
    private var jobAuto: Job? = null
    private val heure = DateTimeFormatter.ofPattern("HH:mm:ss")

    private val racine: Path? get() = _etat.value.config?.let { Path.of(it.root) }

    init {
        _etat.value.config?.let { rafraichirConflits() }
    }

    // ------------------------------------------------------------------ connexion

    suspend fun seConnecterEtAttendre(url: String, dossier: String, utilisateur: String, motDePasse: String, organisation: String?) {
        val adresse = url.trim().trimEnd('/')
        if (adresse.isEmpty() || dossier.isBlank() || utilisateur.isBlank() || motDePasse.isEmpty()) {
            _etat.update { it.copy(message = "Renseignez le serveur, le dossier, l'identifiant et le mot de passe.") }
            return
        }
        val existante = Config.charger(dossierConfig)
        val base = existante?.takeIf { it.baseUrl == adresse && it.username == utilisateur }
            ?: Config(baseUrl = adresse, root = dossier, username = utilisateur, deviceLabel = nomPoste())
        val config = base.copy(root = dossier.trim(), organisation = organisation?.trim()?.ifEmpty { null })
        val nouveauClient = creerClient()
        try {
            val jetons = Jetons()
            val paire = SyncApi(nouveauClient, adresse, jetons).connecter(utilisateur, motDePasse, config.deviceId, config.deviceLabel)
            val complete = config.copy(refreshToken = paire.refreshToken)
            complete.enregistrer(dossierConfig)
            fermerClient()
            client = nouveauClient
            api = null
            _etat.update { it.copy(config = complete, message = null, journal = emptyList(), erreurs = emptyList(), ignores = emptyList()) }
            ajouterJournal("Connecté en tant que $utilisateur.")
        } catch (e: ErreurAuthentification) {
            nouveauClient.close()
            _etat.update { it.copy(message = "Connexion refusée : ${e.message}") }
        } catch (e: ErreurReseau) {
            nouveauClient.close()
            _etat.update { it.copy(message = e.message) }
        } catch (e: java.io.IOException) {
            nouveauClient.close()
            FichierJournal.erreur("enregistrement de la configuration", e)
            _etat.update { it.copy(message = "Connexion réussie mais la configuration n'a pas pu être enregistrée. ${mg.hydria.sync.core.decrire(e)}") }
        }
    }

    fun seConnecter(url: String, dossier: String, utilisateur: String, motDePasse: String, organisation: String?) {
        scope.launch { seConnecterEtAttendre(url, dossier, utilisateur, motDePasse, organisation) }
    }

    fun deconnecter() {
        basculerAuto(false)
        fermerClient()
        val erreur = oublierJeton()
        _etat.update {
            EtatUi(
                config = null, intervalleMinutes = it.intervalleMinutes,
                message = erreur?.let { e -> "Déconnecté, mais le jeton enregistré n'a pas pu être effacé. ${mg.hydria.sync.core.decrire(e)}" },
            )
        }
    }

    /** Efface le jeton de renouvellement du disque. Retourne l'erreur eventuelle au lieu de la lever. */
    private fun oublierJeton(): Exception? = try {
        Config.charger(dossierConfig)?.copy(refreshToken = null)?.enregistrer(dossierConfig)
        null
    } catch (e: Exception) {
        FichierJournal.erreur("effacement du jeton", e)
        ajouterJournal("Effacement du jeton impossible : ${mg.hydria.sync.core.decrire(e)}")
        e
    }

    private fun nomPoste(): String = System.getenv("COMPUTERNAME") ?: "PC"

    private fun fermerClient() {
        client?.close()
        client = null
        api = null
    }

    private fun apiCourante(config: Config): SyncApi {
        api?.let { return it }
        val c = client ?: creerClient().also { client = it }
        var courante = config
        return SyncApi(c, config.baseUrl, Jetons(renouvellement = config.refreshToken)) { paire ->
            courante = courante.copy(refreshToken = paire.refreshToken)
            courante.enregistrer(dossierConfig)
        }.also { api = it }
    }

    // ------------------------------------------------------------------ synchronisation

    fun synchroniser() {
        scope.launch { synchroniserEtAttendre() }
    }

    suspend fun synchroniserEtAttendre() {
        if (!verrou.tryLock()) return // une synchronisation est deja en cours
        try {
            executer()
        } finally {
            verrou.unlock()
        }
    }

    private suspend fun executer() {
        val config = _etat.value.config ?: return
        _etat.update { it.copy(enCours = true, message = null) }
        try {
            val moteur = SyncEngine(apiCourante(config), Path.of(config.root), config) { ajouterJournal(it) }
            val rapport = try {
                moteur.synchroniser()
            } finally {
                apiCourante(config).persistanceEchouee?.let { e ->
                    FichierJournal.erreur("enregistrement du jeton renouvelé", e)
                    ajouterJournal("Attention : le jeton renouvelé n'a pas pu être enregistré (${e.message}).")
                }
            }
            terminer(rapport)
        } catch (e: ErreurAuthentification) {
            FichierJournal.ecrire("Authentification refusée : ${e.message}")
            ajouterJournal("Session expirée : ${e.message}")
            _etat.update { it.copy(enCours = false, message = e.message ?: "Session expirée : reconnectez-vous.") }
            deconnecterSession()
        } catch (e: ErreurReseau) {
            FichierJournal.erreur("réseau", e)
            ajouterJournal("Réseau : ${e.message}")
            _etat.update { it.copy(enCours = false, message = e.message) }
        } catch (e: Exception) {
            FichierJournal.erreur("synchronisation", e)
            ajouterJournal("Erreur : ${e.message ?: e::class.simpleName}")
            _etat.update { it.copy(enCours = false, message = "Erreur inattendue. ${mg.hydria.sync.core.decrire(e)}") }
        }
    }

    private fun terminer(rapport: Rapport) {
        _etat.update {
            it.copy(
                enCours = false, derniereSynchro = LocalDateTime.now(), message = null,
                resume = ResumeUi(rapport.telecharges, rapport.envoyes, rapport.misAJour, rapport.corbeille),
                erreurs = rapport.erreurs.toList(), ignores = rapport.ignores.toList(),
            )
        }
        rafraichirConflits()
    }

    /** Session invalide : on oublie le jeton mais on garde le formulaire prerempli (config sans jeton). */
    private fun deconnecterSession() {
        basculerAuto(false)
        fermerClient()
        oublierJeton()
        _etat.update { it.copy(config = null, auto = false) }
    }

    private fun rafraichirConflits() {
        val dossier = racine ?: return
        val conflits = Etat.charger(dossier).fichiers.values.filter { it.conflit }
            .map { ConflitUi(it.id, it.relPath, it.conflitCopie) }
            .sortedBy { it.relPath }
        _etat.update { it.copy(conflits = conflits) }
    }

    // ------------------------------------------------------------------ synchronisation automatique

    fun basculerAuto(actif: Boolean) {
        jobAuto?.cancel()
        jobAuto = null
        _etat.update { it.copy(auto = actif) }
        if (!actif) return
        jobAuto = scope.launch {
            while (isActive) {
                synchroniserEtAttendre()
                delay(_etat.value.intervalleMinutes * 60_000L)
            }
        }
    }

    fun choisirIntervalle(minutes: Int) {
        _etat.update { it.copy(intervalleMinutes = minutes.coerceIn(1, 60)) }
    }

    // ------------------------------------------------------------------ conflits

    /** Garder ma version : on supprime la copie du serveur, la synchronisation envoie ma version par-dessus. */
    suspend fun garderMaVersionEtAttendre(id: String) = resoudre(id) { dossier, suivi ->
        suivi.conflitCopie?.let { Files.deleteIfExists(dossier.resolve(it)) }
        ajouterJournal("Conflit : version locale conservée pour ${suivi.relPath}.")
    }

    /** Prendre celle du serveur : la copie remplace mon fichier, la synchronisation s'aligne sans rien envoyer. */
    suspend fun prendreVersionServeurEtAttendre(id: String) = resoudre(id) { dossier, suivi ->
        val copie = suivi.conflitCopie?.let { dossier.resolve(it) }
        if (copie != null && Files.exists(copie)) {
            Files.move(copie, dossier.resolve(suivi.relPath), StandardCopyOption.REPLACE_EXISTING)
            ajouterJournal("Conflit : version du serveur adoptée pour ${suivi.relPath}.")
        }
    }

    fun garderMaVersion(id: String) { scope.launch { garderMaVersionEtAttendre(id) } }
    fun prendreVersionServeur(id: String) { scope.launch { prendreVersionServeurEtAttendre(id) } }

    private suspend fun resoudre(id: String, action: (Path, mg.hydria.sync.core.FichierSuivi) -> Unit) {
        val dossier = racine ?: return
        verrou.withLock {
            val suivi = Etat.charger(dossier).fichiers[id] ?: return
            try {
                action(dossier, suivi)
            } catch (e: Exception) {
                _etat.update { it.copy(message = "Impossible de résoudre le conflit : ${e.message}") }
                return
            }
            executer()
        }
    }

    // ------------------------------------------------------------------ divers

    fun ouvrirDossier(relatif: String? = null) {
        val dossier = racine ?: return
        val cible = relatif?.let { dossier.resolve(it).parent } ?: dossier
        runCatching {
            Files.createDirectories(cible)
            if (Desktop.isDesktopSupported()) Desktop.getDesktop().open(cible.toFile())
        }
    }

    /** Derniere configuration enregistree (pour prerremplir le formulaire de connexion). */
    fun configEnregistree(): Config? = Config.charger(dossierConfig)

    fun effacerMessage() {
        _etat.update { it.copy(message = null) }
    }

    private fun ajouterJournal(ligne: String) {
        FichierJournal.ecrire(ligne)
        val horodatee = "${LocalDateTime.now().format(heure)}  $ligne"
        _etat.update { it.copy(journal = (it.journal + horodatee).takeLast(300)) }
    }

    fun arreter() {
        jobAuto?.cancel()
        fermerClient()
    }
}
