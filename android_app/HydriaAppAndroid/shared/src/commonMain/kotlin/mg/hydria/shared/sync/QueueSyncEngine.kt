package mg.hydria.shared.sync

data class QueueResponse<R>(val successful: Boolean, val status: Int, val error: String, val body: R)

/** Executes one snapshot of the queue. Storage and network effects are supplied by the caller. */
object QueueSyncEngine {
    fun <O, P, R> run(
        operations: () -> Iterable<O>,
        id: (O) -> String,
        isVolume: (O) -> Boolean,
        syncVolume: (O) -> QueueResponse<R>,
        markSynchronizing: (String) -> Unit,
        payload: (O) -> P,
        send: (O, P) -> QueueResponse<R>,
        recordConflict: (O, P, R) -> Unit,
        confirmationError: (O, P, R) -> String?,
        markSynced: (O, P) -> Unit,
        remove: (String) -> Unit,
        markFailed: (String, String) -> Unit,
        afterQueue: () -> String?,
    ): String? {
        var failure: String? = null
        var activeUuid: String? = null
        try {
            for (operation in operations()) {
                val localUuid = id(operation)
                if (isVolume(operation)) {
                    val response = syncVolume(operation)
                    if (!response.successful) failure = response.error
                    continue
                }
                activeUuid = localUuid
                markSynchronizing(localUuid)
                val value = payload(operation)
                val response = send(operation, value)
                if (!response.successful) {
                    failure = response.error
                    if (response.status == 409) recordConflict(operation, value, response.body)
                    markFailed(localUuid, response.error)
                    activeUuid = null
                    continue
                }
                val error = confirmationError(operation, value, response.body)
                if (error != null) {
                    failure = error
                    markFailed(localUuid, error)
                    activeUuid = null
                    continue
                }
                markSynced(operation, value)
                remove(localUuid)
                activeUuid = null
            }
            afterQueue()?.let { failure = it }
        } catch (exception: Exception) {
            failure = exception.message ?: "Connexion interrompue"
            activeUuid?.let { markFailed(it, failure ?: "Connexion interrompue") }
        }
        return failure
    }
}
