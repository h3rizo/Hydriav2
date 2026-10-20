package mg.hydria.app

import android.app.Application
import androidx.appcompat.app.AppCompatDelegate
import mg.hydria.app.repairs.RepairsSync
import mg.hydria.app.planning.PlanningsSync
import mg.hydria.app.terrain.TerrainSync
import mg.hydria.app.navigation.NavigationSync
import mg.hydria.app.pointage.PointageStore
import mg.hydria.app.pointage.PointageSync

/**
 * Point d'entrée du processus. Active le mode « clair + sombre automatiques »
 * (direction « Lisible au soleil ») : le thème Theme.HydriaApp est en DayNight
 * et bascule seul avec le réglage système.
 *
 * La résolution des couleurs et des polices se fait ensuite par Activity, via
 * HydriaColors.bind(this) / HydriaType.bind(this) en tête de onCreate().
 */
class HydriaApp : Application() {
    override fun onCreate() {
        super.onCreate()
        AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM)
        // Contexte Application : pas besoin de re-bind par Activity comme les
        // couleurs/polices, un SoundPool n'a pas de dépendance au thème.
        HydriaFeedback.bind(applicationContext)
        // Chaque domaine extrait de MainActivity enregistre ici ses operations de synchro
        // (voir mg.hydria.app.sync.SyncDispatch).
        RepairsSync.register()
        PlanningsSync.register()
        TerrainSync.register()
        NavigationSync.register()
        PointageStore.bind(applicationContext)
        PointageSync.register()
    }
}
