package mg.hydria.bienetre.core.model

data class ShoppingList(
    val id: Long,
    val startDate: String,
    val endDate: String,
    val items: List<ShoppingItem>,
)

data class ShoppingItem(
    val id: Long,
    val name: String,
    val icon: String,
    val type: String,
    val quantity: Double,
    val unit: String,
    val checked: Boolean,
    val purchaseDate: String?,
    val earliestMealDate: String?,
    val latestMealDate: String?,
    val vendorId: Long?,
    val vendorName: String?,
    val vendorCity: String?,
    val latestPrice: Double?,
    val latestPriceUnit: String?,
    val pendingSync: Boolean = false,
) {
    val estimatedTotal: Double
        get() {
            val price = latestPrice ?: return 0.0
            return when (latestPriceUnit ?: "total") {
                "total" -> price
                "100g" -> when (unit.lowercase()) { "g" -> price * quantity / 100; "kg" -> price * quantity * 10; else -> 0.0 }
                "kg" -> when (unit.lowercase()) { "g" -> price * quantity / 1000; "kg" -> price * quantity; else -> 0.0 }
                "piece" -> if (unit.lowercase() in setOf("piece", "pieces", "unite", "unites", "u")) price * quantity else 0.0
                else -> if (type == "wellbeing_article") price * quantity else 0.0
            }
        }
}

data class WellbeingArticle(
    val id: Long,
    val name: String,
    val icon: String,
    val unit: String,
    val category: String = "",
    val vendorIds: Set<Long> = emptySet(),
)

data class VendorOption(val id: Long, val name: String, val cityId: Long, val cityName: String)

data class IngredientSupplyPreference(
    val id: Long,
    val ingredientId: Long,
    val ingredientName: String,
    val preferredVendorId: Long?,
    val preferredVendorName: String?,
    val preferredVendorCity: String?,
    val disliked: Boolean,
    val unavailable: Boolean,
    val note: String,
)

data class WellbeingSupplyPreference(
    val id: Long,
    val articleId: Long,
    val articleName: String,
    val preferredVendorId: Long?,
    val preferredVendorName: String?,
    val preferredVendorCity: String?,
    val unavailable: Boolean,
    val note: String,
)

data class ShoppingOverview(
    val lists: List<ShoppingList>,
    val articles: List<WellbeingArticle>,
    val ingredients: List<IngredientOption> = emptyList(),
    val vendors: List<VendorOption> = emptyList(),
    val ingredientPreferences: List<IngredientSupplyPreference> = emptyList(),
    val wellbeingPreferences: List<WellbeingSupplyPreference> = emptyList(),
    val offline: Boolean = false,
)
