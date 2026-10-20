package mg.hydria.app.calculator

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** CALC_VOL-04 : « Tout effacer » passe par CalculatorRepository.clearMemory, en une seule écriture. */
class CalculatorRepositoryTest {
    /** Stockage factice : une ligne par compte, remplacée à chaque écriture ; chaque écriture est journalisée. */
    private class FakeStorage(initial: JSONObject? = null) : CalculatorStateStorage {
        var stored: JSONObject? = initial
        val writes = mutableListOf<JSONObject>()
        override fun state(accountKey: String): JSONObject? = stored
        override fun save(accountKey: String, payload: JSONObject) {
            writes += payload
            stored = payload
        }
    }

    private val book = NamedCashBook(
        name = "Septembre 2026", updatedAt = 123L,
        lines = listOf(CashLine(entryInput = "500")), criteria = emptyList(),
    )

    private fun draftState() = CalculatorState(
        calculationLines = listOf(CalculationLine(label = "Base", expression = "12500 × 3")),
        cashLines = listOf(CashLine(designation = "Entrée", entryInput = "1000")),
        namedCashBooks = listOf(book),
    )

    @Test fun clearMemoryKeepsTheNamedBooksAndEmptiesTheDrafts() {
        val storage = FakeStorage(draftState().toJson())
        val repository = CalculatorRepository(storage, "agent-1")
        assertEquals("12500 × 3", repository.load().calculationLines.single().expression)

        val returned = repository.clearMemory(repository.load().namedCashBooks)

        val reloaded = repository.load()
        assertEquals("Septembre 2026", reloaded.namedCashBooks.single().name)
        assertEquals(0, reloaded.namedCashBooks.single().lines.single().balance.compareTo("500".toBigDecimal()))
        assertEquals("", reloaded.calculationLines.single().expression)
        assertTrue(reloaded.cashLines.all { it.entryInput.isBlank() && it.exitInput.isBlank() })
        assertEquals(returned.namedCashBooks.single().name, reloaded.namedCashBooks.single().name)
    }

    @Test fun clearMemoryWritesTheStateOnceSoNoStepLosesTheBooks() {
        val storage = FakeStorage(draftState().toJson())
        val repository = CalculatorRepository(storage, "agent-1")

        repository.clearMemory(listOf(book))

        // Une seule écriture, et elle contient déjà les cahiers : aucun état intermédiaire sans cahiers.
        assertEquals(1, storage.writes.size)
        assertEquals("Septembre 2026", CalculatorState.fromJson(storage.writes.single()).namedCashBooks.single().name)
    }

    @Test fun clearMemoryWithoutBooksWritesTheDefaultState() {
        val storage = FakeStorage(draftState().toJson())
        val repository = CalculatorRepository(storage, "agent-1")

        repository.clearMemory()

        assertEquals(1, storage.writes.size)
        val reloaded = repository.load()
        assertEquals(emptyList<NamedCashBook>(), reloaded.namedCashBooks)
        assertEquals("", reloaded.calculationLines.single().expression)
    }

    @Test fun loadOfAnEmptyStorageGivesTheDefaultState() {
        val storage = FakeStorage()
        assertNull(storage.state("agent-1"))
        assertEquals(emptyList<NamedCashBook>(), CalculatorRepository(storage, "agent-1").load().namedCashBooks)
    }
}
