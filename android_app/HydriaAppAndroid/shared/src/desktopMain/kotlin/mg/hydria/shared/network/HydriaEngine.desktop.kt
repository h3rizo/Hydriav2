package mg.hydria.shared.network

import io.ktor.client.engine.HttpClientEngineFactory
import io.ktor.client.engine.cio.CIO

actual val hydriaEngine: HttpClientEngineFactory<*> = CIO
