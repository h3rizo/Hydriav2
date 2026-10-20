package mg.hydria.bienetre.core.designsystem

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val WellnessOrange = Color(0xFFFF8A1E)
val WellnessOrangeSoft = Color(0xFFFFB24C)
val WellnessEmerald = Color(0xFF56D98C)
val WellnessSky = Color(0xFF46B7FF)
val WellnessGold = Color(0xFFF6C454)
val WellnessViolet = Color(0xFFB078FF)
val WellnessRose = Color(0xFFFF718C)
val WellnessNight = Color(0xFF07100D)
val WellnessNightSurface = Color(0xFF0D1714)

private val LightColors = lightColorScheme(
    primary = Color(0xFFE66F00),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFFDCC2),
    onPrimaryContainer = Color(0xFF4A2100),
    secondary = Color(0xFF087A4B),
    tertiary = Color(0xFF006590),
    background = Color(0xFFF0F7F3),
    onBackground = Color(0xFF13211B),
    surface = Color(0xFFF8FCFA),
    onSurface = Color(0xFF13211B),
    surfaceVariant = Color(0xFFE3ECE7),
    onSurfaceVariant = Color(0xFF52625A),
    outlineVariant = Color(0xFFD0DBD5),
)

private val DarkColors = darkColorScheme(
    primary = WellnessOrange,
    onPrimary = Color(0xFF321500),
    primaryContainer = Color(0xFF5F2D00),
    onPrimaryContainer = Color(0xFFFFDCC2),
    secondary = WellnessEmerald,
    onSecondary = Color(0xFF00391F),
    tertiary = WellnessSky,
    background = WellnessNight,
    onBackground = Color(0xFFF0FAF5),
    surface = WellnessNightSurface,
    onSurface = Color(0xFFF0FAF5),
    surfaceVariant = Color(0xFF17231F),
    onSurfaceVariant = Color(0xFFAAB9B1),
    outline = Color(0xFF627169),
    outlineVariant = Color(0xFF29362F),
)

@Composable
fun BienetreTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = BienetreTypography,
        content = content,
    )
}
