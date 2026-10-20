package mg.hydria.bienetre.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import mg.hydria.bienetre.core.model.ShoppingItem
import mg.hydria.bienetre.core.model.ShoppingList
import mg.hydria.bienetre.core.model.WellbeingArticle

@Serializable
data class ShoppingListDto(
    val id: Long,
    @SerialName("date_debut") val startDate: String,
    @SerialName("date_fin") val endDate: String,
    val items: List<ShoppingItemDto> = emptyList(),
)

@Serializable
data class ShoppingItemDto(
    val id: Long,
    @SerialName("item_type") val type: String = "ingredient",
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("ingredient_nom") val ingredientName: String? = null,
    @SerialName("wellbeing_article_nom") val articleName: String? = null,
    @SerialName("display_icon") val displayIcon: String? = null,
    @SerialName("ingredient_icone") val ingredientIcon: String? = null,
    @SerialName("wellbeing_article_icone") val articleIcon: String? = null,
    @SerialName("quantite_totale") val quantity: String = "0",
    @SerialName("unite") val unit: String = "",
    val checked: Boolean = false,
    @SerialName("purchase_date") val purchaseDate: String? = null,
    @SerialName("earliest_meal_date") val earliestMealDate: String? = null,
    @SerialName("latest_meal_date") val latestMealDate: String? = null,
    @SerialName("preferred_vendor_id") val vendorId: Long? = null,
    @SerialName("preferred_vendor_nom") val vendorName: String? = null,
    @SerialName("preferred_vendor_city_nom") val vendorCity: String? = null,
    @SerialName("latest_price") val latestPrice: String? = null,
    @SerialName("latest_price_unit") val latestPriceUnit: String? = null,
)

@Serializable
data class WellbeingArticleDto(
    val id: Long,
    @SerialName("nom") val name: String,
    @SerialName("icone") val icon: String? = null,
    @SerialName("unite_base") val unit: String = "piece",
)

@Serializable data class ShoppingVendorDto(
    val id: Long,
    @SerialName("nom") val name: String,
    @SerialName("city") val cityId: Long,
    @SerialName("city_nom") val cityName: String,
)
@Serializable data class ShoppingPreferenceMetaDto(val vendors: List<ShoppingVendorDto> = emptyList())
@Serializable data class WellbeingArticleOptionDto(
    val id: Long,
    @SerialName("nom") val name: String,
    @SerialName("icone") val icon: String = "",
    @SerialName("categorie") val category: String = "",
    @SerialName("unite_base") val unit: String = "piece",
    @SerialName("vendor_ids") val vendorIds: List<Long> = emptyList(),
)
@Serializable data class WellbeingPreferenceMetaDto(val articles: List<WellbeingArticleOptionDto> = emptyList())

@Serializable data class IngredientPreferenceDto(
    val id: Long,
    val ingredient: Long,
    @SerialName("ingredient_nom") val ingredientName: String = "",
    @SerialName("preferred_vendor") val preferredVendor: Long? = null,
    @SerialName("preferred_vendor_nom") val preferredVendorName: String? = null,
    @SerialName("preferred_vendor_city_nom") val preferredVendorCity: String? = null,
    @SerialName("is_disliked") val disliked: Boolean = false,
    @SerialName("is_unavailable") val unavailable: Boolean = false,
    val note: String = "",
)
@Serializable data class IngredientPreferenceRequest(
    val ingredient: Long,
    @SerialName("preferred_vendor") val preferredVendor: Long? = null,
    @SerialName("is_disliked") val disliked: Boolean,
    @SerialName("is_unavailable") val unavailable: Boolean,
    val note: String,
)
@Serializable data class WellbeingPreferenceDto(
    val id: Long,
    val article: Long,
    @SerialName("article_nom") val articleName: String = "",
    @SerialName("preferred_vendor") val preferredVendor: Long? = null,
    @SerialName("preferred_vendor_nom") val preferredVendorName: String? = null,
    @SerialName("preferred_vendor_city_nom") val preferredVendorCity: String? = null,
    @SerialName("is_unavailable") val unavailable: Boolean = false,
    val note: String = "",
)
@Serializable data class WellbeingPreferenceRequest(
    val article: Long,
    @SerialName("preferred_vendor") val preferredVendor: Long? = null,
    @SerialName("is_unavailable") val unavailable: Boolean,
    val note: String,
)

@Serializable data class ShoppingGenerateRequest(
    @SerialName("date_debut") val startDate: String,
    @SerialName("date_fin") val endDate: String,
    @SerialName("replace_existing") val replaceExisting: Boolean = true,
)
@Serializable data class ShoppingCheckRequest(val checked: Boolean)
@Serializable data class ShoppingCheckResponse(
    val id: Long,
    val checked: Boolean,
    @SerialName("purchase_date") val purchaseDate: String? = null,
)
@Serializable data class ShoppingPurchaseDateRequest(@SerialName("purchase_date") val purchaseDate: String?)
@Serializable data class ShoppingPurchaseDateResponse(
    val id: Long,
    @SerialName("purchase_date") val purchaseDate: String? = null,
)
@Serializable data class ShoppingPriceRequest(
    @SerialName("prix") val price: String,
    @SerialName("pricing_unit") val unit: String,
)
@Serializable data class ShoppingPriceResponse(
    @SerialName("prix") val price: String,
    @SerialName("pricing_unit") val unit: String,
)
@Serializable data class ManualShoppingItemRequest(
    @SerialName("wellbeing_article") val articleId: Long,
    @SerialName("quantite_totale") val quantity: String,
    @SerialName("unite") val unit: String,
)

internal fun ShoppingListDto.toModel() = ShoppingList(id, startDate, endDate, items.map { it.toModel() })
internal fun ShoppingItemDto.toModel() = ShoppingItem(
    id = id,
    name = displayName ?: ingredientName ?: articleName.orEmpty(),
    icon = displayIcon ?: ingredientIcon ?: articleIcon.orEmpty(),
    type = type,
    quantity = quantity.toDecimal(),
    unit = unit,
    checked = checked,
    purchaseDate = purchaseDate,
    earliestMealDate = earliestMealDate,
    latestMealDate = latestMealDate,
    vendorId = vendorId,
    vendorName = vendorName,
    vendorCity = vendorCity,
    latestPrice = latestPrice?.toDecimal(),
    latestPriceUnit = latestPriceUnit,
)
internal fun WellbeingArticleDto.toModel() = WellbeingArticle(id, name, icon.orEmpty(), unit)
private fun String.toDecimal() = replace(',', '.').toDoubleOrNull() ?: 0.0
