package mg.hydria.desktop

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Calculate
import androidx.compose.material.icons.filled.Explore
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import mg.hydria.desktop.screens.CalculatorScreen
import mg.hydria.desktop.screens.NavigationScreen
import mg.hydria.desktop.screens.PlanningScreen
import mg.hydria.desktop.screens.ReadingsScreen
import mg.hydria.desktop.screens.RepairsScreen
import mg.hydria.desktop.screens.SearchScreen
import mg.hydria.desktop.screens.VolumeScreen

private fun DesktopScreen.icon(): ImageVector = when (this) {
    DesktopScreen.CALCULATRICE -> Icons.Filled.Calculate
    DesktopScreen.RECHERCHE -> Icons.Filled.Search
    DesktopScreen.RELEVES -> Icons.Filled.WaterDrop
    DesktopScreen.REPARATIONS -> Icons.Filled.Build
    DesktopScreen.PLANNING -> Icons.Filled.CalendarMonth
    DesktopScreen.NAVIGATION -> Icons.Filled.Explore
    DesktopScreen.VOLUMETRIQUE -> Icons.Filled.Receipt
}

@Composable
fun HydriaDesktopApp(model: DesktopAppModel) {
    MaterialTheme(colorScheme = darkColorScheme()) {
        Surface(modifier = Modifier.fillMaxSize()) {
            Row(Modifier.fillMaxSize()) {
                NavigationRail {
                    DesktopScreen.entries.forEach { screen ->
                        NavigationRailItem(
                            selected = model.screen == screen,
                            onClick = { model.screen = screen },
                            icon = { Icon(screen.icon(), contentDescription = screen.label) },
                            label = { Text(screen.label) },
                        )
                    }
                }
                Box(Modifier.fillMaxSize().padding(24.dp)) {
                    when (model.screen) {
                        DesktopScreen.CALCULATRICE -> CalculatorScreen()
                        DesktopScreen.RECHERCHE -> SearchScreen(model.session)
                        DesktopScreen.RELEVES -> ReadingsScreen(model.session)
                        DesktopScreen.REPARATIONS -> RepairsScreen(model.session)
                        DesktopScreen.PLANNING -> PlanningScreen(model.session)
                        DesktopScreen.NAVIGATION -> NavigationScreen(model.session, model.prefs)
                        DesktopScreen.VOLUMETRIQUE -> VolumeScreen(model.session)
                    }
                }
            }
        }
    }
}
