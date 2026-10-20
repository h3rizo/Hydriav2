package mg.hydria.shared.navigation

data class PhotoUploadResponse(val successful: Boolean, val error: String)
data class PhotoUploadResult(val successful: Boolean, val statusMessage: String)

object ImmediatePhotoUpload {
    fun run(
        markSynchronizing: () -> Unit,
        send: () -> PhotoUploadResponse,
        remove: () -> Unit,
        markFailed: (String) -> Unit,
    ): PhotoUploadResult {
        markSynchronizing()
        val response = runCatching { send() }.getOrNull()
        val successful = response?.successful == true
        if (successful) remove()
        else markFailed(response?.error ?: "Synchronisation de la photo impossible")
        return PhotoUploadResult(successful,
            if (successful) "Photo synchronisée" else "Photo conservée pour une prochaine synchronisation")
    }
}
