package mg.hydria.compta.data.prefs

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "hydria_compta_sync_prefs")

/** Réglages de synchronisation (non secrets). */
class SyncPreferences(private val context: Context) {

    val wifiOnly: Flow<Boolean> = context.dataStore.data.map { it[WIFI_ONLY] ?: false }
    val autoSync: Flow<Boolean> = context.dataStore.data.map { it[AUTO_SYNC] ?: true }

    suspend fun setWifiOnly(value: Boolean) {
        context.dataStore.edit { it[WIFI_ONLY] = value }
    }

    suspend fun setAutoSync(value: Boolean) {
        context.dataStore.edit { it[AUTO_SYNC] = value }
    }

    private companion object {
        val WIFI_ONLY = booleanPreferencesKey("wifi_only")
        val AUTO_SYNC = booleanPreferencesKey("auto_sync")
    }
}
