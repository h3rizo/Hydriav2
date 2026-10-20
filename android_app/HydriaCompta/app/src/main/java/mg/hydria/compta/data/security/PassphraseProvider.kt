package mg.hydria.compta.data.security

import android.content.Context
import java.security.SecureRandom

/**
 * Fournit la passphrase SQLCipher : générée une fois, aléatoirement, et
 * conservée dans un `SharedPreferences` chiffré (Keystore) — avec repli en clair
 * si le chiffrement est indisponible sur l'appareil (voir [openSecurePrefs]).
 *
 * Le verrou applicatif (PIN / biométrie) — à ajouter dans `ui` / `AppLock` —
 * contrôlera l'accès à l'app avant l'ouverture de la base.
 */
class PassphraseProvider(context: Context) {

    private val prefs by lazy { openSecurePrefs(context, "hydria_compta_secrets") }

    /** Renvoie une copie fraîche des octets (SupportFactory les efface après usage). */
    fun passphraseBytes(): ByteArray {
        val existing = prefs.getString(KEY, null)
        val hex = existing ?: newPassphraseHex().also { prefs.edit().putString(KEY, it).apply() }
        return hex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    }

    private fun newPassphraseHex(): String {
        val bytes = ByteArray(32).also { SecureRandom().nextBytes(it) }
        return bytes.joinToString("") { "%02x".format(it) }
    }

    private companion object {
        const val KEY = "db_passphrase_hex"
    }
}
