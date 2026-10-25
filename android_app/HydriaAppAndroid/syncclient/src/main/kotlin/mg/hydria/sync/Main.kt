package mg.hydria.sync

import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import mg.hydria.sync.core.Config
import mg.hydria.sync.core.ErreurAuthentification
import mg.hydria.sync.core.ErreurReseau
import mg.hydria.sync.core.Etat
import mg.hydria.sync.core.Jetons
import mg.hydria.sync.core.SyncApi
import mg.hydria.sync.core.SyncEngine
import java.nio.file.Path
import kotlin.system.exitProcess

private const val AIDE = """
Client de synchronisation Hydria (PC <-> serveur)

  syncclient login --url https://www.hydria.mg --root C:\Users\moi\Hydria --user MON_IDENTIFIANT [--organisation UUID] [--propager-suppressions]
      Se connecte (mot de passe demandé, ou variable HYDRIA_SYNC_PASSWORD) et enregistre la configuration.
  syncclient sync [--watch SECONDES]
      Synchronise une fois, ou en boucle toutes les SECONDES secondes (Ctrl+C pour arrêter).
  syncclient status
      Affiche la configuration et l'état local (sans jamais afficher de jeton).

Configuration : %APPDATA%\HydriaSync\config.json    État : <dossier>\.hydria-sync\state.json
"""

private fun options(arguments: List<String>): Map<String, String> {
    val resultat = mutableMapOf<String, String>()
    var i = 0
    while (i < arguments.size) {
        val cle = arguments[i]
        if (cle.startsWith("--")) {
            val suivant = arguments.getOrNull(i + 1)
            if (suivant != null && !suivant.startsWith("--")) { resultat[cle.removePrefix("--")] = suivant; i += 2 }
            else { resultat[cle.removePrefix("--")] = "true"; i += 1 }
        } else i += 1
    }
    return resultat
}

private fun lireMotDePasse(): String {
    System.getenv("HYDRIA_SYNC_PASSWORD")?.takeIf { it.isNotEmpty() }?.let { return it }
    val console = System.console()
    if (console != null) return String(console.readPassword("Mot de passe : "))
    print("Mot de passe (attention : saisie visible) : ")
    return readlnOrNull().orEmpty()
}

private fun nouveauClient() = HttpClient(CIO) {
    engine { requestTimeout = 180_000 }
}

private fun api(config: Config, client: HttpClient, dossierConfig: Path = Config.dossierParDefaut()): SyncApi {
    var courante = config
    return SyncApi(client, config.baseUrl, Jetons(renouvellement = config.refreshToken)) { paire ->
        courante = courante.copy(refreshToken = paire.refreshToken)
        courante.enregistrer(dossierConfig)
    }
}

fun main(arguments: Array<String>) = runBlocking {
    val commande = arguments.firstOrNull()
    val opts = options(arguments.drop(1))
    when (commande) {
        "login" -> login(opts)
        "sync" -> synchroniser(opts)
        "status" -> statut()
        else -> { println(AIDE); exitProcess(if (commande == null || commande == "aide") 0 else 2) }
    }
}

private suspend fun login(opts: Map<String, String>) {
    val url = opts["url"] ?: "https://www.hydria.mg"
    val racine = opts["root"] ?: run { println("--root est obligatoire."); exitProcess(2) }
    val utilisateur = opts["user"] ?: run { println("--user est obligatoire."); exitProcess(2) }
    val existante = Config.charger()
    val config = (existante?.takeIf { it.baseUrl == url && it.username == utilisateur }
        ?: Config(baseUrl = url, root = racine, username = utilisateur)).copy(
        root = racine, organisation = opts["organisation"] ?: existante?.organisation,
        propagerSuppressions = opts["propager-suppressions"] == "true",
    )
    val client = nouveauClient()
    try {
        val jetons = Jetons()
        val api = SyncApi(client, config.baseUrl, jetons)
        val paire = api.connecter(utilisateur, lireMotDePasse(), config.deviceId, config.deviceLabel)
        config.copy(refreshToken = paire.refreshToken).enregistrer()
        println("Connecté. Configuration enregistrée dans ${Config.dossierParDefaut()}. Lancez : syncclient sync")
    } catch (e: ErreurAuthentification) {
        println("Connexion refusée : ${e.message}"); exitProcess(1)
    } catch (e: ErreurReseau) {
        println(e.message); exitProcess(1)
    } finally {
        client.close()
    }
}

private suspend fun synchroniser(opts: Map<String, String>) {
    val config = Config.charger() ?: run { println("Aucune configuration : lancez d'abord « syncclient login »."); exitProcess(2) }
    val intervalle = opts["watch"]?.toLongOrNull()?.coerceAtLeast(10)
    val client = nouveauClient()
    try {
        val moteur = SyncEngine(api(config, client), Path.of(config.root), config) { println(it) }
        do {
            try {
                val rapport = moteur.synchroniser()
                rapport.conflits.forEach { println("⚠ $it") }
                rapport.erreurs.forEach { println("✖ $it") }
                rapport.ignores.forEach { println("• $it") }
                if (intervalle == null && !rapport.propre) exitProcess(1)
            } catch (e: ErreurReseau) {
                println("Réseau : ${e.message}")
                if (intervalle == null) exitProcess(1)
            }
            if (intervalle != null) delay(intervalle * 1000)
        } while (intervalle != null)
    } catch (e: ErreurAuthentification) {
        println("Authentification : ${e.message} → relancez « syncclient login »."); exitProcess(1)
    } finally {
        client.close()
    }
}

private fun statut() {
    val config = Config.charger() ?: run { println("Aucune configuration."); return }
    println("Serveur : ${config.baseUrl}\nCompte : ${config.username}\nDossier : ${config.root}")
    println("Suppressions propagées : ${config.propagerSuppressions}")
    val etat = Etat.charger(Path.of(config.root))
    println("Curseur : ${etat.curseur} | fichiers suivis : ${etat.fichiers.size} | téléchargements en attente : ${etat.enAttente.size}")
    etat.fichiers.values.filter { it.conflit }.forEach { println("⚠ conflit : ${it.relPath}") }
}
