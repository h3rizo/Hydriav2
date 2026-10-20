package mg.hydria.compta.di

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import mg.hydria.compta.BuildConfig
import mg.hydria.compta.data.db.ComptaDatabase
import mg.hydria.compta.data.db.DatabaseFactory
import mg.hydria.compta.data.prefs.SessionStore
import mg.hydria.compta.data.prefs.SyncPreferences
import mg.hydria.compta.data.remote.ComptaApi
import mg.hydria.compta.data.repository.AuthRepository
import mg.hydria.compta.data.repository.ConflictRepository
import mg.hydria.compta.data.repository.OutboxRepository
import mg.hydria.compta.data.security.PassphraseProvider
import mg.hydria.compta.sync.SyncManager
import mg.hydria.compta.sync.SyncRepository

/**
 * Graphe de dépendances construit à la main (pas de Hilt), détenu par
 * [mg.hydria.compta.HydriaComptaApp]. Tout est lazy : la base chiffrée n'est
 * ouverte qu'au premier accès (après déverrouillage applicatif).
 */
class AppGraph(context: Context) {

    val appScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val session by lazy { SessionStore(context) }
    val syncPreferences by lazy { SyncPreferences(context) }

    private val passphraseProvider by lazy { PassphraseProvider(context) }
    val database: ComptaDatabase by lazy { DatabaseFactory.create(context, passphraseProvider) }

    val api by lazy {
        ComptaApi(
            baseUrl = BuildConfig.HYDRIA_BASE_URL,
            tokenProvider = { session.session.value?.accessToken },
        )
    }

    val authRepository by lazy { AuthRepository(api, session) }
    val outboxRepository by lazy { OutboxRepository(database) }
    val conflictRepository by lazy { ConflictRepository(database, outboxRepository) }

    val syncRepository by lazy {
        SyncRepository(database, api, session, outboxRepository, conflictRepository)
    }

    val syncManager by lazy {
        SyncManager(context.applicationContext, database, syncPreferences, appScope)
    }
}
