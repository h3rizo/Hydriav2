package mg.hydria.shared.readings

import kotlin.test.*

class ReadingValidationTest {
    @Test fun requiredFieldsHavePriorityOverVolumeErrors() {
        assertEquals(ReadingError.POINT_REQUIRED, ReadingValidation.validate(false, null, 10.0, -1.0, 0.0, null))
        assertEquals(ReadingError.INVALID_INDEX, ReadingValidation.validate(true, null, 10.0, -1.0, 0.0, null))
        assertEquals(ReadingError.INDEX_DECREASED, ReadingValidation.validate(true, 9.0, 10.0, -1.0, 0.0, null))
        assertEquals(ReadingError.NEGATIVE_NON_BILLABLE, ReadingValidation.validate(true, 10.0, 10.0, -1.0, 2.0, null))
    }
    @Test fun negativeBilledVolumePrecedesMissingCampaign() {
        assertEquals(ReadingError.NEGATIVE_BILLED_VOLUME, ReadingValidation.validate(true, 12.0, 10.0, 1.0, 2.0, null))
        assertEquals(ReadingError.INVALID_CAMPAIGN_DATE, ReadingValidation.validate(true, 12.0, 10.0, 0.0, 0.0, " "))
    }
    @Test fun campaignDateThatDoesNotExistIsRejected() {
        // La forme est bonne mais la date n'existe pas : refusée ici, pas par le serveur des heures plus tard.
        assertEquals(ReadingError.INVALID_CAMPAIGN_DATE, ReadingValidation.validate(true, 12.0, 10.0, 0.0, 0.0, "2026-02-30"))
        assertEquals(ReadingError.INVALID_CAMPAIGN_DATE, ReadingValidation.validate(true, 12.0, 10.0, 0.0, 0.0, "2026-02-29"))
        assertEquals(ReadingError.INVALID_CAMPAIGN_DATE, ReadingValidation.validate(true, 12.0, 10.0, 0.0, 0.0, "2026-13-01"))
        assertEquals(ReadingError.INVALID_CAMPAIGN_DATE, ReadingValidation.validate(true, 12.0, 10.0, 0.0, 0.0, "07/09/2026"))
        assertEquals(ReadingError.INVALID_CAMPAIGN_DATE, ReadingValidation.validate(true, 12.0, 10.0, 0.0, 0.0, "2026-9-7"))
        assertNull(ReadingValidation.validate(true, 12.0, 10.0, 0.0, 0.0, "2024-02-29"))
        assertNull(ReadingValidation.validate(true, 12.0, 10.0, 0.0, 0.0, "2026-10-20"))
    }
    @Test fun dateCheckKeepsTheOrderOfTheOtherChecks() {
        // Une date fausse ne masque aucune erreur qui la précédait.
        val badDate = "2026-02-30"
        assertEquals(ReadingError.POINT_REQUIRED, ReadingValidation.validate(false, null, 10.0, -1.0, 0.0, badDate))
        assertEquals(ReadingError.INVALID_INDEX, ReadingValidation.validate(true, null, 10.0, -1.0, 0.0, badDate))
        assertEquals(ReadingError.INDEX_DECREASED, ReadingValidation.validate(true, 9.0, 10.0, -1.0, 0.0, badDate))
        assertEquals(ReadingError.NEGATIVE_NON_BILLABLE, ReadingValidation.validate(true, 10.0, 10.0, -1.0, 2.0, badDate))
        assertEquals(ReadingError.NEGATIVE_BILLED_VOLUME, ReadingValidation.validate(true, 12.0, 10.0, 1.0, 2.0, badDate))
    }
    @Test fun toleranceBoundaryRemainsInclusive() {
        assertNull(ReadingValidation.validate(true, 0.0, 0.0, 0.001, 0.0, "2026-09-07"))
        assertEquals(ReadingError.NEGATIVE_BILLED_VOLUME, ReadingValidation.validate(true, 0.0, 0.0, 0.00101, 0.0, "2026-09-07"))
    }
    @Test fun equalIndexAndFullyDeductedConsumptionAreAccepted() {
        assertNull(ReadingValidation.validate(true, 10.0, 10.0, 0.0, 0.0, "2026-09-07"))
        assertNull(ReadingValidation.validate(true, 15.0, 10.0, 2.0, 3.0, "2026-09-07"))
    }
    @Test fun remarkIsRequiredWhenConsumptionIsZero() {
        val zero = ReadingValidation.consumption(130.67, 130.67)
        assertEquals(ReadingError.REMARK_REQUIRED_ZERO_CONSUMPTION, ReadingValidation.remarkRequirement(zero, 0.0))
        assertEquals(ReadingError.REMARK_REQUIRED_ZERO_CONSUMPTION, ReadingValidation.validateRemark(zero, 0.0, null))
        assertEquals(ReadingError.REMARK_REQUIRED_ZERO_CONSUMPTION, ReadingValidation.validateRemark(zero, 0.0, ""))
        assertNull(ReadingValidation.validateRemark(zero, 0.0, "Kiosque non utilisé"))
        assertTrue(ReadingValidation.remarkRequired(zero, 0.0))
    }
    @Test fun remarkIsRequiredWhenNonBillableVolumeIsNotZero() {
        assertEquals(ReadingError.REMARK_REQUIRED_NON_BILLABLE, ReadingValidation.remarkRequirement(5.0, 2.0))
        assertEquals(ReadingError.REMARK_REQUIRED_NON_BILLABLE, ReadingValidation.validateRemark(5.0, 0.5, null))
        assertNull(ReadingValidation.validateRemark(5.0, 0.5, "Fuite constatée"))
        // Index pas encore saisi : seul le non facturé peut rendre la remarque obligatoire.
        assertEquals(ReadingError.REMARK_REQUIRED_NON_BILLABLE, ReadingValidation.remarkRequirement(null, 1.0))
        assertNull(ReadingValidation.remarkRequirement(null, 0.0))
    }
    @Test fun zeroConsumptionIsReportedBeforeNonBillableVolume() {
        // Même ordre que le serveur : consommation nulle d'abord.
        assertEquals(ReadingError.REMARK_REQUIRED_ZERO_CONSUMPTION, ReadingValidation.remarkRequirement(0.0, 3.0))
    }
    @Test fun remarkIsOptionalForNormalReadings() {
        assertNull(ReadingValidation.remarkRequirement(12.5, 0.0))
        assertNull(ReadingValidation.validateRemark(12.5, 0.0, null))
        assertNull(ReadingValidation.validateRemark(0.001, 0.0, ""))
        assertFalse(ReadingValidation.remarkRequired(12.5, 0.0))
    }
    @Test fun blankRemarkCountsAsMissingLikeTheServerStrip() {
        assertEquals(ReadingError.REMARK_REQUIRED_ZERO_CONSUMPTION, ReadingValidation.validateRemark(0.0, 0.0, "   "))
        assertEquals(ReadingError.REMARK_REQUIRED_NON_BILLABLE, ReadingValidation.validateRemark(4.0, 1.0, " \n"))
    }
    @Test fun remarkRuleDoesNotChangeTheHistoricValidateContract() {
        // Un index égal au précédent reste valide pour validate() : la remarque se contrôle à part.
        assertNull(ReadingValidation.validate(true, 10.0, 10.0, 0.0, 0.0, "2026-09-07"))
        assertNull(ReadingValidation.validate(true, 15.0, 10.0, 2.0, 3.0, "2026-09-07"))
    }
    @Test fun socialCardsAndBilledVolumeKeepExistingUnits() {
        assertEquals(0.02, ReadingValidation.socialCardVolume(1), 0.0000001)
        assertEquals(1.0, ReadingValidation.socialCardVolume(50), 0.0000001)
        val cards = ReadingValidation.socialCardsVolume(listOf(0.2, 0.4))
        assertEquals(0.6, cards, 0.0000001)
        assertEquals(3.4, ReadingValidation.billedVolume(ReadingValidation.consumption(15.0, 10.0), cards, 1.0), 0.0000001)
        assertEquals(0.0, ReadingValidation.socialCardsVolume(emptyList()), 0.0)
    }
}
