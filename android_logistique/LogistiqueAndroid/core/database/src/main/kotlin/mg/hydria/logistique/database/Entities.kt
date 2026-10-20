package mg.hydria.logistique.database

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Fts4
import androidx.room.Index
import androidx.room.PrimaryKey

interface VersionedEntity {
    val revision: Long
    val deletedAt: String?
}

@Entity(tableName = "users")
data class UserEntity(@PrimaryKey val id: String, val displayName: String, val email: String?, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "capabilities", primaryKeys = ["userId", "code"], indices = [Index("userId")])
data class CapabilityEntity(val userId: String, val code: String, val allowed: Boolean, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "bases")
data class BaseEntity(@PrimaryKey val id: String, val name: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "magasins", indices = [Index("baseId")])
data class MagasinEntity(@PrimaryKey val id: String, val baseId: String, val name: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "article_types")
data class ArticleTypeEntity(@PrimaryKey val id: String, val name: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "units")
data class UnitEntity(@PrimaryKey val id: String, val label: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "articles", indices = [Index("code"), Index("typeId")])
data class ArticleEntity(
    @PrimaryKey val id: String,
    val code: String,
    val designation: String,
    val typeId: String?,
    val unit: String,
    val unitPriceAriary: Long?,
    val unitPrice: String? = null,
    val minimumLevel: String = "0.00",
    val nature: String = "",
    val description: String? = null,
    val photoUrl: String?,
    val active: Boolean,
    override val revision: Long,
    override val deletedAt: String? = null,
) : VersionedEntity

@Fts4
@Entity(tableName = "articles_fts")
data class ArticleFtsEntity(
    @PrimaryKey @ColumnInfo(name = "rowid") val rowId: Int,
    val code: String,
    val designation: String,
)

@Entity(tableName = "suppliers")
data class SupplierEntity(@PrimaryKey val id: String, val name: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "employees")
data class EmployeeEntity(@PrimaryKey val id: String, val displayName: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "accounts", indices = [Index("magasinId")])
data class AccountEntity(@PrimaryKey val id: String, val magasinId: String?, val code: String, val label: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "ouvrages")
data class OuvrageEntity(@PrimaryKey val id: String, val name: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "plannings", indices = [Index("ouvrageId"), Index("businessDate")])
data class PlanningEntity(@PrimaryKey val id: String, val ouvrageId: String, val employeeId: String?, val businessDate: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "stock_positions", indices = [Index("articleId"), Index("baseId"), Index("magasinId"), Index("status"), Index("updatedAt")])
data class StockPositionEntity(
    @PrimaryKey val id: String,
    val stockId: String?,
    val articleId: String,
    val baseId: String,
    val magasinId: String?,
    val currentQuantity: String,
    val reservedQuantity: String,
    val availableQuantity: String,
    val status: String,
    val estimated: Boolean,
    val estimateReason: String? = null,
    val inventoryDate: String?,
    val updatedAt: String,
    override val revision: Long,
    override val deletedAt: String? = null,
) : VersionedEntity

@Entity(tableName = "stock_movements", indices = [Index("articleId"), Index("baseId"), Index("magasinId"), Index("movementDate")])
data class StockMovementEntity(@PrimaryKey val id: String, val articleId: String, val baseId: String, val magasinId: String?, val movementDate: String, val movementType: String, val quantity: String, val reference: String?, val notes: String?, val syncStatus: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "inventories", indices = [Index("articleId"), Index("baseId"), Index("magasinId"), Index("inventoryDate")])
data class InventoryEntity(@PrimaryKey val id: String, val articleId: String, val baseId: String, val magasinId: String?, val physicalQuantity: String, val knownTheoreticalQuantity: String, val knownStockRevision: Long, val inventoryDate: String, val notes: String?, val reconciled: Boolean, val syncStatus: String, override val revision: Long = 0, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "purchases", indices = [Index("magasinId"), Index("status"), Index("purchaseDate")])
data class PurchaseEntity(@PrimaryKey val id: String, val number: String?, val purchaseDate: String, val supplierId: String?, val supplierName: String?, val magasinId: String, val status: String, val totalAriary: Long, val allowedActionsJson: String, val syncStatus: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "purchase_items", indices = [Index("purchaseId"), Index("articleId")])
data class PurchaseItemEntity(@PrimaryKey val id: String, val purchaseId: String, val articleId: String, val orderedQuantity: String, val receivedQuantity: String, val unitPriceAriary: Long, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "transfers", indices = [Index("originMagasinId"), Index("destinationMagasinId"), Index("status"), Index("transferDate")])
data class TransferEntity(@PrimaryKey val id: String, val number: String?, val transferDate: String, val originMagasinId: String, val destinationMagasinId: String, val status: String, val allowedActionsJson: String, val syncStatus: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "transfer_items", indices = [Index("transferId"), Index("articleId")])
data class TransferItemEntity(@PrimaryKey val id: String, val transferId: String, val articleId: String, val sentQuantity: String, val receivedQuantity: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "deliveries", indices = [Index("status"), Index("planningId"), Index("magasinId")])
data class DeliveryEntity(@PrimaryKey val id: String, val planningId: String, val ouvrageId: String, val magasinId: String?, val status: String, val useDate: String?, val voucherNumber: String?, val officialPdfUrl: String?, val syncStatus: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "delivery_items", indices = [Index("deliveryId"), Index("articleId")])
data class DeliveryItemEntity(@PrimaryKey val id: String, val deliveryId: String, val articleId: String, val quantity: String, override val revision: Long, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "field_returns", indices = [Index("articleId"), Index("baseId"), Index("magasinId"), Index("operationDate")])
data class FieldReturnEntity(@PrimaryKey val id: String, val articleId: String, val baseId: String, val magasinId: String?, val operationDate: String, val quantity: String, val reference: String?, val notes: String?, val syncStatus: String, override val revision: Long = 0, override val deletedAt: String? = null) : VersionedEntity

@Entity(tableName = "local_photos", indices = [Index("ownerType", "ownerId"), Index("syncStatus")])
data class LocalPhotoEntity(@PrimaryKey val id: String, val ownerType: String, val ownerId: String, val localUri: String, val remoteUrl: String?, val syncStatus: String, val createdAt: String)

@Entity(tableName = "outbox_operations", indices = [Index("status", "createdAt"), Index(value = ["clientOperationId"], unique = true)])
data class OutboxOperationEntity(@PrimaryKey val id: String, val clientOperationId: String, val operationType: String, val localEntityId: String, val userId: String, val deviceId: String, val businessDate: String, val createdAt: String, val knownServerRevision: Long?, val payloadJson: String, val dependencyIdsJson: String, val attemptCount: Int, val status: String, val lastErrorCode: String?, val lastErrorMessage: String?)

@Entity(tableName = "sync_cursors")
data class SyncCursorEntity(@PrimaryKey val stream: String, val cursor: String, val updatedAt: String)

@Entity(tableName = "dashboard_stats")
data class DashboardStatEntity(@PrimaryKey val code: String, val count: Int, val asOfDate: String)

@Entity(tableName = "sync_conflicts", indices = [Index("operationId"), Index("resolvedAt")])
data class SyncConflictEntity(@PrimaryKey val id: String, val operationId: String, val code: String, val message: String, val serverStateJson: String?, val localPayloadJson: String, val createdAt: String, val resolvedAt: String?)
