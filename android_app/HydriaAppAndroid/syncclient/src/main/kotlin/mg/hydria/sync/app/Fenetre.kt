package mg.hydria.sync.app

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.painter.BitmapPainter
import androidx.compose.ui.graphics.toComposeImageBitmap
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Notification
import androidx.compose.ui.window.Tray
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.isTraySupported
import androidx.compose.ui.window.rememberTrayState
import androidx.compose.ui.window.rememberWindowState
import kotlinx.coroutines.delay
import mg.hydria.sync.core.Config
import mg.hydria.sync.core.libelle

/** Point d'entree : `gradlew :syncclient:run`, ou l'executable cree par `createDistributable` / l'installateur. */
fun main(args: Array<String>) {
    val dossier = Config.dossierParDefaut()
    FichierJournal.marquerDemarrage()
    FichierJournal.initialiser(dossier)
    FichierJournal.installerGestionnaireGlobal()
    FichierJournal.ecrire("Démarrage de Hydria Sync (configuration : $dossier)")
    if (!InstanceUnique.obtenir(dossier)) {
        FichierJournal.ecrire("Hydria Sync est déjà ouverte : demande d'affichage de la fenêtre existante.")
        InstanceUnique.demanderOuverture(dossier)
        return
    }
    demarrer(dossier, reduit = DemarrageWindows.ARGUMENT_REDUIT in args)
}

private fun icone(etat: IconeHydria.Etat, angle: Double = 0.0, taille: Int = 64) =
    BitmapPainter(IconeHydria.dessiner(taille, etat, angle).toComposeImageBitmap())

private fun demarrer(dossier: java.nio.file.Path, reduit: Boolean) = application {
    val controleur = remember {
        try {
            SyncController()
        } catch (e: Throwable) {
            FichierJournal.erreur("création du contrôleur (configuration illisible ?)", e)
            throw e
        }
    }
    val etat by controleur.etat.collectAsState()

    // ---- reglages de la fenetre (theme, demarrage avec Windows)
    var preferences by remember { mutableStateOf(Preferences.charger(dossier)) }
    val sombre = preferences.sombre ?: remember { ThemeSysteme.sombre() }
    // Configuration redirigee (HYDRIA_SYNC_DIR : essais, installation portable) : on ne touche jamais au registre de Windows.
    val exe = remember { if (System.getenv("HYDRIA_SYNC_DIR").isNullOrBlank()) DemarrageWindows.cheminExecutable() else null }
    // Premiere utilisation : le demarrage avec Windows est propose active (reglage visible et desactivable dans la fenetre).
    val demarrageActif = preferences.demarrageWindows ?: true
    LaunchedEffect(demarrageActif, exe) {
        if (exe == null) return@LaunchedEffect
        // Reecrit l'entree a chaque lancement : suit l'application si elle a ete deplacee ou reinstallee.
        if (demarrageActif) DemarrageWindows.activer(exe) else DemarrageWindows.desactiver()
    }
    val options = OptionsUi(
        sombre = sombre,
        onBasculerTheme = {
            preferences = preferences.copy(sombre = !sombre).also { it.enregistrer(dossier) }
        },
        demarrageWindows = if (exe != null) demarrageActif else null,
        onDemarrageWindows = { actif ->
            preferences = preferences.copy(demarrageWindows = actif).also { it.enregistrer(dossier) }
        },
    )

    // ---- fenetre visible ou reduite dans la zone de notification
    val zoneNotification = isTraySupported
    // Lance au demarrage de Windows (--minimise) : discret, sauf s'il faut se connecter.
    var visible by remember { mutableStateOf(!(reduit && controleur.etat.value.connecte)) }
    LaunchedEffect(Unit) {
        while (true) {
            if (InstanceUnique.ouvertureDemandee(dossier)) visible = true
            delay(1000)
        }
    }

    fun quitter() {
        controleur.arreter()
        exitApplication()
    }

    if (zoneNotification) {
        val trayState = rememberTrayState()
        var image by remember { mutableStateOf(0) }
        LaunchedEffect(etat.enCours) {
            while (etat.enCours) {
                image = (image + 1) % IconeHydria.IMAGES_PAR_TOUR
                delay(120)
            }
            image = 0
        }
        val (titre, _) = titreEtat(etat)
        val etatIcone = when {
            etat.enCours -> IconeHydria.Etat.EN_COURS
            etat.conflits.isNotEmpty() -> IconeHydria.Etat.ATTENTION
            etat.erreurs.isNotEmpty() -> IconeHydria.Etat.ERREUR
            else -> IconeHydria.Etat.OK
        }
        val painter = remember(etatIcone, image) {
            icone(etatIcone, angleDegres(image))
        }
        // Une alerte (une seule par apparition) quand des conflits attendent une decision.
        LaunchedEffect(etat.conflits.size) {
            if (etat.conflits.isNotEmpty() && !visible) {
                trayState.sendNotification(Notification("Hydria Sync", "${etat.conflits.size} conflit(s) à résoudre", Notification.Type.Warning))
            }
        }
        Tray(
            icon = painter,
            state = trayState,
            tooltip = "Hydria Sync — " + (etat.progression?.takeIf { etat.enCours }?.libelle() ?: titre),
            onAction = { visible = true },
            menu = {
                Item("Ouvrir Hydria Sync", onClick = { visible = true })
                Item("Synchroniser maintenant", enabled = etat.connecte && !etat.enCours, onClick = { controleur.synchroniser() })
                Item("Ouvrir le dossier", enabled = etat.connecte, onClick = { controleur.ouvrirDossier() })
                Separator()
                Item("Quitter Hydria Sync", onClick = { quitter() })
            },
        )
    }

    Window(
        visible = visible,
        onCloseRequest = { if (zoneNotification) visible = false else quitter() },
        title = "Hydria Sync",
        icon = remember { icone(IconeHydria.Etat.OK) },
        state = rememberWindowState(width = 980.dp, height = 720.dp),
    ) {
        HydriaSyncApp(controleur, options)
    }
}

private fun angleDegres(image: Int) = image * 360.0 / IconeHydria.IMAGES_PAR_TOUR
