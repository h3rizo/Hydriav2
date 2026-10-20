package mg.hydria.bienetre.core.network

import org.junit.Assert.assertEquals
import org.junit.Test

class ShoppingDtoTest {
    @Test
    fun mapsVendorPriceAndDisplayFallbacks() {
        val item = ShoppingItemDto(
            id = 8,
            ingredientName = "Riz rouge",
            ingredientIcon = "🌾",
            quantity = "750.00",
            unit = "g",
            vendorId = 3,
            vendorName = "Marché Analakely",
            vendorCity = "Antananarivo",
            latestPrice = "600.00",
            latestPriceUnit = "100g",
        ).toModel()

        assertEquals("Riz rouge", item.name)
        assertEquals("Marché Analakely", item.vendorName)
        assertEquals(4_500.0, item.estimatedTotal, 0.0)
    }

    @Test
    fun estimatesKilogramPricingFromGramQuantity() {
        val item = ShoppingItemDto(
            id = 9,
            displayName = "Poulet",
            quantity = "1250",
            unit = "g",
            latestPrice = "16000",
            latestPriceUnit = "kg",
        ).toModel()

        assertEquals(20_000.0, item.estimatedTotal, 0.0)
    }
}
