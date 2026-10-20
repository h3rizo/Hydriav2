package mg.hydria.logistique.feature.main

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import mg.hydria.logistique.database.LogistiqueDao
import mg.hydria.logistique.network.CreateTransferRequest
import mg.hydria.logistique.network.DeliveryRequest
import mg.hydria.logistique.network.FieldReturnRequest
import mg.hydria.logistique.network.UpdateTransferRequest
import javax.inject.Inject

data class MainUiState(
    val stockCount: Int = 0,
    val lowCount: Int = 0,
    val pendingCount: Int = 0,
    val conflictCount: Int = 0,
    val unallocatedCount: Int = 0,
    val online: Boolean = false,
    val lastSync: String? = null,
)

data class SessionUiState(
    val checking: Boolean = true,
    val authenticated: Boolean = false,
    val loading: Boolean = false,
    val error: String? = null,
)

data class PurchaseReceptionUiState(
    val loadingPurchaseId: String? = null,
    val message: String? = null,
    val error: String? = null,
)

data class OperationUiState(val loading: Boolean = false, val message: String? = null, val error: String? = null)

@HiltViewModel
@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class MainViewModel @Inject constructor(
    dao: LogistiqueDao,
    private val sessionRepository: SessionRepository,
    connectivityObserver: ConnectivityObserver,
) : ViewModel() {
    private val _session = MutableStateFlow(SessionUiState())
    val session: StateFlow<SessionUiState> = _session.asStateFlow()
    private val _stockQuery = MutableStateFlow("")
    val stockQuery: StateFlow<String> = _stockQuery.asStateFlow()
    private val _stockStatus = MutableStateFlow("")
    val stockStatus: StateFlow<String> = _stockStatus.asStateFlow()
    private val _purchaseReception = MutableStateFlow(PurchaseReceptionUiState())
    val purchaseReception: StateFlow<PurchaseReceptionUiState> = _purchaseReception.asStateFlow()
    private val _operation = MutableStateFlow(OperationUiState())
    val operation: StateFlow<OperationUiState> = _operation.asStateFlow()

    val state = combine(
        dao.observeStockPositions(),
        dao.observeActiveOutbox(),
        dao.observeConflicts(),
        connectivityObserver.online,
        dao.observeCursor(),
    ) { stocks, outbox, conflicts, online, cursor ->
        MainUiState(
            stockCount = stocks.size,
            lowCount = stocks.count { it.status == "LOW" || it.status == "OUT" },
            pendingCount = outbox.count { it.status == "PENDING" || it.status == "RUNNING" },
            conflictCount = conflicts.size,
            unallocatedCount = stocks.count { it.magasinId == null },
            online = online,
            lastSync = cursor?.updatedAt,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), MainUiState())

    val stocks = combine(_stockQuery, _stockStatus) { query, status -> query.trim() to status }
        .flatMapLatest { (query, status) -> dao.observeStockDisplayRows(query, status) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val outbox = dao.observeActiveOutbox()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val movements = dao.observeMovementDisplayRows()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val receivablePurchases = dao.observeReceivablePurchases()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val purchaseItems = dao.observePurchaseItemDisplayRows()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val bases = dao.observeBases().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val magasins = dao.observeMagasins().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val employees = dao.observeEmployees().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val ouvrages = dao.observeOuvrages().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val plannings = dao.observePlannings().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val transfers = dao.observeTransfers().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val transferItems = dao.observeTransferItems().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val conflicts = dao.observeConflicts()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val dashboardStats = dao.observeDashboardStats()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        viewModelScope.launch {
            val authenticated = sessionRepository.authenticated.first()
            _session.value = SessionUiState(checking = false, authenticated = authenticated)
            if (authenticated) synchronize()
        }
    }

    fun login(username: String, password: String) {
        if (username.isBlank() || password.isBlank() || _session.value.loading) return
        viewModelScope.launch {
            _session.value = _session.value.copy(loading = true, error = null)
            runCatching { sessionRepository.login(username, password) }
                .onSuccess { _session.value = SessionUiState(checking = false, authenticated = true) }
                .onFailure { _session.value = SessionUiState(checking = false, error = messageFor(it)) }
        }
    }

    fun synchronize() {
        if (_session.value.loading) return
        viewModelScope.launch {
            _session.value = _session.value.copy(loading = true, error = null)
            runCatching { sessionRepository.refreshBootstrap() }
                .onSuccess { _session.value = _session.value.copy(loading = false) }
                .onFailure {
                    val stillAuthenticated = sessionRepository.authenticated.first()
                    _session.value = SessionUiState(
                        checking = false,
                        authenticated = stillAuthenticated,
                        error = messageFor(it),
                    )
                }
        }
    }

    fun logout() {
        viewModelScope.launch {
            sessionRepository.logout()
            _session.value = SessionUiState(checking = false)
        }
    }

    fun clearError() { _session.value = _session.value.copy(error = null) }

    fun setStockQuery(value: String) { _stockQuery.value = value }

    fun setStockStatus(value: String) { _stockStatus.value = value }

    fun receivePurchase(purchaseId: String) {
        if (_purchaseReception.value.loadingPurchaseId != null) return
        viewModelScope.launch {
            _purchaseReception.value = PurchaseReceptionUiState(loadingPurchaseId = purchaseId)
            runCatching { sessionRepository.receivePurchase(purchaseId) }
                .onSuccess { _purchaseReception.value = PurchaseReceptionUiState(message = it) }
                .onFailure { _purchaseReception.value = PurchaseReceptionUiState(error = messageFor(it)) }
        }
    }

    fun clearPurchaseReceptionFeedback() {
        _purchaseReception.value = PurchaseReceptionUiState()
    }

    private fun executeOperation(call: suspend () -> String) {
        if (_operation.value.loading) return
        viewModelScope.launch {
            _operation.value = OperationUiState(loading = true)
            runCatching { call() }
                .onSuccess { _operation.value = OperationUiState(message = it) }
                .onFailure { _operation.value = OperationUiState(error = messageFor(it)) }
        }
    }

    fun createDelivery(request: DeliveryRequest) = executeOperation { sessionRepository.createDelivery(request) }
    fun createTransfer(request: CreateTransferRequest) = executeOperation { sessionRepository.createTransfer(request) }
    fun updateTransfer(id: String, request: UpdateTransferRequest) = executeOperation { sessionRepository.updateTransfer(id, request) }
    fun createInventory(fields: Map<String, String>) = executeOperation { sessionRepository.createInventory(fields) }
    fun adjustStock(stockId: String, fields: Map<String, String>) = executeOperation { sessionRepository.adjustStock(stockId, fields) }
    fun createFieldReturn(request: FieldReturnRequest) = executeOperation { sessionRepository.createFieldReturn(request) }
    fun clearOperationFeedback() { _operation.value = OperationUiState() }

    private fun messageFor(error: Throwable): String = when (error) {
        is retrofit2.HttpException -> serverMessage(error) ?: when (error.code()) {
            400 -> "Les données saisies sont invalides."
            401 -> "La session a expiré. Veuillez vous reconnecter."
            403 -> "Ce compte n’a pas accès à cette opération logistique."
            else -> "Le serveur a refusé la demande (${error.code()})."
        }
        is java.io.IOException -> "Connexion au serveur impossible. Les données locales restent disponibles."
        else -> error.message ?: "Une erreur inattendue est survenue."
    }

    private fun serverMessage(error: retrofit2.HttpException): String? = runCatching {
        val payload = error.response()?.errorBody()?.string().orEmpty()
        val json = org.json.JSONObject(payload)
        json.optString("error").ifBlank { json.optString("message") }.takeIf { it.isNotBlank() }
    }.getOrNull()
}
