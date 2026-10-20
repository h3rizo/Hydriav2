package mg.hydria.bienetre.feature.shopping

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import mg.hydria.bienetre.core.model.ShoppingItem
import mg.hydria.bienetre.core.model.ShoppingList
import mg.hydria.bienetre.core.model.WellbeingArticle
import mg.hydria.bienetre.core.model.IngredientOption
import mg.hydria.bienetre.core.model.IngredientSupplyPreference
import mg.hydria.bienetre.core.model.VendorOption
import mg.hydria.bienetre.core.model.WellbeingSupplyPreference
import mg.hydria.bienetre.core.network.ApiErrorKind
import mg.hydria.bienetre.core.network.ApiException
import mg.hydria.bienetre.core.network.ShoppingRepository
import java.time.LocalDate
import javax.inject.Inject

data class ShoppingContent(
    val lists: List<ShoppingList>,
    val articles: List<WellbeingArticle>,
    val ingredients: List<IngredientOption> = emptyList(),
    val vendors: List<VendorOption> = emptyList(),
    val ingredientPreferences: List<IngredientSupplyPreference> = emptyList(),
    val wellbeingPreferences: List<WellbeingSupplyPreference> = emptyList(),
    val busyItemIds: Set<Long> = emptySet(),
    val generating: Boolean = false,
    val savingPreferences: Boolean = false,
    val offline: Boolean = false,
    val message: String? = null,
) {
    val items get() = lists.flatMap { it.items }
    val checkedCount get() = items.count { it.checked }
    val estimatedTotal get() = items.sumOf { it.estimatedTotal }
}

sealed interface ShoppingUiState {
    data object Loading : ShoppingUiState
    data class Content(val data: ShoppingContent) : ShoppingUiState
    data class Error(val message: String) : ShoppingUiState
    data object SessionExpired : ShoppingUiState
}

@HiltViewModel
class ShoppingViewModel @Inject constructor(private val repository: ShoppingRepository) : ViewModel() {
    private val _state = MutableStateFlow<ShoppingUiState>(ShoppingUiState.Loading)
    val state: StateFlow<ShoppingUiState> = _state.asStateFlow()
    init { load() }

    fun load() {
        _state.value = ShoppingUiState.Loading
        viewModelScope.launch { runCatching { repository.load() }
            .onSuccess { _state.value = ShoppingUiState.Content(it.toContent()) }
            .onFailure(::fail) }
    }

    fun generate(start: String, end: String) {
        val from = runCatching { LocalDate.parse(start) }.getOrNull()
        val to = runCatching { LocalDate.parse(end) }.getOrNull()
        if (from == null || to == null || to < from || to.isAfter(from.plusDays(31))) {
            message("Utilisez des dates AAAA-MM-JJ sur une période de 31 jours maximum."); return
        }
        mutate(generating = true) {
            repository.generate(start, end)
            reload("Liste générée depuis les repas planifiés.")
        }
    }

    fun check(item: ShoppingItem, checked: Boolean) = mutate(item.id) {
        val updated = repository.check(item, checked)
        replace(updated, when {
            updated.pendingSync -> "Modification conservée hors connexion. Synchronisation automatique à venir."
            checked -> "Article acheté."
            else -> "Article remis à acheter."
        })
    }

    fun purchaseDate(item: ShoppingItem, date: String?) {
        if (date != null && runCatching { LocalDate.parse(date) }.isFailure) { message("La date doit utiliser le format AAAA-MM-JJ."); return }
        mutate(item.id) { replace(repository.purchaseDate(item, date), "Date d’achat enregistrée.") }
    }

    fun price(item: ShoppingItem, value: String, unit: String) {
        val parsed = value.replace(',', '.').toDoubleOrNull()
        if (parsed == null || parsed < 0) { message("Saisissez un prix positif."); return }
        mutate(item.id) { replace(repository.price(item, parsed, unit), "Prix enregistré pour le vendeur préféré.") }
    }

    fun addManual(articleId: Long, quantity: String, unit: String) {
        val current = content() ?: return
        val list = current.lists.firstOrNull() ?: run { message("Générez d’abord une liste de courses."); return }
        val parsed = quantity.replace(',', '.').toDoubleOrNull()
        if (parsed == null || parsed <= 0) { message("La quantité doit être positive."); return }
        mutate {
            val updated = repository.addManual(list.id, articleId, parsed, unit)
            val latest = content() ?: return@mutate
            _state.value = ShoppingUiState.Content(latest.copy(lists = latest.lists.map { if (it.id == updated.id) updated else it }, message = "Article bien-être ajouté."))
        }
    }

