package mg.hydria.logistique

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.core.view.WindowCompat
import dagger.hilt.android.AndroidEntryPoint
import mg.hydria.logistique.feature.main.LogistiqueApp
import mg.hydria.logistique.feature.main.LogistiqueTheme

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContent { LogistiqueTheme { LogistiqueApp() } }
    }
}
