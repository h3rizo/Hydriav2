package mg.hydria.compta.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkInfo
import androidx.work.WorkManager
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import mg.hydria.compta.data.db.ComptaDatabase
import mg.hydria.compta.data.db.entity.SyncStateKeys
import mg.hydria.compta.data.prefs.SyncPreferences
import kotlinx.coroutines.CoroutineScope
import java.time.Duration
import java.time.Instant

/**
 * Planification WorkManager + état de synchronisation agrégé pour l'UI.
 */
class SyncManager(
    private val context: Context,
    private val db: ComptaDatabase,
    private val prefs: SyncPreferences,
    scope: CoroutineScope,
) {

    private val workManager get() = WorkManager.getInstance(context)
    private val online = MutableStateFlow(true) // alimenté par un ConnectivityManager.NetworkCallback (à brancher)

    fun setOnline(value: Boolean) { online.value = value }

    val status: Flow<SyncStatus> = combine(
        online,
        workManager.getWorkInfosByTagFlow(WORK_ANY).map { infos ->
            infos.any { it.state == WorkInfo.State.RUNNING }
        },
        db.outboxDao().observeEnAttente(),
        db.outboxDao().observeAProbleme(),
        db.syncStateDao().observe(SyncStateKeys.LAST_PULL_OK),
    ) { online, running, enAttente, aProbleme, lastPull ->
        SyncStatus(
            online = online,
            running = running,
            enAttente = enAttente,
            aProbleme = aProbleme,
            dernierPullOk = lastPull?.takeIf { it.isNotBlank() }?.let(Instant::parse),
        )
    }.stateIn(scope, SharingStarted.WhileSubscribed(5_000L), SyncStatus(true, false, 0, 0, null))

    // ---- déclencheurs ----

    fun lancerSyncInitiale() {
        val request = OneTimeWorkRequestBuilder<InitialSyncWorker>()
            .setConstraints(reseau())
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .addTag(WORK_ANY)
            .build()
        workManager.enqueueUniqueWork(WORK_INITIAL, ExistingWorkPolicy.KEEP, request)
    }

    fun declencherPush() {
        val request = OneTimeWorkRequestBuilder<PushOutboxWorker>()
            .setConstraints(reseau())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, Duration.ofSeconds(30))
            .addTag(WORK_ANY)
            .build()
        workManager.enqueueUniqueWork(WORK_PUSH, ExistingWorkPolicy.APPEND_OR_REPLACE, request)
    }

    fun declencherPull() {
        val request = OneTimeWorkRequestBuilder<PullChangesWorker>()
            .setConstraints(reseau())
            .addTag(WORK_ANY)
            .build()
        workManager.enqueueUniqueWork(WORK_PULL_ONCE, ExistingWorkPolicy.KEEP, request)
    }

    fun planifierPullPeriodique() {
        val request = PeriodicWorkRequestBuilder<PullChangesWorker>(Duration.ofMinutes(15))
            .setConstraints(reseau())
            .addTag(WORK_ANY)
            .build()
        workManager.enqueueUniquePeriodicWork(WORK_PULL_PERIODIC, ExistingPeriodicWorkPolicy.KEEP, request)
    }

    /**
     * @param unmetered passer `true` quand le réglage « Wi-Fi uniquement » est actif
     *        (le flux [SyncPreferences.wifiOnly] est lu par l'appelant).
     */
    fun reseau(unmetered: Boolean = false): Constraints =
        Constraints.Builder()
            .setRequiredNetworkType(if (unmetered) NetworkType.UNMETERED else NetworkType.CONNECTED)
            .build()

    private companion object {
        const val WORK_ANY = "compta.sync"
        const val WORK_INITIAL = "compta.sync.initial"
        const val WORK_PUSH = "compta.sync.push"
        const val WORK_PULL_ONCE = "compta.sync.pull.once"
        const val WORK_PULL_PERIODIC = "compta.sync.pull.periodic"
    }
}