    fun saveIngredientPreference(ingredientId: Long, vendorId: Long?, disliked: Boolean, unavailable: Boolean, note: String) {
        if (note.length > 255) { message("La note est limitée à 255 caractères."); return }
        val existing = content()?.ingredientPreferences?.firstOrNull { it.ingredientId == ingredientId }
        val empty = vendorId == null && !disliked && !unavailable && note.isBlank()
        if (empty && existing == null) { message("Aucune préférence à enregistrer."); return }
        mutate(savingPreferences = true) {
            if (empty) repository.deleteIngredientPreference(requireNotNull(existing).id)
            else repository.saveIngredientPreference(ingredientId, vendorId, disliked, unavailable, note)
            reload("Préférence d’ingrédient enregistrée.")
        }
    }

    fun saveWellbeingPreference(articleId: Long, vendorId: Long?, unavailable: Boolean, note: String) {
        if (note.length > 255) { message("La note est limitée à 255 caractères."); return }
        val existing = content()?.wellbeingPreferences?.firstOrNull { it.articleId == articleId }
        val empty = vendorId == null && !unavailable && note.isBlank()
        if (empty && existing == null) { message("Aucune préférence à enregistrer."); return }
        mutate(savingPreferences = true) {
            if (empty) repository.deleteWellbeingPreference(requireNotNull(existing).id)
            else repository.saveWellbeingPreference(articleId, vendorId, unavailable, note)
            reload("Préférence d’article enregistrée.")
        }
    }

    private fun mutate(itemId: Long? = null, generating: Boolean = false, savingPreferences: Boolean = false, action: suspend () -> Unit) {
        val current = content() ?: return
        _state.value = ShoppingUiState.Content(current.copy(
            busyItemIds = itemId?.let { current.busyItemIds + it } ?: current.busyItemIds,
            generating = generating || current.generating,
            savingPreferences = savingPreferences || current.savingPreferences,
            message = null,
        ))
        viewModelScope.launch { runCatching { action() }.onFailure(::mutationFailed) }
    }

    private suspend fun reload(message: String) {
        val overview = repository.load()
        _state.value = ShoppingUiState.Content(overview.toContent(message))
    }

    private fun replace(updated: ShoppingItem, message: String) {
        val current = content() ?: return
        _state.value = ShoppingUiState.Content(current.copy(
            lists = current.lists.map { list -> list.copy(items = list.items.map { if (it.id == updated.id) updated else it }) },
            busyItemIds = current.busyItemIds - updated.id,
            message = message,
        ))
    }

    private fun message(value: String) { content()?.let { _state.value = ShoppingUiState.Content(it.copy(message = value)) } }
    private fun content() = (_state.value as? ShoppingUiState.Content)?.data
    private fun fail(error: Throwable) { _state.value = error.toState() }
    private fun mutationFailed(error: Throwable) {
        if ((error as? ApiException)?.kind == ApiErrorKind.Unauthorized) _state.value = ShoppingUiState.SessionExpired
        else content()?.let { _state.value = ShoppingUiState.Content(it.copy(busyItemIds = emptySet(), generating = false, savingPreferences = false, message = error.messageForUser())) }
    }
}

private fun mg.hydria.bienetre.core.model.ShoppingOverview.toContent(message: String? = null) = ShoppingContent(
    lists, articles, ingredients, vendors, ingredientPreferences, wellbeingPreferences, offline = offline, message = message,
)

private fun Throwable.messageForUser() = when ((this as? ApiException)?.kind) {
    ApiErrorKind.Network -> "Connexion indisponible. La modification n’a pas été enregistrée."
    ApiErrorKind.Forbidden -> "Cette action n’est pas autorisée."
    else -> "L’action a échoué. Vérifiez le vendeur préféré et les données saisies."
}
private fun Throwable.toState() = when ((this as? ApiException)?.kind) {
    ApiErrorKind.Unauthorized -> ShoppingUiState.SessionExpired
    else -> ShoppingUiState.Error(messageForUser())
}
