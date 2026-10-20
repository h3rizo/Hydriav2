package mg.hydria.compta.data.db

import android.content.Context
import androidx.room.Room
import mg.hydria.compta.data.security.PassphraseProvider
import net.sqlcipher.database.SQLiteDatabase
import net.sqlcipher.database.SupportFactory

/**
 * Construit la base Room chiffrée par SQLCipher. La passphrase provient du
 * [PassphraseProvider] (clé scellée dans l'Android Keystore, débloquée par le
 * verrou applicatif).
 */
object DatabaseFactory {

    fun create(context: Context, passphraseProvider: PassphraseProvider): ComptaDatabase {
        SQLiteDatabase.loadLibs(context)
        val passphrase = passphraseProvider.passphraseBytes()
        val factory = SupportFactory(passphrase, null, /* clearPassphrase = */ true)

        return Room.databaseBuilder(context, ComptaDatabase::class.java, ComptaDatabase.NAME)
            .openHelperFactory(factory)
            // La base peut être reconstruite intégralement depuis le serveur :
            // en cas d'échec de migration on repart d'un bootstrap propre.
            .fallbackToDestructiveMigration(dropAllTables = true)
            .build()
    }
}
