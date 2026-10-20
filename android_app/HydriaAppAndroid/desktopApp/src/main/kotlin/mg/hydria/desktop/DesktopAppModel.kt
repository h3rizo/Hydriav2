package mg.hydria.desktop

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.storage.DesktopPaths
import mg.hydria.desktop.storage.DesktopPrefs

/** Modules du poste de travail Desktop (portage KMP : tous cables sur :shared). */
enum class DesktopScreen(val label: String) {
    CALCULATRICE("Calculatrice"),
    RECHERCHE("Recherche"),
    RELEVES("Releves"),
    REPARATIONS("Reparations"),
    PLANNING("Planning"),
    VOLUMETRIQUE("Volume"),
    NAVIGATION("Navigation"),
}

/** Etat applicatif partage par la fenetre. Pas de DI formelle : la base
 * SQLDelight (ouverte dans Main.kt sur [DesktopPaths.databaseFile]) et le
 * client reseau Ktor de :shared sont accedes directement par les ecrans. */
class DesktopAppModel(val paths: DesktopPaths) {
    val prefs = DesktopPrefs(paths.preferencesFile)
    val session = DesktopSession(prefs)

    var screen by mutableStateOf(DesktopScreen.CALCULATRICE)
}
