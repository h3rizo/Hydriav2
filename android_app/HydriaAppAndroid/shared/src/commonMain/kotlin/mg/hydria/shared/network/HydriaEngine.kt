package mg.hydria.shared.network

import io.ktor.client.engine.HttpClientEngineFactory

/**
 * Moteur HTTP Ktor propre a chaque plateforme : OkHttp sur Android
 * (androidMain), CIO sur Desktop (desktopMain). Voir HydriaHttpClient.kt.
 */
expect val hydriaEngine: HttpClientEngineFactory<*>
