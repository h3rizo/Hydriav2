package mg.hydria.logistique.database

import androidx.room.Dao
import androidx.room.ColumnInfo
import androidx.room.Embedded
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow

data class StockDisplayRow(
    @Embedded val stock: StockPositionEntity,
    @ColumnInfo(name = "displayArticleCode") val articleCode: String,
    @ColumnInfo(name = "displayArticleName") val articleName: String,
    @ColumnInfo(name = "displayUnit") val unit: String,
    @ColumnInfo(name = "displayBaseName") val baseName: String,
    @ColumnInfo(name = "displayMagasinName") val magasinName: String?,
)

data class MovementDisplayRow(
    @Embedded val movement: StockMovementEntity,
    @ColumnInfo(name = "displayArticleCode") val articleCode: String,
    @ColumnInfo(name = "displayArticleName") val articleName: String,
    @ColumnInfo(name = "displayBaseName") val baseName: String,
    @ColumnInfo(name = "displayMagasinName") val magasinName: String?,
)

data class PurchaseDisplayRow(
    @Embedded val purchase: PurchaseEntity,
    @ColumnInfo(name = "displayMagasinName") val magasinName: String,
    @ColumnInfo(name = "displayBaseName") val baseName: String,
    @ColumnInfo(name = "displayItemCount") val itemCount: Int,
)

data class PurchaseItemDisplayRow(
    @Embedded val item: PurchaseItemEntity,
    @ColumnInfo(name = "displayArticleCode") val articleCode: String,
    @ColumnInfo(name = "displayArticleName") val articleName: String,
    @ColumnInfo(name = "displayUnit") val unit: String,
)

@Dao
interface LogistiqueDao {
    @Query("SELECT * FROM stock_positions WHERE deletedAt IS NULL ORDER BY updatedAt DESC")
    fun observeStockPositions(): Flow<List<StockPositionEntity>>

    @Query("""
        SELECT sp.*, a.code AS displayArticleCode, a.designation AS displayArticleName,
               a.unit AS displayUnit, b.name AS displayBaseName, m.name AS displayMagasinName
        FROM stock_positions sp
        JOIN articles a ON a.id = sp.articleId
        JOIN bases b ON b.id = sp.baseId
        LEFT JOIN magasins m ON m.id = sp.magasinId
        WHERE sp.deletedAt IS NULL AND a.deletedAt IS NULL
          AND (:query = '' OR a.code LIKE '%' || :query || '%' OR a.designation LIKE '%' || :query || '%')
          AND (:status = '' OR sp.status = :status)
        ORDER BY a.designation, b.name, m.name
    """)
    fun observeStockDisplayRows(query: String, status: String): Flow<List<StockDisplayRow>>

    @Query("""
        SELECT sm.*, a.code AS displayArticleCode, a.designation AS displayArticleName,
               b.name AS displayBaseName, m.name AS displayMagasinName
        FROM stock_movements sm
        JOIN articles a ON a.id = sm.articleId
        JOIN bases b ON b.id = sm.baseId
        LEFT JOIN magasins m ON m.id = sm.magasinId
        WHERE sm.deletedAt IS NULL
        ORDER BY sm.movementDate DESC
    """)
    fun observeMovementDisplayRows(): Flow<List<MovementDisplayRow>>

    @Query("""
        SELECT p.*, m.name AS displayMagasinName, b.name AS displayBaseName,
               COUNT(pi.id) AS displayItemCount
        FROM purchases p
        JOIN magasins m ON m.id = p.magasinId
        JOIN bases b ON b.id = m.baseId
        LEFT JOIN purchase_items pi ON pi.purchaseId = p.id AND pi.deletedAt IS NULL
        WHERE p.deletedAt IS NULL AND p.status NOT IN ('recu', 'annule')
          AND p.allowedActionsJson LIKE '%receive%'
        GROUP BY p.id
        ORDER BY p.purchaseDate DESC
    """)
    fun observeReceivablePurchases(): Flow<List<PurchaseDisplayRow>>

    @Query("""
        SELECT pi.*, a.code AS displayArticleCode, a.designation AS displayArticleName,
               a.unit AS displayUnit
        FROM purchase_items pi
        JOIN articles a ON a.id = pi.articleId
        WHERE pi.deletedAt IS NULL AND a.deletedAt IS NULL
        ORDER BY pi.purchaseId, a.designation
    """)
    fun observePurchaseItemDisplayRows(): Flow<List<PurchaseItemDisplayRow>>

    @Query("SELECT * FROM articles WHERE deletedAt IS NULL AND (code LIKE '%' || :query || '%' OR designation LIKE '%' || :query || '%') ORDER BY designation LIMIT :limit")
    fun observeArticles(query: String, limit: Int = 100): Flow<List<ArticleEntity>>

