package mg.hydria.shared.database

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import java.io.File

/**
 * Ouverture Desktop (Windows / Linux) de la base SQLDelight partagee, sur un
 * fichier SQLite dans le dossier de donnees local. Equivalent de
 * [HydriaAndroidDatabase] cote poste de travail.
 *
 * En passant [HydriaSharedDatabase.Schema] au driver JDBC, la creation du
 * schema au premier lancement (et les migrations ensuite) sont automatiques :
 * le driver lit `PRAGMA user_version` et applique ce qu'il faut.
 */
object HydriaDesktopDatabase {
    fun init(databaseFile: File) {
        if (HydriaSharedDatabaseHolder.isInitialized) return
        databaseFile.parentFile?.mkdirs()
        val driver = JdbcSqliteDriver(
            url = "jdbc:sqlite:${databaseFile.absolutePath}",
            schema = HydriaSharedDatabase.Schema,
        )
        HydriaSharedDatabaseHolder.init(driver)
    }
}
