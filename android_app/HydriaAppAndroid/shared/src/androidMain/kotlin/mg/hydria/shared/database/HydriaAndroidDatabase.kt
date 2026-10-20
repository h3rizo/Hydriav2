package mg.hydria.shared.database

import android.content.Context
import app.cash.sqldelight.driver.android.AndroidSqliteDriver

/**
 * Ouverture Android de la base SQLDelight partagee. Remplace l'ancien
 * `HydriaXGateway.init(context)` : les facades vivent maintenant en
 * jvmCommonMain (partagees avec le Desktop) et ne connaissent plus le driver.
 *
 * Comportement identique a l'ancien HydriaSharedDatabaseHolder.init(context) :
 * meme fichier "hydria_shared.db", meme AndroidSqliteDriver.
 */
object HydriaAndroidDatabase {
    fun init(context: Context) {
        if (HydriaSharedDatabaseHolder.isInitialized) return
        HydriaSharedDatabaseHolder.init(
            AndroidSqliteDriver(
                schema = HydriaSharedDatabase.Schema,
                context = context.applicationContext,
                name = "hydria_shared.db",
            )
        )
    }
}
