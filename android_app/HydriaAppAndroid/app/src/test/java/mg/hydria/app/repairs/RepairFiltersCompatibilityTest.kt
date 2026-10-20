package mg.hydria.app.repairs

import mg.hydria.shared.planning.PlanningFilter
import mg.hydria.shared.rules.planning.PlanningViewModelGateway
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class RepairFiltersCompatibilityTest {
    @Test fun repairFiltersPreserveInputOrderAndDoNotChangePlanningSelection() {
        val repairs = RepairScreenModel().filters
        val planning = PlanningViewModelGateway()
        val urgent = JSONObject("""{"id":"urgent","date_prevue":"2026-09-09","assigne_a":"Alice","region":"Nord"}""")
        val older = JSONObject("""{"id":"older","date_prevue":"2026-09-07","participants":"Bob, Alice","region":"Sud"}""")
        val input = listOf(urgent, older)
        repairs.replaceItems(input, "2026-09-07")
        planning.replaceItems(input, "2026-09-07")
        repairs.selectFilter(PlanningFilter.EMPLOYEE, "nom:Alice")
        assertEquals(input, repairs.state.items)
        repairs.selectFilter(PlanningFilter.REGION, "nom:Sud")
        assertSame(older, repairs.state.items.single())
        assertEquals("", planning.state.filters.regionId)
        assertEquals("", planning.state.filters.employeeId)
        assertEquals(input, planning.state.items)
        repairs.replaceItems(listOf(urgent), "2026-09-07")
        assertEquals("", repairs.state.filters.regionId)
        assertEquals("nom:Alice", repairs.state.filters.employeeId)
        assertSame(urgent, repairs.state.items.single())
    }
}
