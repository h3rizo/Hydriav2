package mg.hydria.logistique.database

import android.content.Context
import androidx.room.Room
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    private val migration1To2 = object : Migration(1, 2) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE articles ADD COLUMN unitPrice TEXT")
            db.execSQL("ALTER TABLE articles ADD COLUMN minimumLevel TEXT NOT NULL DEFAULT '0.00'")
            db.execSQL("ALTER TABLE articles ADD COLUMN nature TEXT NOT NULL DEFAULT ''")
            db.execSQL("ALTER TABLE articles ADD COLUMN description TEXT")
            db.execSQL("ALTER TABLE stock_positions ADD COLUMN estimateReason TEXT")
        }
    }

    private val migration2To3 = object : Migration(2, 3) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("CREATE TABLE IF NOT EXISTS dashboard_stats (code TEXT NOT NULL, count INTEGER NOT NULL, asOfDate TEXT NOT NULL, PRIMARY KEY(code))")
        }
    }

    private val migration3To4 = object : Migration(3, 4) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE purchases ADD COLUMN supplierName TEXT")
        }
    }

    private val migration4To5 = object : Migration(4, 5) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE stock_positions ADD COLUMN stockId TEXT")
        }
    }

    @Provides @Singleton
    fun provideDatabase(@ApplicationContext context: Context): LogistiqueDatabase =
        Room.databaseBuilder(context, LogistiqueDatabase::class.java, "logistique.db")
            .addMigrations(migration1To2, migration2To3, migration3To4, migration4To5)
            .build()

    @Provides
    fun provideDao(database: LogistiqueDatabase): LogistiqueDao = database.dao()
}
