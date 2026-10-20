package mg.hydria.logistique.database

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(
    entities = [
        UserEntity::class, CapabilityEntity::class, BaseEntity::class, MagasinEntity::class,
        ArticleTypeEntity::class, UnitEntity::class, ArticleEntity::class, ArticleFtsEntity::class,
        SupplierEntity::class, EmployeeEntity::class, AccountEntity::class, OuvrageEntity::class,
        PlanningEntity::class, StockPositionEntity::class, StockMovementEntity::class,
        InventoryEntity::class, PurchaseEntity::class, PurchaseItemEntity::class,
        TransferEntity::class, TransferItemEntity::class, DeliveryEntity::class,
        DeliveryItemEntity::class, FieldReturnEntity::class, LocalPhotoEntity::class,
        OutboxOperationEntity::class, SyncCursorEntity::class, SyncConflictEntity::class,
        DashboardStatEntity::class,
    ],
    version = 5,
    exportSchema = true,
)
abstract class LogistiqueDatabase : RoomDatabase() {
    abstract fun dao(): LogistiqueDao
}
