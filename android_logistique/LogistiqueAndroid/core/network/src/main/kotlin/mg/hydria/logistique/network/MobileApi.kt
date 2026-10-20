package mg.hydria.logistique.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import mg.hydria.logistique.model.OutboxEnvelope
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query
import retrofit2.http.FieldMap
import retrofit2.http.FormUrlEncoded

@Serializable
data class LoginRequest(
    val username: String,
    val password: String,
    @SerialName("device_id") val deviceId: String,
    @SerialName("device_label") val deviceLabel: String,
)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("expires_in") val expiresInSeconds: Long,
    val user: UserDto? = null,
)

@Serializable data class RefreshRequest(@SerialName("refresh_token") val refreshToken: String)

@Serializable
data class UserDto(
    val id: String,
    val username: String,
    @SerialName("display_name") val displayName: String,
    val email: String? = null,
    @SerialName("employee_id") val employeeId: String? = null,
    @SerialName("base_id") val baseId: String? = null,
    @SerialName("inventory_scope") val inventoryScope: String,
)

@Serializable data class CapabilityDto(val code: String, val allowed: Boolean)
@Serializable data class BaseDto(val id: String, val name: String, val revision: Long, @SerialName("deleted_at") val deletedAt: String? = null)
@Serializable data class MagasinDto(val id: String, @SerialName("base_id") val baseId: String, val name: String, val revision: Long, @SerialName("deleted_at") val deletedAt: String? = null)
@Serializable data class ArticleTypeDto(val id: String, val name: String, val revision: Long, @SerialName("deleted_at") val deletedAt: String? = null)

@Serializable
data class ArticleDto(
    val id: String,
    val code: String,
    val designation: String,
    val description: String? = null,
    @SerialName("type_id") val typeId: String? = null,
    val unit: String,
    @SerialName("unit_price") val unitPrice: String? = null,
    @SerialName("minimum_level") val minimumLevel: String,
    val nature: String,
    @SerialName("photo_url") val photoUrl: String? = null,
    val active: Boolean,
    val revision: Long,
    @SerialName("deleted_at") val deletedAt: String? = null,
)

@Serializable
data class StockPositionDto(
    val id: String,
    @SerialName("stock_id") val stockId: String? = null,
    @SerialName("article_id") val articleId: String,
    @SerialName("base_id") val baseId: String,
    @SerialName("magasin_id") val magasinId: String? = null,
    val current: String,
    val reserved: String,
    val available: String,
    val status: String,
    @SerialName("inventory_date") val inventoryDate: String? = null,
    @SerialName("updated_at") val updatedAt: String,
    val revision: Long,
    val estimated: Boolean,
    @SerialName("estimate_reason") val estimateReason: String? = null,
    @SerialName("deleted_at") val deletedAt: String? = null,
)

@Serializable data class EmployeeDto(val id: String, @SerialName("display_name") val displayName: String, val revision: Long, @SerialName("deleted_at") val deletedAt: String? = null)
@Serializable data class OuvrageDto(val id: String, val name: String, val revision: Long, @SerialName("deleted_at") val deletedAt: String? = null)
@Serializable data class PlanningDto(val id: String, @SerialName("ouvrage_id") val ouvrageId: String, @SerialName("employee_id") val employeeId: String? = null, @SerialName("business_date") val businessDate: String, val revision: Long, @SerialName("deleted_at") val deletedAt: String? = null)
@Serializable data class TransferItemDto(val id: String, @SerialName("article_id") val articleId: String, @SerialName("sent_quantity") val sentQuantity: String, @SerialName("received_quantity") val receivedQuantity: String, val revision: Long, @SerialName("deleted_at") val deletedAt: String? = null)
@Serializable data class TransferDto(val id: String, val number: String, @SerialName("transfer_date") val transferDate: String, @SerialName("origin_magasin_id") val originMagasinId: String, @SerialName("destination_magasin_id") val destinationMagasinId: String, val status: String, @SerialName("allowed_actions") val allowedActions: List<String>, val revision: Long, @SerialName("deleted_at") val deletedAt: String? = null, val items: List<TransferItemDto> = emptyList())

@Serializable
data class StockMovementDto(
    val id: String,
    @SerialName("article_id") val articleId: String,
    @SerialName("base_id") val baseId: String,
    @SerialName("magasin_id") val magasinId: String? = null,
    @SerialName("movement_date") val movementDate: String,
    @SerialName("movement_type") val movementType: String,
    val quantity: String,
    val reference: String? = null,
    val notes: String? = null,
    @SerialName("sync_status") val syncStatus: String,
    val revision: Long,
    @SerialName("deleted_at") val deletedAt: String? = null,
)

@Serializable
data class PurchaseItemDto(
    val id: String,
    @SerialName("article_id") val articleId: String,
    @SerialName("ordered_quantity") val orderedQuantity: String,
    @SerialName("received_quantity") val receivedQuantity: String,
    @SerialName("unit_price_ariary") val unitPriceAriary: Long,
    val revision: Long,
    @SerialName("deleted_at") val deletedAt: String? = null,
)

@Serializable
data class PurchaseDto(
    val id: String,
    val number: String,
    @SerialName("purchase_date") val purchaseDate: String,
    @SerialName("supplier_name") val supplierName: String? = null,
    @SerialName("magasin_id") val magasinId: String? = null,
    val status: String,
    @SerialName("total_ariary") val totalAriary: Long,
    @SerialName("allowed_actions") val allowedActions: List<String>,
    val revision: Long,
    @SerialName("deleted_at") val deletedAt: String? = null,
    val items: List<PurchaseItemDto> = emptyList(),
)

