package mg.hydria.bienetre

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import mg.hydria.bienetre.core.designsystem.BienetreTheme
import mg.hydria.bienetre.core.model.Dashboard
import mg.hydria.bienetre.core.model.FitnessOverview
import mg.hydria.bienetre.core.model.NutritionProgress
import mg.hydria.bienetre.core.model.ProfileMetrics
import mg.hydria.bienetre.core.model.ProfileOverview
import mg.hydria.bienetre.core.model.TodayWorkout
import mg.hydria.bienetre.core.model.WellbeingProfile
import mg.hydria.bienetre.core.model.WorkoutCycle
import mg.hydria.bienetre.core.preferences.ThemeMode
import mg.hydria.bienetre.feature.dashboard.DashboardScreen
import mg.hydria.bienetre.feature.dashboard.DashboardUiState
import mg.hydria.bienetre.feature.fitness.FitnessContent
import mg.hydria.bienetre.feature.fitness.FitnessScreen
import mg.hydria.bienetre.feature.fitness.FitnessUiState
import mg.hydria.bienetre.feature.profile.ProfileForm
import mg.hydria.bienetre.feature.profile.ProfileScreen
import mg.hydria.bienetre.feature.profile.ProfileUiState
import mg.hydria.bienetre.feature.progress.ProgressScreen
import mg.hydria.bienetre.feature.progress.ProgressUiState
import mg.hydria.bienetre.feature.shopping.ShoppingContent
import mg.hydria.bienetre.feature.shopping.ShoppingScreen
import mg.hydria.bienetre.feature.shopping.ShoppingUiState
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ConnectedScreensTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun dashboardShowsRealSectionsWithoutInventedHydration() {
        composeRule.setContent {
            BienetreTheme {
                DashboardScreen(
                    displayName = "Miora",
                    state = DashboardUiState.Content(
                        Dashboard(
                            date = "2026-08-31",
                            objective = "alimentation_saine",
                            metricsMessage = null,
                            missingProfileFields = emptyList(),
                            nutrition = NutritionProgress(
                                calories = mg.hydria.bienetre.core.model.NutrientProgress(0.0, null),
                                proteins = mg.hydria.bienetre.core.model.NutrientProgress(0.0, null),
                                carbohydrates = mg.hydria.bienetre.core.model.NutrientProgress(0.0, null),
                                fats = mg.hydria.bienetre.core.model.NutrientProgress(0.0, null),
                            ),
                            meals = emptyList(),
                            workouts = emptyList(),
                            shoppingItems = emptyList(),
                            latestMeasurement = null,
                            weightDelta = null,
                            suggestions = emptyList(),
                        ),
                    ),
                    onRetry = {},
                    onLogout = {},
                )
            }
        }

        composeRule.onNodeWithText("Bonjour, Miora").assertIsDisplayed()
        composeRule.onNodeWithText("Nutrition").assertIsDisplayed()
        composeRule.onNodeWithText("Hydratation").assertDoesNotExist()
    }

    @Test
    fun dashboardErrorOffersRecoveryAction() {
        composeRule.setContent {
            BienetreTheme {
                DashboardScreen(
                    displayName = "Miora",
                    state = DashboardUiState.Error("Connexion indisponible"),
                    onRetry = {},
                    onLogout = {},
                )
            }
        }

        composeRule.onNodeWithText("Impossible d’afficher votre journée").assertIsDisplayed()
        composeRule.onNodeWithText("Réessayer").assertIsDisplayed()
    }

    @Test
    fun profileShowsCalculatedMetricsAndSaveAction() {
        val overview = ProfileOverview(
            profile = WellbeingProfile(
                id = 1,
                username = "Miora",
                birthDate = null,
                gender = "",
                heightCm = null,
                referenceWeightKg = null,
                activitiesPerWeek = 0,
                averageDurationMinutes = 0,
                activityLevel = "",
                objective = "",
                fastingMode = "aucun",
                residenceCityId = null,
                residenceCityName = null,
                listedAsCoach = false,
                coachBio = "",
                coachSpecialties = "",
                coachAvailability = "",
            ),
            metrics = ProfileMetrics(
                complete = false,
                basalMetabolism = null,
                dailyEnergyExpenditure = null,
                calorieTarget = null,
                proteinTarget = null,
                carbohydrateTarget = null,
                fatTarget = null,
                calculatedActivityLevel = "",
                message = "Profil à compléter",
                missingFields = emptyList(),
            ),
        )
        composeRule.setContent {
            BienetreTheme {
                ProfileScreen(
                    state = ProfileUiState.Content(overview, ProfileForm()),
                    themeMode = ThemeMode.System,
                    onThemeModeChange = {},
                    onRetry = {},
                    onEdit = {},
                    onSave = {},
                )
            }
        }

        composeRule.onNodeWithText("Miora").assertIsDisplayed()
        composeRule.onNodeWithText("Métriques calculées").assertIsDisplayed()
        composeRule.onNodeWithText("Enregistrer le profil").assertIsDisplayed()
    }

    @Test
    fun emptyShoppingScreenExplainsHowToStart() {
        composeRule.setContent {
            BienetreTheme {
                ShoppingScreen(
                    state = ShoppingUiState.Content(ShoppingContent(emptyList(), emptyList())),
                    onRetry = {},
                    onGenerate = { _, _ -> },
                    onCheck = { _, _ -> },
                    onPurchaseDate = { _, _ -> },
                    onPrice = { _, _, _ -> },
                    onAddManual = { _, _, _ -> },
                    onSaveIngredientPreference = { _, _, _, _, _ -> },
                    onSaveWellbeingPreference = { _, _, _, _ -> },
                )
            }
        }

        composeRule.onNodeWithText("Vos achats").assertIsDisplayed()
        composeRule.onNodeWithText("Aucune liste active").assertIsDisplayed()
        composeRule.onNodeWithText("Générer").assertIsDisplayed()
    }

    @Test
    fun fitnessWithoutProgramOffersProgramCreation() {
        val overview = FitnessOverview(
            cycle = WorkoutCycle(plan = null, weeks = emptyList()),
            today = TodayWorkout(
                date = "2026-08-31",
                weekIndex = null,
                plan = null,
                items = emptyList(),
            ),
            daySession = null,
            history = emptyList(),
        )

        composeRule.setContent {
            BienetreTheme {
                FitnessScreen(
                    state = FitnessUiState.Content(FitnessContent(overview)),
                    onRetry = {},
                    onGenerate = { _, _, _ -> },
                    onStart = {},
                    onEnd = {},
                    onComplete = { _, _, _, _, _, _, _ -> },
                    onPostpone = { _, _ -> },
                )
            }
        }

        composeRule.onNodeWithText("Votre entraînement").assertIsDisplayed()
        composeRule.onNodeWithText("Programme").assertIsDisplayed()
        composeRule.onNodeWithText("Aucun programme actif").assertIsDisplayed()
    }

    @Test
    fun emptyProgressScreenDoesNotInventMeasurements() {
        composeRule.setContent {
            BienetreTheme {
                ProgressScreen(
                    state = ProgressUiState.Content(mg.hydria.bienetre.core.model.ProgressOverview(emptyList())),
                    onBack = {},
                    onRetry = {},
                    onAdd = { _, _, _, _ -> },
                    onSelectPhoto = { _, _, _ -> },
                    onClearPhoto = {},
                    onUploadPhoto = { _, _ -> },
                )
            }
        }

        composeRule.onNodeWithText("Votre progression").assertIsDisplayed()
        composeRule.onNodeWithText("Aucune mesure").assertIsDisplayed()
        composeRule.onNodeWithText("68 kg").assertDoesNotExist()
    }
}
