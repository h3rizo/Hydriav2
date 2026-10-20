package mg.hydria.shared.volume

import kotlin.test.*

class VolumeConfirmationRulesTest {
    @Test fun accountAndConfirmationMustMatchExactly() {
        VolumeConfirmationRules.requireAccount("a","a")
        VolumeConfirmationRules.requireUuid("id","id")
        assertEquals("Opération d'une autre session",assertFailsWith<IllegalArgumentException> {
            VolumeConfirmationRules.requireAccount("other","a")
        }.message)
        assertEquals("Confirmation serveur manquante",assertFailsWith<IllegalArgumentException> {
            VolumeConfirmationRules.requireUuid("wrong","id")
        }.message)
    }
    @Test fun reviewRequiresTenTrimmedCharactersAndAConflictMarker() {
        assertEquals("0123456789",VolumeConfirmationRules.reviewNote(" 0123456789 "))
        assertFailsWith<IllegalArgumentException> { VolumeConfirmationRules.reviewNote(" 123456789 ") }
        assertFailsWith<IllegalArgumentException> { VolumeConfirmationRules.requireConflict(false) }
        VolumeConfirmationRules.requireConflict(true)
        assertEquals("refusee",VolumeConfirmationRules.failedRecapState(409))
        assertEquals("en_attente",VolumeConfirmationRules.failedRecapState(500))
    }
}
