package mg.hydria.shared.network

import io.ktor.client.engine.HttpClientEngineFactory
import io.ktor.client.engine.okhttp.OkHttp

actual val hydriaEngine: HttpClientEngineFactory<*> = OkHttp
