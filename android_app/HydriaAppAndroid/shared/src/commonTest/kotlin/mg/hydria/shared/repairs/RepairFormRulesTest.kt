package mg.hydria.shared.repairs

import kotlin.test.*

class RepairFormRulesTest {
    @Test fun missingFieldsKeepLegacyErrorPriority() {
        assertEquals(RepairFormError.EMPLOYEE, RepairFormRules.validate(RepairDraft(null, null, "", "bad")).error)
        assertEquals(RepairFormError.ACTIVITY, RepairFormRules.validate(RepairDraft("1", null, "", "bad")).error)
        val missingWork = RepairFormRules.validate(RepairDraft("1", "2", "  ", "bad"))
        assertEquals(RepairFormError.WORK, missingWork.error)
        assertNull(missingWork.fields)
        assertEquals(RepairFormError.DATE_FORMAT, RepairFormRules.validate(RepairDraft("1", "2", "3", "07/09/2026")).error)
    }
    @Test fun creationKeepsAllQueueFieldsAndDefaults() {
        val result = RepairFormRules.validate(RepairDraft("1", "2", "3", " 2026-09-07 ", remark = " Note "))
        assertNull(result.error)
        assertEquals(mapOf("employe_id" to "1", "fiche_poste_id" to "2", "ouvrage_id" to "3",
            "date" to "2026-09-07", "statut" to "en_cours", "priorite" to "normale", "remarque" to "Note"), result.fields)
    }
    @Test fun updatePreservesIdAndExplicitStatusAndPriority() {
        val result = RepairFormRules.validate(RepairDraft("1", "2", "3", "2026-02-28", status = "", priority = "urgente", existingId = "42"))
        assertNull(result.error)
        assertEquals("42", result.fields?.get("id"))
        assertEquals("", result.fields?.get("statut"))
        assertEquals("urgente", result.fields?.get("priorite"))
    }
    @Test fun impossibleDatesAreRejectedBeforeQueueing() {
        // REP_PLAN-10 : « 2026-02-30 » a la bonne forme mais n'existe pas.
        for (bad in listOf("2026-02-30", "2026-02-31", "2026-13-01", "2026-04-31", "2026-02-29")) {
            val result = RepairFormRules.validate(RepairDraft("1", "2", "3", bad))
            assertEquals(RepairFormError.DATE_FORMAT, result.error, bad)
            assertNull(result.fields, bad)
        }
        assertNull(RepairFormRules.validate(RepairDraft("1", "2", "3", "2024-02-29")).error)
    }
    @Test fun dateErrorMessageIsNeutralWhetherTheDateIsPickedOrTyped() {
        assertEquals("Date invalide : ce jour n'existe pas (AAAA-MM-JJ)", RepairFormError.DATE_FORMAT.message)
    }
    @Test fun blankUpdateIdIsOmitted() {
        val result = RepairFormRules.validate(RepairDraft("1", "2", "3", "2026-09-07", priority = "", existingId = " "))
        assertFalse(result.fields!!.containsKey("id"))
        assertEquals("", result.fields["priorite"])
    }
    @Test fun withoutTargetNoTargetFieldIsSent() {
        val fields = RepairFormRules.validate(RepairDraft("1", "2", "3", "2026-09-07")).fields!!
        assertFalse(fields.containsKey("equipement_id"))
        assertFalse(fields.containsKey("point_eau_id"))
        assertFalse(fields.containsKey("composants_ids"))
    }
    @Test fun pointEauTargetWithComponentsIsJoinedForFormEncoding() {
        val target = RepairTarget(pointEauId = " pe1 ", componentIds = listOf("c1", " c2 ", "c1", ""))
        val fields = RepairFormRules.validate(RepairDraft("1", "2", "3", "2026-09-07", target = target)).fields!!
        assertEquals("", fields["equipement_id"])
        assertEquals("pe1", fields["point_eau_id"])
        assertEquals("c1,c2", fields["composants_ids"])
    }
    @Test fun emptyTargetExplicitlyClearsServerSide() {
        val fields = RepairFormRules.validate(RepairDraft("1", "2", "3", "2026-09-07", target = RepairTarget())).fields!!
        assertEquals(mapOf("equipement_id" to "", "point_eau_id" to "", "composants_ids" to ""),
            fields.filterKeys { it in setOf("equipement_id", "point_eau_id", "composants_ids") })
    }
    @Test fun equipmentAndPointTogetherAreRejected() {
        val target = RepairTarget(equipmentId = "e1", pointEauId = "p1")
        assertEquals(RepairFormError.TARGET_CONFLICT,
            RepairFormRules.validate(RepairDraft("1", "2", "3", "2026-09-07", target = target)).error)
    }
    @Test fun componentsRequireATarget() {
        val target = RepairTarget(componentIds = listOf("c1"))
        assertEquals(RepairFormError.COMPONENTS_WITHOUT_TARGET,
            RepairFormRules.validate(RepairDraft("1", "2", "3", "2026-09-07", target = target)).error)
    }
}
