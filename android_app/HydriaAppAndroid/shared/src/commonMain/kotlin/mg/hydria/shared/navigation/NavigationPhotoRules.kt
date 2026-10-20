package mg.hydria.shared.navigation

data class PhotoDimensions(val width: Int, val height: Int, val needsResize: Boolean)

object NavigationPhotoRules {
    const val JPEG_QUALITY = 80
    const val MAX_BYTES = 5 * 1024 * 1024

    fun sampleSize(width: Int, height: Int): Int {
        var sample = 1
        while (width / sample > 1600 || height / sample > 1600) sample *= 2
        return sample
    }

    fun dimensions(width: Int, height: Int): PhotoDimensions {
        val ratio = minOf(1f, 1280f / maxOf(width, height).toFloat())
        return if (ratio < 1f) PhotoDimensions(
            (width * ratio).toInt().coerceAtLeast(1),
            (height * ratio).toInt().coerceAtLeast(1),
            true,
        ) else PhotoDimensions(width, height, false)
    }

    fun checkSize(byteCount: Int) {
        if (byteCount > MAX_BYTES) error("Photo trop volumineuse")
    }
}
