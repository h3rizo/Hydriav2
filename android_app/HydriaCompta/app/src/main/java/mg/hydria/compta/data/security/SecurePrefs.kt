package mg.hydria.compta.data.security

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Ouvre un `SharedPreferences` chiffré (Keystore). Si le sous-système de
 * chiffrement est indisponible ou corrompu sur l'appareil, repli sur des
 * préférences en clair plutôt que de faire planter l'app au démarrage.
 *
 * ⚠️ Le repli affaiblit la protection locale — à surveiller / durcir avant
 * mise en production (verrou applicatif + éventuel blocage si non chiffré).
 */
fun openSecurePrefs(context: Context, fileName: String): SharedPreferences {
    return try {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            fileName,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    } catch (t: Throwable) {
        Log.w("SecurePrefs", "EncryptedSharedPreferences indisponible ($fileName) — repli prefs claires", t)
        runCatching { context.deleteSharedPreferences(fileName) }
        context.getSharedPreferences("${fileName}__plain", Context.MODE_PRIVATE)
    }
}
