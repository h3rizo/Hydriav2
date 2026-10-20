package mg.hydria.shared.navigation

data class NavigationPage<T>(val body: T, val successful: Boolean, val error: String)
data class NavigationPageCursor(val next: String, val hasMore: Boolean)
data class NavigationDownloadResult(val imported: Int, val message: String)

object NavigationDownload {
    fun <T> run(
        initialCursor: String?,
        fetch: (String?) -> NavigationPage<T>,
        importPage: (T) -> Int,
        readCursor: (T, String?) -> NavigationPageCursor,
        saveCursor: (String) -> Unit,
    ): NavigationDownloadResult {
        var cursor = initialCursor
        var imported = 0
        var pages = 0
        while (pages < 50) {
            val response = fetch(cursor)
            if (!response.successful) {
                val suffix = if (imported > 0) " · $imported élément(s) reçus" else ""
                return NavigationDownloadResult(imported, response.error + suffix)
            }
            imported += importPage(response.body)
            pages++
            val pageCursor = readCursor(response.body, cursor)
            val next = pageCursor.next
            if (next.isNotBlank()) saveCursor(next)
            if (!pageCursor.hasMore || next.isBlank() || next == cursor) break
            cursor = next
        }
        return NavigationDownloadResult(
            imported,
            if (imported > 0) "$imported élément(s) cartographique(s) actualisé(s)" else "Carte terrain à jour",
        )
    }
}
