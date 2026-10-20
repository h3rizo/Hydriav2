package mg.hydria.logistique.feature.main

import kotlinx.coroutines.flow.first
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import mg.hydria.logistique.database.ArticleEntity
import mg.hydria.logistique.database.ArticleTypeEntity
import mg.hydria.logistique.database.BaseEntity
import mg.hydria.logistique.database.CapabilityEntity
import mg.hydria.logistique.database.DashboardStatEntity
import mg.hydria.logistique.database.LogistiqueDao
import mg.hydria.logistique.database.MagasinEntity
import mg.hydria.logistique.database.EmployeeEntity
import mg.hydria.logistique.database.OuvrageEntity
import mg.hydria.logistique.database.PlanningEntity
import mg.hydria.logistique.database.PurchaseEntity
import mg.hydria.logistique.database.PurchaseItemEntity
import mg.hydria.logistique.database.TransferEntity
import mg.hydria.logistique.database.TransferItemEntity
import mg.hydria.logistique.database.StockPositionEntity
import mg.hydria.logistique.database.StockMovementEntity
import mg.hydria.logistique.database.SyncCursorEntity
import mg.hydria.logistique.database.UserEntity
import mg.hydria.logistique.network.BootstrapResponse
import mg.hydria.logistique.network.CreateTransferRequest
import mg.hydria.logistique.network.DeliveryRequest
import mg.hydria.logistique.network.FieldReturnRequest
import mg.hydria.logistique.network.LoginRequest
import mg.hydria.logistique.network.MobileApi
import mg.hydria.logistique.network.RefreshRequest
import mg.hydria.logistique.network.UpdateTransferRequest
import mg.hydria.logistique.network.SecureTokenStore
import retrofit2.HttpException
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SessionRepository @Inject constructor(
    private val api: MobileApi,
    private val tokenStore: SecureTokenStore,
    private val dao: LogistiqueDao,
    private val json: Json,
) {
    val authenticated = tokenStore.authenticated

    suspend fun login(username: String, password: String) {
        val response = api.login(
            LoginRequest(
                username = username.trim(),
                password = password,
                deviceId = tokenStore.deviceId(),
                deviceLabel = tokenStore.deviceLabel(),
            )
        )
        tokenStore.save(response.accessToken, response.refreshToken)
        runCatching { refreshBootstrap() }.onFailure {
            tokenStore.clear()
            throw it
        }
    }

    suspend fun refreshBootstrap() {
        val response = try {
            api.bootstrap()
        } catch (error: HttpException) {
            if (error.code() != 401) throw error
            refreshAccessToken()
            api.bootstrap()
        }
        persist(response)
    }

    suspend fun logout() = tokenStore.clear()

    suspend fun receivePurchase(purchaseId: String): String {
        val response = try {
            api.receivePurchase(purchaseId)
        } catch (error: HttpException) {
            if (error.code() != 401) throw error
            refreshAccessToken()
            api.receivePurchase(purchaseId)
        }
        refreshBootstrap()
        return response.message
    }

    suspend fun createDelivery(request: DeliveryRequest) = runOperation { api.createDelivery(request) }
    suspend fun createTransfer(request: CreateTransferRequest) = runOperation { api.createTransfer(request) }
    suspend fun updateTransfer(transferId: String, request: UpdateTransferRequest) = runOperation { api.updateTransfer(transferId, request) }
    suspend fun createInventory(fields: Map<String, String>) = runOperation { api.createInventory(fields) }
    suspend fun adjustStock(stockId: String, fields: Map<String, String>) = runOperation { api.adjustStock(stockId, fields) }
    suspend fun createFieldReturn(request: FieldReturnRequest) = runOperation { api.createFieldReturn(request) }

    private suspend fun runOperation(call: suspend () -> mg.hydria.logistique.network.OperationResponse): String {
        val response = try {
            call()
        } catch (error: HttpException) {
            if (error.code() != 401) throw error
            refreshAccessToken()
            call()
        }
        refreshBootstrap()
        return response.message ?: "Opération enregistrée avec succès."
    }

    private suspend fun refreshAccessToken() {
        val refresh = tokenStore.refreshToken.first()
            ?: error("Session expirée. Veuillez vous reconnecter.")
        try {
            val response = api.refresh(RefreshRequest(refresh))
            tokenStore.updateAccess(response.accessToken, response.refreshToken)
        } catch (error: Exception) {
            tokenStore.clear()
            throw error
        }
    }

    private suspend fun persist(response: BootstrapResponse) {
        val data = response.payload
        val userRevision = response.cursor.toLongOrNull() ?: 0L
        dao.applyBootstrap(
            user = UserEntity(data.user.id, data.user.displayName, data.user.email, userRevision),
            capabilities = data.capabilities.map {
                CapabilityEntity(data.user.id, it.code, it.allowed, userRevision)
            },
            bases = data.bases.map { BaseEntity(it.id, it.name, it.revision, it.deletedAt) },
            magasins = data.magasins.map { MagasinEntity(it.id, it.baseId, it.name, it.revision, it.deletedAt) },
            articleTypes = data.articleTypes.map { ArticleTypeEntity(it.id, it.name, it.revision, it.deletedAt) },
            articles = data.articles.map {
                ArticleEntity(
                    id = it.id,
                    code = it.code,
                    designation = it.designation,
                    typeId = it.typeId,
                    unit = it.unit,
                    unitPriceAriary = null,
                    unitPrice = it.unitPrice,
                    minimumLevel = it.minimumLevel,
                    nature = it.nature,
                    description = it.description,
                    photoUrl = it.photoUrl,
                    active = it.active,
                    revision = it.revision,
                    deletedAt = it.deletedAt,
                )
            },
            stocks = data.stockPositions.map {
                StockPositionEntity(
                    id = it.id,
                    stockId = it.stockId,
                    articleId = it.articleId,
                    baseId = it.baseId,
                    magasinId = it.magasinId,
                    currentQuantity = it.current,
                    reservedQuantity = it.reserved,
                    availableQuantity = it.available,
                    status = it.status,
                    estimated = it.estimated,
                    estimateReason = it.estimateReason,
                    inventoryDate = it.inventoryDate,
                    updatedAt = it.updatedAt,
                    revision = it.revision,
                    deletedAt = it.deletedAt,
                )
            },
            movements = data.stockMovements.map {
                StockMovementEntity(
                    id = it.id,
                    articleId = it.articleId,
                    baseId = it.baseId,
                    magasinId = it.magasinId,
                    movementDate = it.movementDate,
                    movementType = it.movementType,
                    quantity = it.quantity,
                    reference = it.reference,
                    notes = it.notes,
                    syncStatus = it.syncStatus,
                    revision = it.revision,
                    deletedAt = it.deletedAt,
                )
            },
            purchases = data.purchases.map {
                PurchaseEntity(
                    id = it.id,
                    number = it.number,
                    purchaseDate = it.purchaseDate,
                    supplierId = null,
                    supplierName = it.supplierName,
                    magasinId = it.magasinId.orEmpty(),
                    status = it.status,
                    totalAriary = it.totalAriary,
                    allowedActionsJson = json.encodeToString(it.allowedActions),
                    syncStatus = "SYNCED",
                    revision = it.revision,
                    deletedAt = it.deletedAt,
                )
            },
            purchaseItems = data.purchases.flatMap { purchase ->
                purchase.items.map {
                    PurchaseItemEntity(
                        id = it.id,
                        purchaseId = purchase.id,
                        articleId = it.articleId,
                        orderedQuantity = it.orderedQuantity,
                        receivedQuantity = it.receivedQuantity,
                        unitPriceAriary = it.unitPriceAriary,
                        revision = it.revision,
                        deletedAt = it.deletedAt,
                    )
                }
            },
            employees = data.employees.map { EmployeeEntity(it.id, it.displayName, it.revision, it.deletedAt) },
            ouvrages = data.ouvrages.map { OuvrageEntity(it.id, it.name, it.revision, it.deletedAt) },
            plannings = data.plannings.map { PlanningEntity(it.id, it.ouvrageId, it.employeeId, it.businessDate, it.revision, it.deletedAt) },
            transfers = data.transfers.map {
                TransferEntity(
                    id = it.id,
                    number = it.number,
                    transferDate = it.transferDate,
                    originMagasinId = it.originMagasinId,
                    destinationMagasinId = it.destinationMagasinId,
                    status = it.status,
                    allowedActionsJson = json.encodeToString(it.allowedActions),
                    syncStatus = "SYNCED",
                    revision = it.revision,
                    deletedAt = it.deletedAt,
                )
            },
            transferItems = data.transfers.flatMap { transfer ->
                transfer.items.map {
                    TransferItemEntity(it.id, transfer.id, it.articleId, it.sentQuantity, it.receivedQuantity, it.revision, it.deletedAt)
                }
            },
            dashboardStats = data.activityDueStats?.let {
                listOf(
                    DashboardStatEntity("repair_overdue_works", it.repairOverdueWorks, it.asOfDate),
                    DashboardStatEntity("maintenance_only_works", it.maintenanceOnlyWorks, it.asOfDate),
                )
            }.orEmpty(),
            cursor = SyncCursorEntity("main", response.cursor, response.serverTime.ifBlank { Instant.now().toString() }),
        )
    }
}
