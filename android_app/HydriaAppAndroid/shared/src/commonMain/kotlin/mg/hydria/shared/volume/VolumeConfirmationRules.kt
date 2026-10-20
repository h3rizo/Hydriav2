package mg.hydria.shared.volume

object VolumeConfirmationRules {
    fun requireAccount(operationAccount: String, account: String) {
        require(operationAccount == account) { "Opération d'une autre session" }
    }
    fun requireUuid(serverUuid: String, localUuid: String) {
        require(serverUuid == localUuid) { "Confirmation serveur manquante" }
    }
    fun reviewNote(note: String): String {
        require(note.trim().length >= 10) { "Indiquez le résultat de la vérification (10 caractères minimum)" }
        return note.trim()
    }
    fun requireConflict(present: Boolean) {
        require(present) { "Réessayez la synchronisation : le résultat serveur n'est pas confirmé" }
    }
    fun failedRecapState(status: Int): String = if (status == 409) "refusee" else "en_attente"
}
