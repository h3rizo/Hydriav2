package mg.hydria.shared.planning

import kotlin.test.*

class PlanningViewModelTest {
    private fun record(id: String, employee: String, region: String, district: String, commune: String, date: String = "2026-09-07",
        work: String = "") =
        PlanningRecord(PlanningEntry(id, date), listOf(PlanningOption(employee, employee)),
            PlanningOption(region, region), PlanningOption(district, district), PlanningOption(commune, commune), work)
    private val records = listOf(record("a", "Alice", "R1", "D1", "C1"),
        record("b", "Bob", "R1", "D2", "C2", "2026-09-08"), record("c", "Alice", "R2", "D3", "C3"))
    private fun model() = PlanningViewModel<String>().apply { replaceRecords(records, "2026-09-07") }

    @Test fun regionAndDistrictChangesClearDescendants() {
        val model = model()
        model.selectFilter(PlanningFilter.REGION, "R1")
        assertEquals(listOf("", "D1", "D2"), model.state.districtOptions.map { it.id })
        model.selectFilter(PlanningFilter.DISTRICT, "D1")
        model.selectFilter(PlanningFilter.COMMUNE, "C1")
        assertEquals(listOf("a"), model.state.items)
        model.selectFilter(PlanningFilter.DISTRICT, "D2")
        assertEquals("", model.state.filters.communeId)
        assertEquals(listOf("", "C2"), model.state.communeOptions.map { it.id })
        model.selectFilter(PlanningFilter.REGION, "R2")
        assertEquals(PlanningFilters(regionId = "R2"), model.state.filters)
        assertEquals(listOf("c"), model.state.items)
    }
    @Test fun employeeFilterDoesNotReduceGeographicOptions() {
        val model = model()
        model.selectFilter(PlanningFilter.EMPLOYEE, "Alice")
        assertEquals(listOf("a", "c"), model.state.items)
        assertEquals(4, model.state.districtOptions.size)
        model.selectFilter(PlanningFilter.COMMUNE, "C2")
        assertTrue(model.state.items.isEmpty())
        assertEquals(2, model.state.activeFilterCount)
        assertEquals("Périmètre affiché : Alice · C2", model.state.perimeterSummary)
    }
    @Test fun refreshRetainsValidSelectionAndDropsRemovedOptions() {
        val model = model()
        model.selectFilter(PlanningFilter.EMPLOYEE, "Alice")
        model.selectFilter(PlanningFilter.REGION, "R1")
        model.replaceRecords(records.take(2), "2026-09-07")
        assertEquals(PlanningFilters(employeeId = "Alice", regionId = "R1"), model.state.filters)
        model.replaceRecords(records.takeLast(1), "2026-09-07")
        assertEquals(PlanningFilters(employeeId = "Alice"), model.state.filters)
        assertEquals(1, model.state.totalCount)
    }
    @Test fun selectedDaySurvivesRefreshAndFallsBackWhenFilteredOut() {
        val model = model()
        model.selectDate("2026-09-08")
        model.replaceRecords(records, "2026-09-07")
        assertEquals("2026-09-08", model.state.agenda.selectedDate)
        model.selectDate("missing")
        assertEquals("2026-09-08", model.state.agenda.selectedDate)
        model.selectFilter(PlanningFilter.EMPLOYEE, "Alice")
        assertEquals("2026-09-07", model.state.agenda.selectedDate)
        assertEquals(model.state, model.states.value)
    }
    @Test fun optionsDeduplicateAndEmptyRefreshResetsFilters() {
        val model = model()
        assertEquals(listOf("", "Alice", "Bob"), model.state.employeeOptions.map { it.id })
        model.selectFilter(PlanningFilter.REGION, "R1")
        model.replaceRecords(emptyList(), "2026-09-07")
        assertEquals(PlanningFilters(), model.state.filters)
        assertTrue(model.state.agenda.days.isEmpty())
        assertEquals(0, model.state.activeFilterCount)
    }
    @Test fun workQueryFiltersAllTermsCombinesWithOtherFiltersAndIsNotCountedAsPanelFilter() {
        val withWorks = listOf(
            record("a", "Alice", "R1", "D1", "C1", work = "Ambato AEPG"),
            record("b", "Bob", "R1", "D1", "C1", "2026-09-08", work = "Ambanja BP"),
            record("c", "Alice", "R1", "D1", "C1", "2026-09-09", work = "Ambato BP"),
            record("d", "Alice", "R1", "D1", "C1", "2026-09-10"))
        val model = PlanningViewModel<String>().apply { replaceRecords(withWorks, "2026-09-07") }
        model.setQuery("amba")
        assertEquals(listOf("a", "b", "c"), model.state.items)
        assertEquals(0, model.state.activeFilterCount)
        model.setQuery("  AMBATO bp ")
        assertEquals(listOf("c"), model.state.items)
        model.setQuery("ambato")
        model.selectFilter(PlanningFilter.EMPLOYEE, "Alice")
        assertEquals(listOf("a", "c"), model.state.items)
        assertEquals(listOf("2026-09-07", "2026-09-09"), model.state.agenda.days.map { it.dateKey })
        model.setQuery("")
        assertEquals(listOf("a", "c", "d"), model.state.items)
    }
    @Test fun validationPreservesErrorPriorityAndPublishesIt() {
        val model = model()
        assertEquals(PlanningFormError.EMPLOYEE, model.validateForm(PlanningDraft(null, null, "bad")).error)
        assertNull(model.validateForm(PlanningDraft("1", null, "bad")).fields)
        assertEquals(PlanningFormError.ACTIVITY, model.states.value.formError)
        assertEquals(PlanningFormError.DATE_FORMAT, model.validateForm(PlanningDraft("1", "2", "7/9/2026")).error)
        model.clearFormError()
        assertNull(model.state.formError)
    }
    @Test fun createPayloadKeepsOptionalWorkAndTrimsText() {
        val result = PlanningFormRules.validate(PlanningDraft("1", "2", " 2026-09-07 ", remark = " hello "))
        assertNull(result.error)
        assertEquals(mapOf("employe_id" to "1", "fiche_poste_id" to "2", "ouvrage_id" to "",
            "date" to "2026-09-07", "statut" to "en_cours", "remarque" to "hello"), result.fields)
    }
    @Test fun updateKeepsExplicitEmptyStatus() {
        val result = PlanningFormRules.validate(PlanningDraft("1", "2", "2026-02-28", "3", "", existingId = "4"))
        assertNull(result.error)
        assertEquals("4", result.fields?.get("id"))
        assertEquals("", result.fields?.get("statut"))
        assertFalse(result.fields!!.containsKey("priorite"))
    }
    @Test fun impossibleDatesAreRejectedBeforeQueueing() {
        // REP_PLAN-10 : bien formée ne suffit plus, la date doit exister au calendrier.
        for (bad in listOf("2026-02-30", "2026-02-31", "2026-13-01", "2026-00-10", "2026-04-31", "2026-02-29", "2026-09-00")) {
            val result = PlanningFormRules.validate(PlanningDraft("1", "2", bad))
            assertEquals(PlanningFormError.DATE_FORMAT, result.error, bad)
            assertNull(result.fields, bad)
        }
    }
    @Test fun realDatesAreAccepted() {
        for (good in listOf("2026-02-28", "2024-02-29", "2026-12-31", " 2026-09-07 ")) {
            assertNull(PlanningFormRules.validate(PlanningDraft("1", "2", good)).error, good)
        }
    }
    @Test fun dateErrorMessageIsNeutralWhetherTheDateIsPickedOrTyped() {
        // Desktop et Android partagent ce message : « choisissez » était trompeur là où la date se tape.
        assertEquals("Date invalide : ce jour n'existe pas (AAAA-MM-JJ)", PlanningFormError.DATE_FORMAT.message)
    }
    @Test fun impossibleDateIsPublishedByTheViewModel() {
        val model = model()
        assertEquals(PlanningFormError.DATE_FORMAT, model.validateForm(PlanningDraft("1", "2", "2026-02-30")).error)
        assertEquals(PlanningFormError.DATE_FORMAT, model.state.formError)
    }
    @Test fun isoDateRecognisesOnlyRealCalendarDays() {
        assertTrue(IsoDate.isReal("2026-10-19"))
        assertTrue(IsoDate.isReal("2024-02-29"))
        assertFalse(IsoDate.isReal("2026-02-29"))
        assertFalse(IsoDate.isReal("2026-02-30"))
        assertFalse(IsoDate.isReal("2026-13-01"))
        assertFalse(IsoDate.isReal("19/10/2026"))
        assertFalse(IsoDate.isReal("2026-1-5"))
        assertFalse(IsoDate.isReal("2026-10-19T10:00"))
        assertFalse(IsoDate.isReal(""))
    }
}
