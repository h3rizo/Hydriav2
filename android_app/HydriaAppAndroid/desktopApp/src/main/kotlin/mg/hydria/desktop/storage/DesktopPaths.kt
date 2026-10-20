package mg.hydria.desktop.storage

import java.io.File
import java.util.Locale

/**
 * Dossier de donnees local, par systeme d'exploitation. Equivalent Desktop
 * du repertoire prive de l'app Android : contiendra la base SQLDelight
 * (`hydria.db`) et le fichier de preferences.
 *
 *  - Windows : %APPDATA%\Hydria\Operations
 *  - Linux   : $XDG_DATA_HOME/hydria-operations  (defaut ~/.local/share/hydria-operations)
 *  - macOS   : ~/Library/Application Support/Hydria/Operations  (build non cible pour l'instant)
 */
data class DesktopPaths(val dataDir: File) {
    val databaseFile: File get() = File(dataDir, "hydria.db")
    val preferencesFile: File get() = File(dataDir, "preferences.json")

    companion object {
        fun resolve(): DesktopPaths {
            val os = System.getProperty("os.name").orEmpty().lowercase(Locale.ROOT)
            val home = File(System.getProperty("user.home"))
            val dir = when {
                os.contains("win") -> {
                    val appData = System.getenv("APPDATA")?.let(::File) ?: File(home, "AppData/Roaming")
                    File(appData, "Hydria/Operations")
                }
                os.contains("mac") || os.contains("darwin") ->
                    File(home, "Library/Application Support/Hydria/Operations")
                else -> {
                    val xdg = System.getenv("XDG_DATA_HOME")?.takeIf { it.isNotBlank() }?.let(::File)
                        ?: File(home, ".local/share")
                    File(xdg, "hydria-operations")
                }
            }
            dir.mkdirs()
            return DesktopPaths(dir)
        }
    }
}
