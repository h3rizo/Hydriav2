package mg.hydria.shared.repairs

import kotlin.test.*

class RepairOverviewTest {
    private fun entry(id: String, work: String = "A", priority: Int = 2, date: String = "2026-09-07",
        activity: String = id, completed: Boolean = false, outside: Boolean = false) =
        RepairEntry(id, id, work, work.lowercase(), activity, date, priority, completed, outside)

    @Test fun visibilityCombinesPendingCompletionAndPerimeter() {
        val items = listOf(entry("open"), entry("done", completed = true), entry("pending"), entry("outside", outside = true))
        assertEquals(listOf("open"), RepairOverview.visible(items, setOf("pending"), false, false))
        assertEquals(listOf("open", "outside"), RepairOverview.visible(items, setOf("pending"), false, true))
        assertEquals(listOf("open", "done", "pending"), RepairOverview.visible(items, setOf("pending"), true, false))
        assertEquals(items.map { it.item }, RepairOverview.visible(items, setOf("pending"), true, true))
    }
    @Test fun groupsUseHighestPriorityThenEarliestDateThenName() {
        val items = listOf(entry("b", "B"), entry("a", "A"), entry("urgent", "U", 4, "2026-10-01"),
            entry("early", "E", 2, "2026-09-01"))
        assertEquals(listOf("U", "E", "A", "B"), RepairOverview.prepare(items, emptySet()).groups.map { it.workKey })
    }
    @Test fun groupOrderingKeepsEarliestDateEvenOnLowerPriorityItem() {
        val items = listOf(entry("urgentB", "B", 4, "2026-09-09"), entry("urgentA", "A", 4, "2026-09-10"),
            entry("olderA", "A", 1, "2026-09-01"))
        val result = RepairOverview.prepare(items, emptySet())
        assertEquals(listOf("A", "B"), result.groups.map { it.workKey })
        assertEquals(listOf("urgentA", "olderA"), result.groups.first().items)
    }
    @Test fun activitiesUsePriorityDateNameAndStableTieOrder() {
        val items = listOf(entry("z", activity = "z"), entry("a2", activity = "a"), entry("a1", activity = "a"),
            entry("urgent", priority = 5), entry("early", date = "2026-09-01"))
        assertEquals(listOf("urgent", "early", "a2", "a1", "z"), RepairOverview.prepare(items, emptySet()).groups.single().items)
    }
    @Test fun completedCountDoesNotDoubleCountPendingAndServerCompletion() {
        val items = listOf(entry("both", completed = true), entry("pending"), entry("open"))
        assertEquals(2, RepairOverview.prepare(items, setOf("both", "pending", "missing")).completedCount)
        val empty = RepairOverview.prepare(emptyList<RepairEntry<String>>(), setOf("missing"))
        assertTrue(empty.groups.isEmpty())
        assertEquals(0, empty.completedCount)
    }
}
