package mg.hydria.shared.database

import app.cash.sqldelight.db.SqlDriver

/**
 * Point d'entree unique pour la base SQLDelight partagee (Phase 2 KMP) : une
 * seule instance de [HydriaSharedDatabase], partagee par toutes les facades de
 * table (HydriaSyncQueueGateway, HydriaSnapshotGateway, HydriaSearchCacheGateway,
 * HydriaCalculatorGateway, HydriaVolumeCacheGateway, HydriaGeoGateway).
 *
 * Le driver est fourni par la couche applicative de chaque plateforme :
 *  - Android : [HydriaAndroidDatabase.init] (AndroidSqliteDriver, "hydria_shared.db")
 *  - Desktop : [HydriaDesktopDatabase.init] (JdbcSqliteDriver sur un fichier)
 *
 * [init] est idempotent et thread-safe ; il doit etre appele une fois avant
 * toute autre methode des facades.
 */
object HydriaSharedDatabaseHolder {
    @Volatile
    private var instance: HydriaSharedDatabase? = null

    val isInitialized: Boolean get() = instance != null

    @Synchronized
    fun init(driver: SqlDriver) {
        if (instance != null) return
        instance = HydriaSharedDatabase(driver)
    }

    /** Reserve aux tests : repose le holder pour un nouveau driver. */
    @Synchronized
    fun resetForTests() {
        instance = null
    }

    val database: HydriaSharedDatabase
        get() = instance ?: error("HydriaSharedDatabaseHolder.init(driver) doit etre appele avant usage")
}
