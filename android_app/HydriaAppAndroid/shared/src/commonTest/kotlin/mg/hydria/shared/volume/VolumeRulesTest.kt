package mg.hydria.shared.volume

import kotlin.test.*

class VolumeRulesTest {
    @Test fun collectionRequiresValidationAndBlocksPendingCollectionOrPointing() {
        assertTrue(VolumeRules.collectable(false,false,false,setOf("validate")))
        assertTrue(VolumeRules.collectable(false,false,true,emptySet()))
        assertFalse(VolumeRules.collectable(false,false,false,emptySet()))
        assertFalse(VolumeRules.collectable(false,true,true,emptySet()))
        assertFalse(VolumeRules.collectable(true,false,true,emptySet()))
        for(action in listOf("collect","point"))
            assertFalse(VolumeRules.collectable(false,false,true,setOf(action)))
    }
    @Test fun matchingRequiresPositiveExactTotalAndAvailableEntry() {
        assertTrue(VolumeRules.matches(2,30,30,0,false))
        assertFalse(VolumeRules.matches(0,30,30,0,false))
        assertFalse(VolumeRules.matches(2,30,null,0,false))
        assertFalse(VolumeRules.matches(2,30,31,0,false))
        assertFalse(VolumeRules.matches(2,0,0,0,false))
        assertFalse(VolumeRules.matches(2,30,30,0,true))
    }
    @Test fun enqueueChecksKeepPriorityAndDoNotReadDuplicatesForInvalidSession() {
        var calls = 0
        val duplicate = { calls++; true }
        assertEquals("Sélectionnez au moins une facture",
            assertFailsWith<IllegalArgumentException> { VolumeRules.requireCanEnqueue(false,"",duplicate) }.message)
        assertEquals("Reconnectez la session avant de continuer",
            assertFailsWith<IllegalArgumentException> { VolumeRules.requireCanEnqueue(true," ",duplicate) }.message)
        assertEquals(0,calls)
        assertEquals("Cette opération attend déjà une synchronisation",
            assertFailsWith<IllegalArgumentException> { VolumeRules.requireCanEnqueue(true,"account",duplicate) }.message)
        assertEquals(1,calls)
        VolumeRules.requireCanEnqueue(true,"account") { false }
    }
    @Test fun recapScopeRequiresSameWorkAndMonth() {
        assertFailsWith<IllegalArgumentException> { VolumeRules.requireSingleScope(emptyList()) }
        assertFailsWith<IllegalArgumentException> { VolumeRules.requireSingleScope(listOf("a" to "m","b" to "m")) }
        assertFailsWith<IllegalArgumentException> { VolumeRules.requireSingleScope(listOf("a" to "m","a" to "n")) }
        VolumeRules.requireSingleScope(listOf("a" to "m","a" to "m"))
    }
    @Test fun qrMatchesIdentityScopeAndRejectsAmbiguity() {
        val invoice = VolumeQrInvoice(Any(),"id","month","work","number")
        assertSame(invoice.value,VolumeQrRules.find(" HYDRIA|FACTURE|id|ignored-number|month|work ",listOf(invoice)))
        assertSame(invoice.value,VolumeQrRules.find(" number ",listOf(invoice)))
        assertNull(VolumeQrRules.find("HYDRIA|FACTURE|id|number|other|work",listOf(invoice)))
        assertNull(VolumeQrRules.find("number",listOf(invoice,invoice)))
        assertNull(VolumeQrRules.find("hydria|FACTURE|id|number|month|work",listOf(invoice)))
    }
}