    @Query("SELECT * FROM bases WHERE deletedAt IS NULL ORDER BY name") fun observeBases(): Flow<List<BaseEntity>>
    @Query("SELECT * FROM magasins WHERE deletedAt IS NULL ORDER BY name") fun observeMagasins(): Flow<List<MagasinEntity>>
    @Query("SELECT * FROM employees WHERE deletedAt IS NULL ORDER BY displayName") fun observeEmployees(): Flow<List<EmployeeEntity>>
    @Query("SELECT * FROM ouvrages WHERE deletedAt IS NULL ORDER BY name") fun observeOuvrages(): Flow<List<OuvrageEntity>>
    @Query("SELECT * FROM plannings WHERE deletedAt IS NULL ORDER BY businessDate DESC") fun observePlannings(): Flow<List<PlanningEntity>>
    @Query("SELECT * FROM transfers WHERE deletedAt IS NULL AND status != 'annule' ORDER BY transferDate DESC") fun observeTransfers(): Flow<List<TransferEntity>>
    @Query("SELECT * FROM transfer_items WHERE deletedAt IS NULL") fun observeTransferItems(): Flow<List<TransferItemEntity>>

    @Query("SELECT * FROM outbox_operations WHERE status IN ('PENDING', 'RUNNING', 'CONFLICT', 'REJECTED') ORDER BY createdAt")
    fun observeActiveOutbox(): Flow<List<OutboxOperationEntity>>

    @Query("SELECT * FROM sync_conflicts WHERE resolvedAt IS NULL ORDER BY createdAt DESC")
    fun observeConflicts(): Flow<List<SyncConflictEntity>>

    @Query("SELECT * FROM users LIMIT 1")
    fun observeCurrentUser(): Flow<UserEntity?>

    @Query("SELECT * FROM capabilities WHERE userId = :userId AND allowed = 1 AND deletedAt IS NULL")
    fun observeCapabilities(userId: String): Flow<List<CapabilityEntity>>

    @Query("SELECT * FROM sync_cursors WHERE stream = 'main' LIMIT 1")
    fun observeCursor(): Flow<SyncCursorEntity?>

    @Query("SELECT * FROM dashboard_stats")
    fun observeDashboardStats(): Flow<List<DashboardStatEntity>>

    @Query("SELECT * FROM outbox_operations WHERE status = 'PENDING' ORDER BY createdAt LIMIT :limit")
    suspend fun pendingOperations(limit: Int = 50): List<OutboxOperationEntity>

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun enqueue(operation: OutboxOperationEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertStockPositions(items: List<StockPositionEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertStockMovements(items: List<StockMovementEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertPurchases(items: List<PurchaseEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertPurchaseItems(items: List<PurchaseItemEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertEmployees(items: List<EmployeeEntity>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertOuvrages(items: List<OuvrageEntity>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertPlannings(items: List<PlanningEntity>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertTransfers(items: List<TransferEntity>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertTransferItems(items: List<TransferItemEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertArticles(items: List<ArticleEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertUser(item: UserEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertCapabilities(items: List<CapabilityEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertBases(items: List<BaseEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertMagasins(items: List<MagasinEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertArticleTypes(items: List<ArticleTypeEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertDashboardStats(items: List<DashboardStatEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertConflict(conflict: SyncConflictEntity)

    @Query("UPDATE outbox_operations SET status = :status, attemptCount = attemptCount + :attemptIncrement, lastErrorCode = :code, lastErrorMessage = :message WHERE id = :id")
    suspend fun updateOutboxStatus(id: String, status: String, attemptIncrement: Int, code: String? = null, message: String? = null)

    @Query("SELECT * FROM sync_cursors WHERE stream = :stream LIMIT 1")
    suspend fun cursor(stream: String = "main"): SyncCursorEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertCursor(cursor: SyncCursorEntity)

    @Transaction
    suspend fun applyCanonicalStock(items: List<StockPositionEntity>, cursor: SyncCursorEntity) {
        upsertStockPositions(items)
        upsertCursor(cursor)
    }

    @Transaction
    suspend fun applyBootstrap(
        user: UserEntity,
        capabilities: List<CapabilityEntity>,
        bases: List<BaseEntity>,
        magasins: List<MagasinEntity>,
        articleTypes: List<ArticleTypeEntity>,
        articles: List<ArticleEntity>,
        stocks: List<StockPositionEntity>,
        movements: List<StockMovementEntity>,
        purchases: List<PurchaseEntity>,
        purchaseItems: List<PurchaseItemEntity>,
        employees: List<EmployeeEntity>,
        ouvrages: List<OuvrageEntity>,
        plannings: List<PlanningEntity>,
        transfers: List<TransferEntity>,
        transferItems: List<TransferItemEntity>,
        dashboardStats: List<DashboardStatEntity>,
        cursor: SyncCursorEntity,
    ) {
        upsertUser(user)
        upsertCapabilities(capabilities)
        upsertBases(bases)
        upsertMagasins(magasins)
        upsertArticleTypes(articleTypes)
        upsertArticles(articles)
        upsertStockPositions(stocks)
        upsertStockMovements(movements)
        upsertPurchases(purchases)
        upsertPurchaseItems(purchaseItems)
        upsertEmployees(employees)
        upsertOuvrages(ouvrages)
        upsertPlannings(plannings)
        upsertTransfers(transfers)
        upsertTransferItems(transferItems)
        upsertDashboardStats(dashboardStats)
        upsertCursor(cursor)
    }
}
