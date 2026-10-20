package mg.hydria.app.navigation.sync

import android.content.Context
import mg.hydria.app.HydriaNetwork
import mg.hydria.app.navigation.data.GeoRepository
import mg.hydria.app.navigation.model.NavigationConfig

class NavigationSyncManager(context: Context, private val repository: GeoRepository) {
    private val preferences = context.getSharedPreferences("hydria_navigation_sync", Context.MODE_PRIVATE)

    data class Result(
        val config: NavigationConfig,
        val imported: Int,
        val message: String,
    )

    fun synchronize(token: String, bbox: String? = null): Result {
        var config = NavigationConfig()
        val configResponse = runCatching { HydriaNetwork.navigationConfig(token) }.getOrNull()
        if (configResponse?.successful == true) config = NavigationConfig.fromJson(configResponse.body)

        val downloaded = mg.hydria.shared.navigation.NavigationDownload.run(
            initialCursor = preferences.getString("cursor", null),
            fetch = { cursor ->
                val response = HydriaNetwork.navigationEntities(token, cursor, bbox)
                mg.hydria.shared.navigation.NavigationPage(response.body, response.successful, response.error)
            },
            importPage = repository::importNavigationPage,
            readCursor = { body, cursor ->
                val page = body.optJSONObject("data") ?: body
                val next = page.optString("next_cursor").ifBlank { page.optString("cursor") }
                mg.hydria.shared.navigation.NavigationPageCursor(
                    next, page.optBoolean("has_more", next.isNotBlank() && next != cursor),
                )
            },
            saveCursor = { next -> preferences.edit().putString("cursor", next).apply() },
        )
        return Result(config, downloaded.imported, downloaded.message)
    }

    fun resetCursor() = preferences.edit().remove("cursor").apply()
}
