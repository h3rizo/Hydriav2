package mg.hydria.logistique.network

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import java.nio.ByteBuffer
import java.security.KeyStore
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.inject.Inject
import javax.inject.Singleton

private val Context.authDataStore by preferencesDataStore(name = "secure_mobile_session")

@Singleton
class SecureTokenStore @Inject constructor(@param:ApplicationContext private val context: Context) {
    private val accessKey = stringPreferencesKey("access_ciphertext")
    private val refreshKey = stringPreferencesKey("refresh_ciphertext")
    private val deviceKey = stringPreferencesKey("device_id")

    val accessToken: Flow<String?> = context.authDataStore.data.map { preferences ->
        preferences[accessKey]?.let(::decrypt)
    }
    val refreshToken: Flow<String?> = context.authDataStore.data.map { preferences ->
        preferences[refreshKey]?.let(::decrypt)
    }
    val authenticated: Flow<Boolean> = accessToken.map { !it.isNullOrBlank() }

    suspend fun save(access: String, refresh: String) {
        context.authDataStore.edit {
            it[accessKey] = encrypt(access)
            it[refreshKey] = encrypt(refresh)
        }
    }

    suspend fun updateAccess(access: String, refresh: String) = save(access, refresh)

    suspend fun clear() {
        context.authDataStore.edit {
            it.remove(accessKey)
            it.remove(refreshKey)
        }
    }

    suspend fun deviceId(): String {
        context.authDataStore.data.first()[deviceKey]?.let { return it }
        val generated = UUID.randomUUID().toString()
        context.authDataStore.edit { it[deviceKey] = generated }
        return generated
    }

    fun deviceLabel(): String = "${Build.MANUFACTURER} ${Build.MODEL}".trim().take(120)

    private fun secretKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return generator.generateKey()
    }

    private fun encrypt(value: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val bytes = ByteBuffer.allocate(4 + cipher.iv.size + encrypted.size)
            .putInt(cipher.iv.size).put(cipher.iv).put(encrypted).array()
        return Base64.encodeToString(bytes, Base64.NO_WRAP)
    }

    private fun decrypt(encoded: String): String? = runCatching {
        val buffer = ByteBuffer.wrap(Base64.decode(encoded, Base64.NO_WRAP))
        val iv = ByteArray(buffer.int).also(buffer::get)
        val encrypted = ByteArray(buffer.remaining()).also(buffer::get)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
        String(cipher.doFinal(encrypted), Charsets.UTF_8)
    }.getOrNull()

    private companion object {
        const val KEY_ALIAS = "mg.hydria.logistique.mobile.tokens.v1"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
