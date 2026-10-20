package mg.hydria.app.terrain

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Base64
import mg.hydria.shared.navigation.NavigationPhotoRules
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Compression commune des photos Terrain (point d'eau / équipement) : même
 * réglage que Navigation terrain (1280 px max, JPEG 80, < 5 Mo), encodée en
 * base64 sans retour à la ligne pour l'opération `terrain_photo`.
 */
object TerrainPhotoEncoder {
    fun encode(photoFile: File): String {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(photoFile.absolutePath, bounds)
        val bitmap = BitmapFactory.decodeFile(
            photoFile.absolutePath,
            BitmapFactory.Options().apply { inSampleSize = NavigationPhotoRules.sampleSize(bounds.outWidth, bounds.outHeight) },
        ) ?: error("Photo illisible")
        val dimensions = NavigationPhotoRules.dimensions(bitmap.width, bitmap.height)
        val resized = if (dimensions.needsResize) Bitmap.createScaledBitmap(bitmap, dimensions.width, dimensions.height, true) else bitmap
        val output = ByteArrayOutputStream()
        resized.compress(Bitmap.CompressFormat.JPEG, NavigationPhotoRules.JPEG_QUALITY, output)
        if (resized !== bitmap) resized.recycle()
        bitmap.recycle()
        val bytes = output.toByteArray()
        NavigationPhotoRules.checkSize(bytes.size)
        return Base64.encodeToString(bytes, Base64.NO_WRAP)
    }

    /** Aperçu d'une photo reçue du serveur (« data:image/…;base64,… »), null pour une URL ou un format inconnu. */
    fun decodePreview(dataUri: String, maxSide: Int = 900): Bitmap? = runCatching {
        if (!dataUri.startsWith("data:")) return null
        val bytes = Base64.decode(dataUri.substringAfter(','), Base64.DEFAULT)
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        var sample = 1
        while (bounds.outWidth / sample > maxSide || bounds.outHeight / sample > maxSide) sample *= 2
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
    }.getOrNull()
}
