package mg.hydria.shared.search

data class SearchWork<T>(val item: T, val name: String, val type: String, val village: String, val commune: String)
object OfflineWorkSearch {
    fun subtitle(type: String, village: String, commune: String): String =
        listOf(type, village, commune).filter { it.isNotBlank() }.joinToString(" · ")
    fun <T> find(works: List<SearchWork<T>>, query: String): List<T> {
        val needle = query.lowercase()
        return works.filter {
            needle.isBlank() || listOf(it.name, it.type, it.village, it.commune).joinToString(" ").lowercase().contains(needle)
        }.map { it.item }
    }
}
