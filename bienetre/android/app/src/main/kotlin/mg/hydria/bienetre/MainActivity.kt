package mg.hydria.bienetre

import android.app.Activity
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.DarkMode
import androidx.compose.material.icons.outlined.FitnessCenter
import androidx.compose.material.icons.outlined.LightMode
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.RestaurantMenu
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import dagger.hilt.android.AndroidEntryPoint
import mg.hydria.bienetre.core.designsystem.BienetreTheme
import mg.hydria.bienetre.core.designsystem.BienetreBrandLogo
import mg.hydria.bienetre.core.model.AuthenticatedUser
import mg.hydria.bienetre.core.preferences.ThemeMode
import mg.hydria.bienetre.feature.auth.AuthRoute
import mg.hydria.bienetre.feature.auth.AuthState
import mg.hydria.bienetre.feature.auth.AuthViewModel
import mg.hydria.bienetre.feature.dashboard.DashboardRoute
import mg.hydria.bienetre.feature.fitness.FitnessRoute
import mg.hydria.bienetre.feature.meals.MealsRoute
import mg.hydria.bienetre.feature.household.HouseholdRoute
import mg.hydria.bienetre.feature.profile.ProfileRoute
import mg.hydria.bienetre.feature.progress.ProgressRoute
import mg.hydria.bienetre.feature.shopping.ShoppingRoute

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            BienetreRoot()
        }
    }
}

@Composable
private fun BienetreRoot(settingsViewModel: AppSettingsViewModel = hiltViewModel()) {
    val themeMode by settingsViewModel.themeMode.collectAsStateWithLifecycle()
    val systemDark = isSystemInDarkTheme()
    val darkTheme = when (themeMode) {
        ThemeMode.System -> systemDark
        ThemeMode.Light -> false
        ThemeMode.Dark -> true
    }
    val view = LocalView.current
    SideEffect {
        val window = (view.context as Activity).window
        WindowCompat.getInsetsController(window, view).apply {
            isAppearanceLightStatusBars = !darkTheme
            isAppearanceLightNavigationBars = !darkTheme
        }
    }
    BienetreTheme(darkTheme = darkTheme) {
        BienetreApp(themeMode, settingsViewModel::setThemeMode)
    }
}

@Composable
private fun BienetreApp(
    themeMode: ThemeMode,
    onThemeModeChange: (ThemeMode) -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val authState by viewModel.authState.collectAsStateWithLifecycle()
    val navController = rememberNavController()

    LaunchedEffect(authState) {
        val destination = when (authState) {
            AuthState.Checking -> return@LaunchedEffect
            AuthState.SignedOut -> "auth"
            is AuthState.SignedIn -> "home"
        }
        if (navController.currentDestination?.route != destination) {
            navController.navigate(destination) {
                popUpTo("root")
                launchSingleTop = true
            }
        }
    }

    NavHost(
        navController = navController,
        startDestination = "loading",
        route = "root",
    ) {
        composable("loading") { LoadingScreen() }
        composable("auth") { AuthRoute(viewModel) }
        composable("home") {
            val user = (authState as? AuthState.SignedIn)?.user
            if (user == null) LoadingScreen() else AuthenticatedShell(
                user = user,
                themeMode = themeMode,
                onThemeModeChange = onThemeModeChange,
                onLogout = viewModel::logout,
            )
        }
    }
}

@Composable
private fun LoadingScreen() {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        BienetreBrandLogo(Modifier.size(112.dp))
    }
}

