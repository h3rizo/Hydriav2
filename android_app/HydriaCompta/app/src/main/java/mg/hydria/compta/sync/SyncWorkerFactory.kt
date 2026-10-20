package mg.hydria.compta.sync

import android.content.Context
import androidx.work.ListenableWorker
import androidx.work.WorkerFactory
import androidx.work.WorkerParameters

/** Injection manuelle des workers (pas de Hilt). */
class SyncWorkerFactory(
    private val syncProvider: () -> SyncRepository,
) : WorkerFactory() {

    override fun createWorker(
        appContext: Context,
        workerClassName: String,
        workerParameters: WorkerParameters,
    ): ListenableWorker? = when (workerClassName) {
        InitialSyncWorker::class.java.name -> InitialSyncWorker(appContext, workerParameters, syncProvider())
        PullChangesWorker::class.java.name -> PullChangesWorker(appContext, workerParameters, syncProvider())
        PushOutboxWorker::class.java.name -> PushOutboxWorker(appContext, workerParameters, syncProvider())
        else -> null
    }
}
