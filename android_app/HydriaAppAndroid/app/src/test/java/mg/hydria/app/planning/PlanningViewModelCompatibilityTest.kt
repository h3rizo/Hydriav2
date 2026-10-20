package mg.hydria.app.planning

import mg.hydria.shared.planning.PlanningFilter
import mg.hydria.shared.rules.planning.PlanningViewModelGateway
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class PlanningViewModelCompatibilityTest {
    @Test fun legacyEmployeeNamesAndGeographyWithoutIdsRemainFilterable() {
        val first = JSONObject("""{"date":"2026-09-07","employe":" Alice, Bob ","participants":"Alice","region":" Nord ","district":" D1 ","commune":" C1 "}""")
        val second = JSONObject("""{"date":"2026-09-08","employes":[{"id":7,"nom":" Claire "}],"employe":"Ignored","region_id":" 2 ","region":"Sud","district":"D2","commune":"C2"}""")
        val model = PlanningViewModelGateway()
        model.replaceItems(listOf(first, second), "2026-09-07")
        assertEquals(listOf("", "nom:Alice", "nom:Bob", "7"), model.state.employeeOptions.map { it.id })
        assertEquals(listOf("", "nom:Nord", "2"), model.state.regionOptions.map { it.id })
        model.selectFilter(PlanningFilter.EMPLOYEE, "nom:Bob")
        assertSame(first, model.state.items.single())
        model.selectFilter(PlanningFilter.REGION, "2")
        assertTrue(model.state.items.isEmpty())
        model.selectFilter(PlanningFilter.EMPLOYEE, "7")
        assertSame(second, model.state.items.single())
    }
    @Test fun workNameSearchIgnoresAccentsCaseAndWordOrder() {
        val first = JSONObject("""{"date":"2026-09-07","ouvrage_nom":"Réservoir Ambato Nord"}""")
        val second = JSONObject("""{"date":"2026-09-08","ouvrage_nom":"Forage Ambanja"}""")
        val withoutWork = JSONObject("""{"date":"2026-09-09"}""")
        val model = PlanningViewModelGateway()
        model.replaceItems(listOf(first, second, withoutWork), "2026-09-07")
        model.setQuery("RESERVOIR nord")
        assertSame(first, model.state.items.single())
        model.setQuery("amba")
        assertEquals(listOf(first, second), model.state.items)
        model.setQuery("")
        assertEquals(3, model.state.items.size)
    }
    @Test fun invalidArrayEntriesFallBackToCsvAndMissingDatesRemainVisible() {
        val item = JSONObject("""{"employes":[null,{},"bad"],"assigne_a":" Zoe, Zoe ","participants":" Ana "}""")
        val model = PlanningViewModelGateway()
        model.replaceItems(listOf(item), "2026-09-07")
        assertEquals(listOf("", "nom:Ana", "nom:Zoe"), model.state.employeeOptions.map { it.id })
        assertEquals("9999-12-31", model.state.agenda.days.single().dateKey)
        assertEquals(1, model.state.regionOptions.size)
        assertSame(item, model.state.items.single())
    }
}
