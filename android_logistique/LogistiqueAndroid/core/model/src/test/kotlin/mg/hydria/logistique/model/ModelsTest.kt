package mg.hydria.logistique.model

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelsTest {
    @Test fun `un transfert refuse des magasins identiques`() {
        val input = CreateTransferInput("2026-09-01T10:00:00+03:00", "m1", "m1", lines = emptyList())
        assertTrue(input.validate().size == 2)
    }

    @Test fun `une reception respecte zero et la quantite envoyee`() {
        val valid = ReceiveTransferLineInput("l1", DecimalQuantity("5.00"), DecimalQuantity("4.50"))
        val invalid = valid.copy(received = DecimalQuantity("5.01"))
        assertTrue(valid.isValid())
        assertFalse(invalid.isValid())
    }
}
