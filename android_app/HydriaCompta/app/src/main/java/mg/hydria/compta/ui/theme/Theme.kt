package mg.hydria.compta.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Teal = Color(0xFF16302B)
private val Copper = Color(0xFFA85B2B)

private val LightColors = lightColorScheme(
    primary = Teal,
    secondary = Copper,
    background = Color(0xFFF4F1E9),
    surface = Color(0xFFFFFFFF),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF9FD3C7),
    secondary = Color(0xFFD68C5E),
    background = Color(0xFF0E1917),
    surface = Color(0xFF16211F),
)

@Composable
fun HydriaComptaTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = MaterialTheme.typography,
        content = content,
    )
}
