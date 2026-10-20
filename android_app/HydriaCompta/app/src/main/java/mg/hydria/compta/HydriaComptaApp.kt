package mg.hydria.compta

import android.app.Application
import androidx.work.Configuration
import mg.hydria.compta.di.AppGraph
import mg.hydria.compta.sync.SyncWorkerFactory

class HydriaComptaApp : Application(), Configuration.Provider {

    lateinit var graph: AppGraph
        private set

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph(this)
    }

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(SyncWorkerFactory(syncProvider = { graph.syncRepository }))
            .build()
}