@Composable
private fun AuthenticatedShell(
    user: AuthenticatedUser,
    themeMode: ThemeMode,
    onThemeModeChange: (ThemeMode) -> Unit,
    onLogout: () -> Unit,
) {
    val navController = rememberNavController()
    val currentRoute = navController.currentBackStackEntryAsState().value?.destination?.route
    val destinations = listOf(
        Triple("dashboard", "Accueil", Icons.Outlined.Home),
        Triple("meals", "Repas", Icons.Outlined.RestaurantMenu),
        Triple("fitness", "Sport", Icons.Outlined.FitnessCenter),
        Triple("shopping", "Courses", Icons.Outlined.ShoppingCart),
        Triple("profile", "Profil", Icons.Outlined.Person),
    )

    Scaffold(
        containerColor = Color.Transparent,
        topBar = {
            ThemeQuickSwitch(
                themeMode = themeMode,
                onThemeModeChange = onThemeModeChange,
            )
        },
        bottomBar = {
            Surface(
                color = MaterialTheme.colorScheme.background,
                contentColor = MaterialTheme.colorScheme.onBackground,
            ) {
                Box(
                    modifier = Modifier
                        .navigationBarsPadding()
                        .padding(horizontal = 18.dp, vertical = 10.dp),
                ) {
                    NavigationBar(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(24.dp)),
                        containerColor = MaterialTheme.colorScheme.surface,
                        contentColor = MaterialTheme.colorScheme.onSurface,
                        tonalElevation = 0.dp,
                    ) {
                        destinations.forEach { (route, label, icon) ->
                            NavigationBarItem(
                                selected = currentRoute == route,
                                onClick = {
                                    navController.navigate(route) {
                                        popUpTo("dashboard") { saveState = true }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                },
                                icon = {
                                    if (route == "dashboard") {
                                        BienetreBrandLogo(Modifier.size(28.dp), contentDescription = null)
                                    } else {
                                        Icon(icon, contentDescription = null)
                                    }
                                },
                                label = { Text(label) },
                            )
                        }
                    }
                }
            }
        },
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = "dashboard",
            modifier = Modifier.padding(innerPadding),
        ) {
            composable("dashboard") {
                DashboardRoute(
                    displayName = user.displayName,
                    onLogout = onLogout,
                    onSessionExpired = onLogout,
                )
            }
            composable("profile") {
                ProfileRoute(
                    themeMode = themeMode,
                    onThemeModeChange = onThemeModeChange,
                    onSessionExpired = onLogout,
                    onOpenProgress = { navController.navigate("progress") },
                )
            }
            composable("meals") {
                MealsRoute(onSessionExpired = onLogout, onOpenHousehold = { navController.navigate("household") })
            }
            composable("household") {
                HouseholdRoute(
                    currentUserId = user.id,
                    currentUserName = user.displayName,
                    onBack = { navController.popBackStack() },
                    onSessionExpired = onLogout,
                )
            }
            composable("shopping") {
                ShoppingRoute(onSessionExpired = onLogout)
            }
            composable("fitness") {
                FitnessRoute(onSessionExpired = onLogout)
            }
            composable("progress") {
                ProgressRoute(
                    onBack = { navController.popBackStack() },
                    onSessionExpired = onLogout,
                )
            }
        }
    }
}

@Composable
private fun ThemeQuickSwitch(
    themeMode: ThemeMode,
    onThemeModeChange: (ThemeMode) -> Unit,
) {
    val systemDark = isSystemInDarkTheme()
    val isDark = when (themeMode) {
        ThemeMode.System -> systemDark
        ThemeMode.Light -> false
        ThemeMode.Dark -> true
    }

    Surface(
        color = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.onBackground,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .height(56.dp)
                .padding(horizontal = 20.dp),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = if (isDark) Icons.Outlined.DarkMode else Icons.Outlined.LightMode,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
            )
            Text(
                text = if (isDark) "Mode sombre" else "Mode clair",
                modifier = Modifier.padding(horizontal = 10.dp),
                color = MaterialTheme.colorScheme.onBackground,
            )
            Switch(
                checked = isDark,
                onCheckedChange = { enabled ->
                    onThemeModeChange(if (enabled) ThemeMode.Dark else ThemeMode.Light)
                },
            )
        }
    }
}
