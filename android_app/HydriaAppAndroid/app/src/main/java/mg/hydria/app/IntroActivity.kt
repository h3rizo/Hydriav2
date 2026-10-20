package mg.hydria.app

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import mg.hydria.shared.ui.intro.HydriaIntro

/**
 * Ecran de lancement : joue l'intro animee Hydria Terrain puis enchaine sur
 * [MainActivity]. Remplace MainActivity comme LAUNCHER dans le manifeste.
 */
class IntroActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Décodage du périmètre en tâche de fond pendant l'animation, pour que
        // MainActivity l'affiche sans bloquer le fil principal.
        OfflineStore.preloadSnapshot(this)
        val animationsOn = Settings.Global.getFloat(
            contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f
        ) != 0f
        setContent {
            HydriaIntro(
                animate = animationsOn,
                onFinished = {
                    startActivity(Intent(this, MainActivity::class.java))
                    finish()
                    @Suppress("DEPRECATION")
                    overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out)
                },
            )
        }
    }
}
