package mg.hydria.sync.app

import androidx.compose.runtime.remember
import mg.hydria.sync.core.Config
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState

/** Point d'entree de la fenetre : `gradlew :syncclient:run`, ou l'executable cree par `createDistributable`. */
fun main() {
    FichierJournal.marquerDemarrage()
    FichierJournal.initialiser(Config.dossierParDefaut())
    FichierJournal.installerGestionnaireGlobal()
    FichierJournal.ecrire("Démarrage de Hydria Sync (configuration : ${Config.dossierParDefaut()})")
    demarrer()
}

private fun demarrer() = application {
    val controleur = remember {
        try {
            SyncController()
        } catch (e: Throwable) {
            FichierJournal.erreur("création du contrôleur (configuration illisible ?)", e)
            throw e
        }
    }
    Window(
        onCloseRequest = {
            controleur.arreter()
            exitApplication()
        },
        title = "Hydria Sync",
        state = rememberWindowState(width = 980.dp, height = 720.dp),
    ) {
        HydriaSyncApp(controleur)
    }
}
