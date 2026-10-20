package mg.hydria.bienetre.core.network

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

interface ShoppingSyncScheduler {
    fun schedule()
}

@Singleton
class WorkManagerShoppingSyncScheduler @Inject constructor(
    @param:ApplicationContext private val context: Context,
) : ShoppingSyncScheduler {
    override fun schedule() {
        val request = OneTimeWorkRequestBuilder<ShoppingCheckSyncWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            ShoppingCheckSyncWorker.WORK_NAME,
            ExistingWorkPolicy.APPEND_OR_REPLACE,
            request,
        )
    }
}

@HiltWorker
class ShoppingCheckSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted parameters: WorkerParameters,
    private val repository: ShoppingRepository,
) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = try {
        repository.syncPendingChecks()
        Result.success()
    } catch (error: ApiException) {
        when (error.kind) {
            ApiErrorKind.Unauthorized, ApiErrorKind.Forbidden -> Result.failure()
            ApiErrorKind.Network, ApiErrorKind.Server -> Result.retry()
        }
    } catch (_: Exception) {
        Result.retry()
    }

    companion object {
        const val WORK_NAME = "shopping-check-sync"
    }
}
