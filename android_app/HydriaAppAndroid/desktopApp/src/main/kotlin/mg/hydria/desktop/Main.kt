package mg.hydria.desktop

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import mg.hydria.desktop.storage.DesktopPaths
import mg.hydria.shared.database.HydriaDesktopDatabase
import mg.hydria.shared.ui.intro.HydriaIntro

fun main() {
    // Dossier de donnees local (equivalent Desktop du stockage prive Android).
    val paths = DesktopPaths.resolve()

    // Ouvre la base SQLDelight partagee sur <dataDir>/hydria.db (schema cree au
    // premier lancement). Les facades de :shared (cache recherche, snapshot,
    // file de synchro, ...) sont alors utilisables cote Desktop, exactement
    // comme cote Android.
    HydriaDesktopDatabase.init(paths.databaseFile)

    application {
        val windowState = rememberWindowState(width = 1180.dp, height = 780.dp)
        Window(
            onCloseRequest = ::exitApplication,
            state = windowState,
            title = "Hydria Operations",
        ) {
            var showIntro by remember { mutableStateOf(true) }
            if (showIntro) {
                HydriaIntro(onFinished = { showIntro = false })
            } else {
                val model = remember { DesktopAppModel(paths) }
                HydriaDesktopApp(model)
            }
        }
    }
}
