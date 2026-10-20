package mg.hydria.shared.volume

object VolumeRules {
    fun calculable(amountPresent: Boolean, calculationError: String): Boolean =
        amountPresent && calculationError.isBlank()

    fun collectable(pointed: Boolean, collected: Boolean, validated: Boolean, actions: Set<String>): Boolean =
        !pointed && !collected && actions.none { it == "collect" || it == "point" } &&
            (validated || "validate" in actions)

    fun <T, N> total(rows: List<T>, zero: N, amount: (T) -> N, add: (N, N) -> N): N =
        rows.fold(zero) { sum, row -> add(sum, amount(row)) }

    fun <N : Comparable<N>> matches(rowCount: Int, total: N, entry: N?, zero: N, pointed: Boolean): Boolean =
        rowCount > 0 && entry != null && total.compareTo(entry) == 0 && total > zero && !pointed

    fun requireSingleScope(scopes: List<Pair<String, String>>) {
        require(scopes.isNotEmpty())
        require(scopes.toSet().size == 1)
    }

    fun requireCanEnqueue(hasInvoices: Boolean, account: String, hasDuplicate: () -> Boolean) {
        require(hasInvoices) { "Sélectionnez au moins une facture" }
        require(account.isNotBlank()) { "Reconnectez la session avant de continuer" }
        require(!hasDuplicate()) { "Cette opération attend déjà une synchronisation" }
    }
}

data class VolumeQrInvoice<T>(val value: T, val id: String, val month: String, val workId: String, val number: String)

object VolumeQrRules {
    fun <T> find(raw: String, invoices: List<VolumeQrInvoice<T>>): T? {
        val parts = raw.trim().split('|')
        return if (parts.size == 6 && parts[0] == "HYDRIA" && parts[1] == "FACTURE") {
            invoices.singleOrNull { it.id == parts[2] && it.month == parts[4] && it.workId == parts[5] }?.value
        } else invoices.singleOrNull { it.number == raw.trim() }?.value
    }
}
