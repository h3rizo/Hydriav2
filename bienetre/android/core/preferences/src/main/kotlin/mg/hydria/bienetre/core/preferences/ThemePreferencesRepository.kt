package mg.hydria.bienetre.core.preferences

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

enum class ThemeMode { System, Light, Dark }

private val Context.settingsDataStore by preferencesDataStore(name = "app_settings")

@Singleton
class ThemePreferencesRepository @Inject constructor(
    @param:ApplicationContext private val context: Context,
) {
    val themeMode: Flow<ThemeMode> = context.settingsDataStore.data
        .catch { error ->
            if (error is IOException) emit(androidx.datastore.preferences.core.emptyPreferences())
            else throw error
        }
        .map { preferences ->
            preferences[THEME_KEY]?.let { stored ->
                ThemeMode.entries.firstOrNull { it.name == stored }
            } ?: ThemeMode.System
        }

    suspend fun setThemeMode(mode: ThemeMode) {
        context.settingsDataStore.edit { preferences -> preferences[THEME_KEY] = mode.name }
    }

    private companion object {
        val THEME_KEY = stringPreferencesKey("theme_mode")
    }
}
