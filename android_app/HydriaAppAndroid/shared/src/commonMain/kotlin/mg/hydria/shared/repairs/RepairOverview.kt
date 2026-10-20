package mg.hydria.shared.repairs

/** Platform adapters provide normalized sort keys and retain the original item. */
data class RepairEntry<T>(val item: T, val id: String, val workKey: String,
    val workSortKey: String, val activitySortKey: String, val dateKey: String,
    val criticality: Int, val completed: Boolean, val outsidePerimeter: Boolean)
data class RepairGroup<T>(val workKey: String, val items: List<T>)
data class RepairOverviewState<T>(val groups: List<RepairGroup<T>>, val completedCount: Int)

object RepairOverview {
    fun <T> isCompleted(entry: RepairEntry<T>, pendingCompletionIds: Set<String>): Boolean =
        entry.completed || entry.id in pendingCompletionIds

    fun <T> visible(entries: List<RepairEntry<T>>, pendingCompletionIds: Set<String>,
        showCompleted: Boolean, showOutsidePerimeter: Boolean): List<T> = entries.filter {
        (showCompleted || !isCompleted(it, pendingCompletionIds)) &&
            (showOutsidePerimeter || !it.outsidePerimeter)
    }.map { it.item }

    fun <T> prepare(entries: List<RepairEntry<T>>, pendingCompletionIds: Set<String>): RepairOverviewState<T> {
        val groups = entries.groupBy { it.workKey }.entries.sortedWith(
            compareByDescending<Map.Entry<String, List<RepairEntry<T>>>> { group ->
                group.value.maxOf { it.criticality }
            }.thenBy { group -> group.value.minOf { it.dateKey } }
                .thenBy { group -> group.value.first().workSortKey })
        return RepairOverviewState(groups.map { group ->
            RepairGroup(group.key, group.value.sortedWith(
                compareByDescending<RepairEntry<T>> { it.criticality }
                    .thenBy { it.dateKey }.thenBy { it.activitySortKey }).map { it.item })
        }, entries.count { isCompleted(it, pendingCompletionIds) })
    }
}
