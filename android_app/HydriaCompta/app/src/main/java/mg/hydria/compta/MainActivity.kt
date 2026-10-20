package mg.hydria.compta

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import mg.hydria.compta.ui.AppRoot
import mg.hydria.compta.ui.theme.HydriaComptaTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val graph = (application as HydriaComptaApp).graph
        setContent {
            HydriaComptaTheme {
                AppRoot(graph = graph)
            }
        }
    }
}