@Serializable
data class ReceivePurchaseResponse(
    val success: Boolean,
    @SerialName("already_received") val alreadyReceived: Boolean = false,
    @SerialName("purchase_id") val purchaseId: String,
    val status: String,
    val message: String,
    @SerialName("transaction_id") val transactionId: Long? = null,
)

@Serializable data class OperationResponse(val success: Boolean, val message: String? = null, val id: String? = null, @SerialName("transfert_id") val transferId: String? = null)
@Serializable data class DeliveryRequest(@SerialName("planning_id") val planningId: String, @SerialName("designation_id") val designationId: String, val quantite: String, val magasin: String, @SerialName("numero_bon") val numeroBon: String = "", val statut: String, @SerialName("date_utilisation") val dateUtilisation: String? = null)
@Serializable data class TransferLineRequest(@SerialName("designation_id") val designationId: String, val quantity: String)
@Serializable data class CreateTransferRequest(@SerialName("magasin_origine_id") val originMagasinId: String, @SerialName("magasin_destination_id") val destinationMagasinId: String, @SerialName("expected_arrival_date") val expectedArrivalDate: String? = null, val notes: String = "", val items: List<TransferLineRequest>)
@Serializable data class UpdateTransferRequest(val action: String, val quantities: Map<String, String> = emptyMap())
@Serializable data class FieldReturnRequest(@SerialName("designation_id") val designationId: String, @SerialName("base_id") val baseId: String, @SerialName("magasin_id") val magasinId: String? = null, val quantite: String, @SerialName("date_operation") val dateOperation: String, val reference: String = "", val notes: String = "")

@Serializable
data class ActivityDueStatsDto(
    @SerialName("repair_overdue_works") val repairOverdueWorks: Int,
    @SerialName("maintenance_only_works") val maintenanceOnlyWorks: Int,
    @SerialName("as_of_date") val asOfDate: String,
)

@Serializable
data class BootstrapResponse(val cursor: String, @SerialName("server_time") val serverTime: String, val payload: BootstrapPayload)

@Serializable
data class BootstrapPayload(
    val user: UserDto,
    val capabilities: List<CapabilityDto>,
    val bases: List<BaseDto>,
    val magasins: List<MagasinDto>,
    @SerialName("article_types") val articleTypes: List<ArticleTypeDto>,
    val articles: List<ArticleDto>,
    @SerialName("stock_positions") val stockPositions: List<StockPositionDto>,
    @SerialName("stock_movements") val stockMovements: List<StockMovementDto> = emptyList(),
    val purchases: List<PurchaseDto> = emptyList(),
    val employees: List<EmployeeDto> = emptyList(),
    val ouvrages: List<OuvrageDto> = emptyList(),
    val plannings: List<PlanningDto> = emptyList(),
    val transfers: List<TransferDto> = emptyList(),
    @SerialName("activity_due_stats") val activityDueStats: ActivityDueStatsDto? = null,
)

@Serializable
data class ChangesResponse(
    val cursor: String,
    @SerialName("has_more") val hasMore: Boolean,
    @SerialName("full_refresh_required") val fullRefreshRequired: Boolean = false,
)

@Serializable
data class OperationBatchRequest(val operations: List<OutboxEnvelope>)

@Serializable
data class OperationResult(
    val clientOperationId: String,
    val accepted: Boolean,
    val canonicalEntityId: String? = null,
    val canonicalRevision: Long? = null,
    val errorCode: String? = null,
    val errorMessage: String? = null,
    val conflict: Boolean = false,
    val serverStateJson: String? = null,
)

@Serializable
data class OperationBatchResponse(val results: List<OperationResult>, val cursor: String?)

interface MobileApi {
    @POST("api/mobile/v1/auth/login")
    suspend fun login(@Body request: LoginRequest): TokenResponse

    @POST("api/mobile/v1/auth/refresh")
    suspend fun refresh(@Body request: RefreshRequest): TokenResponse

    @GET("api/mobile/v1/bootstrap")
    suspend fun bootstrap(): BootstrapResponse

    @GET("api/mobile/v1/changes")
    suspend fun changes(@Query("cursor") cursor: String?): ChangesResponse

    @POST("api/mobile/v1/operations:batch")
    suspend fun submitOperations(@Body request: OperationBatchRequest): OperationBatchResponse

    @POST("api/mobile/v1/purchases/{purchaseId}/receive")
    suspend fun receivePurchase(@retrofit2.http.Path("purchaseId") purchaseId: String): ReceivePurchaseResponse

    @POST("api/mobile/v1/deliveries") suspend fun createDelivery(@Body request: DeliveryRequest): OperationResponse
    @POST("api/mobile/v1/transfers") suspend fun createTransfer(@Body request: CreateTransferRequest): OperationResponse
    @POST("api/mobile/v1/transfers/{transferId}/status") suspend fun updateTransfer(@retrofit2.http.Path("transferId") transferId: String, @Body request: UpdateTransferRequest): OperationResponse
    @FormUrlEncoded @POST("api/mobile/v1/inventories") suspend fun createInventory(@FieldMap fields: Map<String, String>): OperationResponse
    @FormUrlEncoded @POST("api/mobile/v1/stocks/{stockId}/adjust") suspend fun adjustStock(@retrofit2.http.Path("stockId") stockId: String, @FieldMap fields: Map<String, String>): OperationResponse
    @POST("api/mobile/v1/field-returns") suspend fun createFieldReturn(@Body request: FieldReturnRequest): OperationResponse
}
