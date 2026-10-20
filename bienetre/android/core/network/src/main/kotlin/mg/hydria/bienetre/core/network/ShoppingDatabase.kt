package mg.hydria.bienetre.core.network

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase

@Entity(tableName = "shopping_cache")
data class ShoppingCacheEntity(
    @PrimaryKey val scope: String,
    val payload: String,
    val updatedAt: Long,
)

@Entity(tableName = "pending_shopping_checks", primaryKeys = ["scope", "itemId"])
data class PendingShoppingCheckEntity(
    val scope: String,
    val itemId: Long,
    val checked: Boolean,
    val updatedAt: Long,
)

@Dao
interface ShoppingDao {
    @Query("SELECT * FROM shopping_cache WHERE scope = :scope")
    suspend fun cache(scope: String): ShoppingCacheEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun saveCache(cache: ShoppingCacheEntity)

    @Query("SELECT * FROM pending_shopping_checks WHERE scope = :scope ORDER BY updatedAt")
    suspend fun pendingChecks(scope: String): List<PendingShoppingCheckEntity>

    @Query("SELECT * FROM pending_shopping_checks WHERE scope = :scope AND itemId = :itemId")
    suspend fun pendingCheck(scope: String, itemId: Long): PendingShoppingCheckEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun savePendingCheck(check: PendingShoppingCheckEntity)

    @Query("DELETE FROM pending_shopping_checks WHERE scope = :scope AND itemId = :itemId AND checked = :checked")
    suspend fun deletePendingCheck(scope: String, itemId: Long, checked: Boolean): Int
}

@Database(
    entities = [ShoppingCacheEntity::class, PendingShoppingCheckEntity::class],
    version = 1,
    exportSchema = false,
)
abstract class BienetreDatabase : RoomDatabase() {
    abstract fun shoppingDao(): ShoppingDao
}
