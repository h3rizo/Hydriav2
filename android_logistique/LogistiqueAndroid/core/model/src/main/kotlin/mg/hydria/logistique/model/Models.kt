package mg.hydria.logistique.model

import kotlinx.serialization.Serializable
import java.math.BigDecimal
import java.math.RoundingMode
import java.util.UUID

@JvmInline
@Serializable
value class DecimalQuantity(val value: String) {
    init {
        require(value.toBigDecimalOrNull() != null) { "Quantité décimale invalide" }
    }

    fun decimal(): BigDecimal = value.toBigDecimal().setScale(2, RoundingMode.UNNECESSARY)
    fun isPositive(): Boolean = decimal() > BigDecimal.ZERO
    fun isBetween(min: DecimalQuantity, max: DecimalQuantity): Boolean =
        decimal() >= min.decimal() && decimal() <= max.decimal()

    companion object {
        val ZERO = DecimalQuantity("0.00")
        fun of(value: BigDecimal) = DecimalQuantity(value.setScale(2, RoundingMode.HALF_UP).toPlainString())
    }
}

@Serializable
enum class StockStatus { OK, LOW, OUT }

@Serializable
enum class SyncStatus { DRAFT, PENDING, RUNNING, SYNCED, CONFLICT, REJECTED }

@Serializable
enum class OperationType {
    CREATE_PURCHASE, RECEIVE_PURCHASE, CREATE_DELIVERY, DELIVER_PENDING,
    CREATE_TRANSFER, SEND_TRANSFER, RECEIVE_TRANSFER, CANCEL_TRANSFER,
    CREATE_INVENTORY, ADJUST_STOCK, CREATE_FIELD_RETURN
}

@Serializable
enum class TransferStatus(val wireValue: String) {
    PENDING("en_attente"), IN_TRANSIT("en_cours"), RECEIVED("recu"), CANCELLED("annule")
}

@Serializable
enum class PurchaseStatus(val wireValue: String) {
    DRAFT("brouillon"), ORDERED("commande"), DELIVERED("livre"), RECEIVED("recu"),
    INVOICED("facture"), PAID("paye"), CANCELLED("annule")
}

@Serializable
data class StockPosition(
    val id: String,
    val articleId: String,
    val articleCode: String,
    val designation: String,
    val unit: String,
    val baseId: String,
    val baseName: String,
    val magasinId: String?,
    val magasinName: String?,
    val current: DecimalQuantity,
    val reserved: DecimalQuantity,
    val available: DecimalQuantity,
    val revision: Long,
    val estimated: Boolean = false,
    val status: StockStatus = StockStatus.OK,
)

@Serializable
data class TransferLineInput(
    val localId: String = UUID.randomUUID().toString(),
    val designationId: String,
    val designation: String,
    val quantity: DecimalQuantity,
)

@Serializable
data class CreateTransferInput(
    val transferDateIso: String,
    val originMagasinId: String,
    val destinationMagasinId: String,
    val initiatedById: String? = null,
    val expectedArrivalDateIso: String? = null,
    val notes: String? = null,
    val lines: List<TransferLineInput>,
) {
    fun validate(): List<String> = buildList {
        if (originMagasinId == destinationMagasinId) add("Les magasins d’origine et de destination doivent être différents.")
        if (lines.isEmpty()) add("Ajoutez au moins un article.")
        if (lines.any { !it.quantity.isPositive() }) add("Chaque quantité doit être strictement positive.")
    }
}

@Serializable
data class ReceiveTransferLineInput(
    val transferItemId: String,
    val sent: DecimalQuantity,
    val received: DecimalQuantity,
) {
    fun isValid(): Boolean = received.isBetween(DecimalQuantity.ZERO, sent)
}

@Serializable
data class OutboxEnvelope(
    val clientOperationId: String = UUID.randomUUID().toString(),
    val operationType: OperationType,
    val localEntityId: String,
    val userId: String,
    val deviceId: String,
    val businessDateIso: String,
    val createdAtIso: String,
    val knownServerRevision: Long?,
    val payloadJson: String,
    val dependencyIds: List<String> = emptyList(),
)
