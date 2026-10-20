package mg.hydria.compta.sync

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import androidx.core.app.NotificationCompat
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mg.hydria.compta.R
import mg.hydria.compta.core.AppResult

private const val CHANNEL_ID = "hydria_compta_sync"
private const val NOTIF_ID = 4201

/** 1 · Sync initiale complète, bloquante. Service au premier plan + progression. */
class InitialSyncWorker(
    context: Context,
    params: WorkerParameters,
    private val sync: SyncRepository,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        setForeground(foregroundInfo("Préparation des données comptables…"))
        when (val r = sync.runInitialSync { etape ->
            // Mise à jour de la notification à chaque étape.
            runCatching { setForegroundAsync(foregroundInfo(etape)) }
        }) {
            is AppResult.Ok -> Result.success()
            is AppResult.Err -> if (r.kind == AppResult.ErrorKind.NETWORK) Result.retry() else Result.failure()
        }
    }

    override suspend fun getForegroundInfo(): ForegroundInfo = foregroundInfo("Préparation des données comptables…")

    private fun foregroundInfo(text: String): ForegroundInfo {
        val manager = applicationContext.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, applicationContext.getString(R.string.sync_channel_name), NotificationManager.IMPORTANCE_LOW).apply {
                description = applicationContext.getString(R.string.sync_channel_desc)
            }
        )
        val notification: Notification = NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setContentTitle("Hydria Compta")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setOngoing(true)
            .setProgress(0, 0, true)
            .build()
        return if (android.os.Build.VERSION.SDK_INT >= 34) {
            ForegroundInfo(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            ForegroundInfo(NOTIF_ID, notification)
        }
    }
}

/** 2 · Pull incrémental (périodique + manuel). */
class PullChangesWorker(
    context: Context,
    params: WorkerParameters,
    private val sync: SyncRepository,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        when (val r = sync.runPull()) {
            is AppResult.Ok -> Result.success()
            is AppResult.Err -> if (r.kind == AppResult.ErrorKind.NETWORK) Result.retry() else Result.failure()
        }
    }
}

/** 3 · Push de l'outbox (déclenché à chaque mutation + retry backoff). */
class PushOutboxWorker(
    context: Context,
    params: WorkerParameters,
    private val sync: SyncRepository,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        when (val r = sync.runPush()) {
            is AppResult.Ok -> Result.success()
            is AppResult.Err ->
                if (r.kind == AppResult.ErrorKind.NETWORK || r.kind == AppResult.ErrorKind.SERVER) Result.retry()
                else Result.failure()
        }
    }
}
