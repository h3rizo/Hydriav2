package mg.hydria.logistique.feature.main

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Light = lightColorScheme(
    primary = Color(0xFF006B5B),
    onPrimary = Color.White,
    primaryContainer = Color(0xFF8CF8DD),
    secondary = Color(0xFF4B635C),
    tertiary = Color(0xFF8A4E00),
    background = Color(0xFFF7FAF7),
    surface = Color(0xFFF7FAF7),
)

private val Dark = darkColorScheme(
    primary = Color(0xFF70DBC2),
    primaryContainer = Color(0xFF005044),
    secondary = Color(0xFFB2CCC3),
    tertiary = Color(0xFFFFB870),
)

@Composable
fun LogistiqueTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, content = content)
}
