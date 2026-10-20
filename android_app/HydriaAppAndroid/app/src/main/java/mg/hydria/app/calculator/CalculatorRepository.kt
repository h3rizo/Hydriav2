package mg.hydria.app.calculator

import mg.hydria.app.OfflineStore
import org.json.JSONObject

/** Persistance du brouillon de calculatrice d'un compte : une lecture, une écriture qui remplace tout l'état. */
interface CalculatorStateStorage {
    fun state(accountKey: String): JSONObject?
    fun save(accountKey: String, payload: JSONObject)
}

class CalculatorRepository internal constructor(
    private val storage: CalculatorStateStorage,
    private val accountKey: String,
) {
    constructor(store: OfflineStore, accountKey: String) : this(
        object : CalculatorStateStorage {
            override fun state(accountKey: String): JSONObject? = store.calculatorState(accountKey)
            override fun save(accountKey: String, payload: JSONObject) = store.saveCalculatorState(accountKey, payload)
        },
        accountKey,
    )

    init { require(accountKey.isNotBlank()) { "Une session Hydria est requise" } }

    fun load(): CalculatorState = CalculatorState.fromJson(storage.state(accountKey))

    fun save(state: CalculatorState): CalculatorState = state.normalized().also {
        storage.save(accountKey, it.toJson())
    }

    /**
     * Vide les brouillons du compte ; les cahiers de caisse nommés ([keepBooks]) sont conservés (CALC_VOL-04).
     * Une seule écriture (l'écriture de l'état remplace la ligne du compte) : si le processus est tué, l'ancien
     * état ou le nouveau reste entier, jamais un état sans les cahiers.
     */
    fun clearMemory(keepBooks: List<NamedCashBook> = emptyList()): CalculatorState =
        CalculatorState(namedCashBooks = keepBooks).also { storage.save(accountKey, it.toJson()) }
}
