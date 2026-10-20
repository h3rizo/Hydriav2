package mg.hydria.shared.search

import kotlin.test.*

class OfflineWorkSearchTest {
    private val works = listOf(SearchWork(1, "Source École", "AEP", "Village Nord", "Commune A"),
        SearchWork(2, "Puits", "Forage", "Village Sud", "Commune B"))
    @Test fun findsAcrossEachFieldIgnoringCase() {
        for (query in listOf("ÉCOLE", "aep", "nord", "commune a")) assertEquals(listOf(1), OfflineWorkSearch.find(works, query))
        assertEquals(listOf(2), OfflineWorkSearch.find(works, "forage"))
    }
    @Test fun blankQueryPreservesOrderAndDuplicates() {
        assertEquals(listOf(1, 2, 1), OfflineWorkSearch.find(works + works.first(), " \t"))
    }
    @Test fun keepsLegacySubstringAndAccentSemantics() {
        assertTrue(OfflineWorkSearch.find(works, "ecole").isEmpty())
        assertTrue(OfflineWorkSearch.find(works, "Source Nord").isEmpty())
        assertEquals(listOf(1), OfflineWorkSearch.find(works, "École AEP"))
    }
    @Test fun subtitleOmitsOnlyBlankFields() {
        assertEquals(" AEP  · Nord", OfflineWorkSearch.subtitle(" AEP ", " ", "Nord"))
        assertEquals("", OfflineWorkSearch.subtitle("", "", ""))
    }
}
