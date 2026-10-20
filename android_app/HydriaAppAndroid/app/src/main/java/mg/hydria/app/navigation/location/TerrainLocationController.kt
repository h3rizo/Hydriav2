package mg.hydria.app.navigation.location

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle

class TerrainLocationController(
    context: Context,
    private val onLocation: (Location) -> Unit,
    private val onUnavailable: (String) -> Unit,
) : LocationListener {
    private val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    private var running = false

    @SuppressLint("MissingPermission")
    fun start() {
        if (running) return
        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
            .filter { runCatching { manager.isProviderEnabled(it) }.getOrDefault(false) }
        if (providers.isEmpty()) {
            onUnavailable("GPS indisponible")
            return
        }
        running = true
        providers.forEach { provider ->
            manager.getLastKnownLocation(provider)?.let(onLocation)
            manager.requestLocationUpdates(provider, 1_000L, 1f, this)
        }
    }

    fun stop() {
        if (running) manager.removeUpdates(this)
        running = false
    }

    override fun onLocationChanged(location: Location) = onLocation(location)
    override fun onProviderDisabled(provider: String) = onUnavailable("Localisation désactivée")
    override fun onProviderEnabled(provider: String) = Unit
    @Deprecated("Deprecated in Android")
    override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit
}

