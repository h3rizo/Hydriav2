package mg.hydria.app

import android.app.DatePickerDialog
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Canvas
import android.graphics.Color
import android.media.AudioAttributes
import android.media.SoundPool
import android.os.Build
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.InsetDrawable
import android.graphics.drawable.LayerDrawable
import android.graphics.drawable.RippleDrawable
import android.text.InputType
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.animation.CycleInterpolator
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.Spinner
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.core.content.res.ResourcesCompat
import androidx.core.view.ViewCompat
import androidx.core.widget.TextViewCompat
import java.util.Locale

/**
 * Hydria Terrain — direction « Lisible au soleil ».
 *
 * Remplace HydriaVisuals.kt. Deux changements de fond :
 *
 *  1. les couleurs ne sont plus des constantes mais lues dans les ressources,
 *     donc values/ et values-night/ pilotent le mode clair et le mode sombre
 *     sans toucher au code ;
 *  2. les composants récurrents (ligne de tâche, carte de stat, pastille de
 *     synchronisation, onglet de navigation) sont des fabriques, pour que les
 *     ~3 000 lignes de MainActivity cessent d'assembler des LinearLayout à la main.
 *
 * Appeler HydriaColors.bind(this) au début de Activity.onCreate(), avant toute
 * construction de vue.
 *
 * Compat : quelques fabriques v2.3 restent (badge, stylePrimary/Secondary/Spinner)
 * car encore appelées par la calculatrice et la recherche ; SparklineView sert
 * toujours à l'histogramme « Complétude par ouvrage ».
 */
object HydriaColors {
    private var bound = false

    var backgroundDeep = 0; private set
    var background = 0; private set
    var surface = 0; private set
    var surfaceRaised = 0; private set
    var outline = 0; private set
    var outlineSoft = 0; private set
    var text = 0; private set
    var textSecondary = 0; private set
    var textMuted = 0; private set
    var cyan = 0; private set
    var cyanStrong = 0; private set
    var cyanWash = 0; private set
    var vase = 0; private set
    var vaseWash = 0; private set
    var success = 0; private set
    var successWash = 0; private set
    var warning = 0; private set
    var warningWash = 0; private set
    var error = 0; private set
    var errorWash = 0; private set
    var onAccent = 0; private set
    var ink = 0; private set

    // Texte coloré par un ton, et contour des champs (TRANSVERSE-03). Les accents ci-dessus
    // servent aux remplissages ; en clair ils n'atteignent pas 7:1 comme texte.
    var cyanText = 0; private set
    var successText = 0; private set
    var warningText = 0; private set
    var vaseText = 0; private set
    var errorText = 0; private set
    var fieldOutline = 0; private set

    /** À rappeler après un changement de configuration (bascule clair/sombre). */
    fun bind(context: Context) {
        fun c(id: Int) = ContextCompat.getColor(context, id)
        backgroundDeep = c(R.color.hydria_background_deep)
        background = c(R.color.hydria_background)
        surface = c(R.color.hydria_surface)
        surfaceRaised = c(R.color.hydria_surface_raised)
        outline = c(R.color.hydria_outline)
        outlineSoft = c(R.color.hydria_outline_soft)
        text = c(R.color.hydria_text)
        textSecondary = c(R.color.hydria_text_secondary)
        textMuted = c(R.color.hydria_text_muted)
        cyan = c(R.color.hydria_cyan)
        cyanStrong = c(R.color.hydria_cyan_strong)
        cyanWash = c(R.color.hydria_cyan_wash)
        vase = c(R.color.hydria_vase)
        vaseWash = c(R.color.hydria_vase_wash)
        success = c(R.color.hydria_success)
        successWash = c(R.color.hydria_success_wash)
        warning = c(R.color.hydria_warning)
        warningWash = c(R.color.hydria_warning_wash)
        error = c(R.color.hydria_error)
        errorWash = c(R.color.hydria_error_wash)
        onAccent = c(R.color.hydria_on_accent)
        ink = c(R.color.hydria_ink)
        cyanText = c(R.color.hydria_cyan_text)
        successText = c(R.color.hydria_success_text)
        warningText = c(R.color.hydria_warning_text)
        vaseText = c(R.color.hydria_vase_text)
        errorText = c(R.color.hydria_error_text)
        fieldOutline = c(R.color.hydria_field_outline)
        bound = true
    }

    fun requireBound() {
        check(bound) { "HydriaColors.bind(context) doit être appelé dans onCreate()." }
    }
}

enum class Tone { INFO, SUCCESS, WARNING, ERROR, NEUTRAL }

object HydriaType {
    private var display: Typeface? = null
    private var mono: Typeface? = null

    /** Archivo et Roboto Mono arrivent par le fournisseur de polices Google. */
    fun bind(context: Context) {
        display = runCatching { ResourcesCompat.getFont(context, R.font.archivo) }.getOrNull()
        mono = runCatching { ResourcesCompat.getFont(context, R.font.roboto_mono) }.getOrNull()
    }

    fun display(weight: Int = 600): Typeface =
        weighted(display ?: Typeface.SANS_SERIF, weight)

    /** Chiffres : toujours en mono, pour que les colonnes de valeurs s'alignent. */
    fun numeral(weight: Int = 700): Typeface =
        weighted(mono ?: Typeface.MONOSPACE, weight)

    /** Typeface.create(base, weight, italic) n'existe qu'en API 28 : repli en gras/normal. */
    private fun weighted(base: Typeface, weight: Int): Typeface =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            Typeface.create(base, weight.coerceIn(1, 1000), false)
        } else {
            Typeface.create(base, if (weight >= 600) Typeface.BOLD else Typeface.NORMAL)
        }
}

/**
 * Retour sonore + petites animations, discrets et ciblés — pas sur chaque
 * bouton de l'appli, seulement sur les moments qui comptent (sauvegarde,
 * confirmation, bascule d'onglet...). Lié une seule fois avec le contexte
 * Application (HydriaApp.onCreate) : contrairement aux couleurs/polices, un
 * SoundPool n'a pas besoin d'être re-bind à chaque Activity.
 */
object HydriaFeedback {
    private var pool: SoundPool? = null
    private var tapId = 0
    private var successId = 0
    private var errorId = 0

    fun bind(context: Context) {
        if (pool != null) return
        val attributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()
        val soundPool = SoundPool.Builder()
            .setMaxStreams(3)
            .setAudioAttributes(attributes)
            .build()
        tapId = soundPool.load(context, R.raw.tap, 1)
        successId = soundPool.load(context, R.raw.success, 1)
        errorId = soundPool.load(context, R.raw.error, 1)
        pool = soundPool
    }

    /** Clic discret : case à cocher, interrupteur, onglet, touche de clavier. */
    fun tap() {
        pool?.play(tapId, 1f, 1f, 1, 0, 1f)
    }

    /** Confirmation : relevé enregistré, réparation terminée. */
    fun success() {
        pool?.play(successId, 1f, 1f, 1, 0, 1f)
    }

    /** Échec de validation — ton grave bref, pas agressif. */
    fun error() {
        pool?.play(errorId, 1f, 1f, 1, 0, 1f)
    }

    /** Rebond d'échelle rapide — confirmation visuelle sur succès. */
    fun pulse(view: View) {
        view.animate().cancel()
        view.scaleX = 1f
        view.scaleY = 1f
        view.animate()
            .scaleX(1.08f).scaleY(1.08f)
            .setDuration(90)
            .withEndAction {
                view.animate().scaleX(1f).scaleY(1f).setDuration(90).start()
            }
            .start()
    }

    /** Léger tremblement horizontal — erreur de validation. */
    fun shake(view: View) {
        view.animate().cancel()
        val distance = HydriaUi.dp(view.context, 6f)
        view.translationX = 0f
        view.animate()
            .translationX(distance)
            .setDuration(300)
            .setInterpolator(CycleInterpolator(4f))
            .withEndAction { view.translationX = 0f }
            .start()
    }
}

object HydriaUi {
    fun dp(context: Context, value: Float): Float =
        value * context.resources.displayMetrics.density

    fun dpi(context: Context, value: Float): Int = dp(context, value).toInt()

    fun toneColor(tone: Tone): Int = when (tone) {
        Tone.INFO -> HydriaColors.cyan
        Tone.SUCCESS -> HydriaColors.success
        Tone.WARNING -> HydriaColors.warning
        Tone.ERROR -> HydriaColors.error
        Tone.NEUTRAL -> HydriaColors.textSecondary
    }

    /**
     * Couleur d'un TEXTE teinté par un ton (chip, badge, pastille, compteur). En clair elle est
     * plus sombre que [toneColor] pour atteindre ≥ 6,5:1 ; en sombre elle lui est identique.
     * [toneColor] reste réservé aux fonds, barres et filets.
     */
    fun toneTextColor(tone: Tone): Int = when (tone) {
        Tone.INFO -> HydriaColors.cyanText
        Tone.SUCCESS -> HydriaColors.successText
        Tone.WARNING -> HydriaColors.warningText
        Tone.ERROR -> HydriaColors.errorText
        Tone.NEUTRAL -> HydriaColors.textSecondary
    }

    fun toneWash(tone: Tone): Int = when (tone) {
        Tone.INFO -> HydriaColors.cyanWash
        Tone.SUCCESS -> HydriaColors.successWash
        Tone.WARNING -> HydriaColors.warningWash
        Tone.ERROR -> HydriaColors.errorWash
        Tone.NEUTRAL -> HydriaColors.surface
    }

    /**
     * Garde l'aspect de [visual] mais agrandit la zone tactile : le fond est inscrit dans un
     * InsetDrawable, la vue elle-même mesure la cible (48 dp). Appeler setPadding() APRÈS
     * avoir posé ce fond, car un InsetDrawable impose son propre padding à la vue.
     */
    fun withTouchInset(context: Context, visual: Drawable, insetHorizontalDp: Float = 0f, insetVerticalDp: Float = 0f): Drawable =
        InsetDrawable(visual, dpi(context, insetHorizontalDp), dpi(context, insetVerticalDp), dpi(context, insetHorizontalDp), dpi(context, insetVerticalDp))

    fun rounded(
        context: Context,
        color: Int,
        radiusDp: Float = 16f,
        strokeColor: Int? = null,
        strokeWidthDp: Float = 1f,
    ): GradientDrawable = GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        setColor(color)
        cornerRadius = dp(context, radiusDp)
        if (strokeColor != null) setStroke(dpi(context, strokeWidthDp), strokeColor)
    }

    fun ripple(context: Context, base: GradientDrawable, rippleOn: Int): RippleDrawable =
        RippleDrawable(ColorStateList.valueOf(Color.argb(48, Color.red(rippleOn), Color.green(rippleOn), Color.blue(rippleOn))), base, null)

    /** Carte plate : fond surface + filet 1dp. Plus d'élévation, plus d'ombre. */
    fun card(view: View, emphasized: Boolean = false) = view.apply {
        background = rounded(
            context,
            if (emphasized) HydriaColors.surfaceRaised else HydriaColors.surface,
            context.resources.getDimension(R.dimen.hydria_radius_card) / context.resources.displayMetrics.density,
            HydriaColors.outline,
        )
        elevation = 0f
    }

    /**
     * Carte avec filet de criticité à gauche — le signal visuel central de la
     * direction retenue : la couleur porte l'urgence, pas le fond de la carte.
     */
    fun accentedCard(view: View, tone: Tone) = view.apply {
        val radius = dp(context, 14f)
        val bar = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(toneColor(tone))
            // 4 coins arrondis comme le corps : décalé de 3 dp, il recouvre la barre à droite
            // (des coins droits carrés dépassaient en éclats colorés — TERRAIN-14).
            cornerRadius = radius
        }
        val body = rounded(context, HydriaColors.surface, 14f, HydriaColors.outline)
        background = LayerDrawable(arrayOf(bar, body)).apply {
            setLayerInset(1, dpi(context, 3f), 0, 0, 0)
        }
        elevation = 0f
    }

    fun primaryButton(button: Button, accent: Int = HydriaColors.cyan) = button.apply {
        val base = rounded(context, accent, 16f)
        background = ripple(context, base, HydriaColors.onAccent)
        setTextColor(HydriaColors.onAccent)
        isAllCaps = false
        textSize = 15f
        typeface = HydriaType.display(700)
        minHeight = dpi(context, 64f)
        stateListAnimator = null
        elevation = 0f
        setPadding(dpi(context, 18f), 0, dpi(context, 18f), 0)
    }

    fun secondaryButton(button: Button, active: Boolean = false) = button.apply {
        val base = rounded(
            context,
            if (active) HydriaColors.surfaceRaised else HydriaColors.surface,
            16f,
            if (active) HydriaColors.cyan else HydriaColors.outline,
        )
        background = ripple(context, base, HydriaColors.cyan)
        setTextColor(if (active) HydriaColors.cyanText else HydriaColors.textSecondary)
        isAllCaps = false
        textSize = 13f
        typeface = HydriaType.display(600)
        minHeight = dpi(context, 52f)
        stateListAnimator = null
        elevation = 0f
        setPadding(dpi(context, 14f), 0, dpi(context, 14f), 0)
    }

    /**
     * Bouton inactif LISIBLE : texte opaque (textSecondary) sur fond surfaceRaised avec contour,
     * sans `alpha` — la transparence divisait le contraste du libellé, seul endroit où le motif
     * du blocage est écrit (POINTAGE-06). Mêmes cotes que [primaryButton] pour que le bouton ne
     * saute pas ; rappeler [primaryButton] quand il redevient actif.
     */
    fun disabledButton(button: Button) = button.apply {
        background = rounded(context, HydriaColors.surfaceRaised, 16f, HydriaColors.fieldOutline)
        setTextColor(HydriaColors.textSecondary)
        isAllCaps = false
        textSize = 15f
        typeface = HydriaType.display(700)
        minHeight = dpi(context, 64f)
        stateListAnimator = null
        elevation = 0f
        alpha = 1f
        setPadding(dpi(context, 18f), 0, dpi(context, 18f), 0)
    }

    /**
     * Chip de filtre : pastille de 34 dp dans une zone tactile de 48 dp (TRANSVERSE-05). Dans une
     * rangée, ne PAS forcer sa hauteur (WRAP_CONTENT) : une hauteur fixe < 48 dp réduirait la
     * pastille visible d'autant (le fond est inscrit avec 7 dp de marge verticale).
     */
    fun chip(context: Context, label: String, active: Boolean): TextView = TextView(context).apply {
        text = label
        textSize = 12f
        typeface = HydriaType.display(600)
        gravity = Gravity.CENTER
        setTextColor(if (active) HydriaColors.cyanText else HydriaColors.textSecondary)
        background = withTouchInset(
            context,
            rounded(
                context,
                if (active) HydriaColors.surfaceRaised else HydriaColors.surface,
                17f,
                if (active) HydriaColors.cyan else HydriaColors.outline,
            ),
            insetVerticalDp = 7f,
        )
        minHeight = dpi(context, 48f)
        // Après le fond : un InsetDrawable impose son padding à la vue.
        setPadding(dpi(context, 14f), 0, dpi(context, 14f), 0)
    }

    /**
     * Pastille de synchronisation de l'en-tête : remplace la barre pleine
     * largeur de la v2.3. Toujours visible, jamais bloquante.
     */
    fun syncChip(context: Context, pending: Int, online: Boolean): TextView {
        val tone = when {
            !online -> Tone.ERROR
            pending > 0 -> Tone.WARNING
            else -> Tone.SUCCESS
        }
        val accent = toneColor(tone)
        return TextView(context).apply {
            text = if (pending > 0) pending.toString() else "à jour"
            textSize = 12.5f
            typeface = if (pending > 0) HydriaType.numeral(600) else HydriaType.display(600)
            setTextColor(toneTextColor(tone))
            gravity = Gravity.CENTER
            // Pastille visible de 38 dp dans une zone tactile de 48 dp (TRANSVERSE-05).
            minHeight = dpi(context, 48f)
            minWidth = dpi(context, 48f)
            background = withTouchInset(
                context,
                rounded(
                    context,
                    Color.argb(36, Color.red(accent), Color.green(accent), Color.blue(accent)),
                    19f,
                    Color.argb(115, Color.red(accent), Color.green(accent), Color.blue(accent)),
                ),
                insetVerticalDp = 5f,
            )
            setPadding(dpi(context, 13f), 0, dpi(context, 13f), 0)
            contentDescription = when {
                !online -> "Hors ligne, $pending action(s) conservée(s) sur ce téléphone"
                pending > 0 -> "$pending action(s) à synchroniser, toucher pour ouvrir le centre de synchronisation"
                else -> "Synchronisation à jour"
            }
        }
    }

    /**
     * Ligne de tâche : chiffre monospace à gauche, titre + sous-titre, chevron.
     * 68dp de haut — la cible entière est cliquable.
     */
    fun taskRow(
        context: Context,
        count: Int,
        title: String,
        subtitle: String,
        tone: Tone,
        onClick: (() -> Unit)? = null,
    ): View {
        val row = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = dpi(context, 68f)
            setPadding(dpi(context, 16f), 0, dpi(context, 16f), 0)
            accentedCard(this, if (count == 0) Tone.SUCCESS else tone)
            if (onClick != null) {
                isClickable = true
                isFocusable = true
                setOnClickListener { onClick() }
            }
        }
        // Colonne du chiffre : au moins 44 dp, elle s'élargit pour un nombre à 4 chiffres
        // (« 1282 » restait coupé en « 128 / 2 » dans 44 dp fixes — TERRAIN-05).
        row.addView(TextView(context).apply {
            text = if (count > 0) count.toString() else "✓"
            textSize = if (count > 0) 24f else 17f
            typeface = if (count > 0) HydriaType.numeral(700) else HydriaType.display(700)
            setTextColor(toneTextColor(if (count == 0) Tone.SUCCESS else tone))
            gravity = Gravity.END
            letterSpacing = -0.03f
            maxLines = 1
            minWidth = dpi(context, 44f)
            // Après textSize : l'autosize l'ignore une fois activé. Ne rétrécit que si la place manque.
            if (count > 0) TextViewCompat.setAutoSizeTextTypeUniformWithConfiguration(this, 14, 24, 1, TypedValue.COMPLEX_UNIT_SP)
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT))

        row.addView(LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            addView(TextView(context).apply {
                text = title
                textSize = 14.5f
                typeface = HydriaType.display(600)
                setTextColor(HydriaColors.text)
            })
            addView(TextView(context).apply {
                text = subtitle
                textSize = 11.5f
                typeface = HydriaType.display(400)
                setTextColor(HydriaColors.textSecondary)
            })
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
            marginStart = dpi(context, 14f)
        })

        if (count > 0) {
            row.addView(TextView(context).apply {
                text = "›"
                textSize = 20f
                setTextColor(HydriaColors.textMuted)
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            })
        }
        row.contentDescription = if (count > 0) "$title, $count restant(s)" else "$title, terminé"
        return row
    }

    /** Barre de progression plate — remplace l'ancien anneau de complétude. */
    fun progressBar(context: Context, percent: Int, accent: Int = HydriaColors.cyan): View {
        val value = percent.coerceIn(0, 100)
        val track = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            background = rounded(context, HydriaColors.outline, 5f)
            clipToOutline = true
            contentDescription = "$value pour cent complet"
        }
        track.addView(View(context).apply {
            background = rounded(context, accent, 5f)
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, value.toFloat().coerceAtLeast(0.001f)))
        track.addView(View(context), LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, (100 - value).toFloat().coerceAtLeast(0.001f)))
        return track
    }

    /**
     * Voile de chargement plein écran (scrim + spinner centré), affiché
     * brièvement lors d'un changement d'écran (barre du bas, rail tablette)
     * pour que la reconstruction synchrone de la vue ne paraisse jamais
     * figée. Masqué par défaut (GONE) ; capte les taps pendant qu'il est
     * visible pour empêcher un second changement d'écran superposé.
     */
    fun loadingOverlay(context: Context): View = FrameLayout(context).apply {
        setBackgroundColor(
            Color.argb(110, Color.red(HydriaColors.ink), Color.green(HydriaColors.ink), Color.blue(HydriaColors.ink))
        )
        visibility = View.GONE
        isClickable = true
        isFocusable = true
        addView(ProgressBar(context).apply {
            indeterminateTintList = ColorStateList.valueOf(HydriaColors.cyan)
        }, FrameLayout.LayoutParams(dpi(context, 40f), dpi(context, 40f), Gravity.CENTER))
    }

    fun styleInput(field: EditText) = field.apply {
        // Contour des champs ≥ 3:1 (hydria_field_outline) ; les cartes gardent hydria_outline.
        background = rounded(context, HydriaColors.surface, 14f, HydriaColors.fieldOutline)
        setTextColor(HydriaColors.text)
        setHintTextColor(HydriaColors.textMuted)
        typeface = HydriaType.display(500)
        textSize = 15f
        minHeight = dpi(context, 56f)
        setPadding(dpi(context, 16f), 0, dpi(context, 16f), 0)
    }

    /** Champ de valeur numérique : gros, monospace, encadré accentué. */
    fun styleNumeralInput(field: EditText) = field.apply {
        background = rounded(context, HydriaColors.surfaceRaised, 18f, HydriaColors.cyan, 2f)
        setTextColor(HydriaColors.text)
        setHintTextColor(HydriaColors.textMuted)
        typeface = HydriaType.numeral(700)
        textSize = 34f
        letterSpacing = -0.04f
        minHeight = dpi(context, 76f)
        setPadding(dpi(context, 18f), 0, dpi(context, 18f), 0)
    }

    /**
     * Champ de date sans clavier : affiche JJ/MM/AAAA, ouvre un sélecteur de date au toucher et garde la
     * valeur en ISO (AAAA-MM-JJ) dans [HydriaDateField.iso]. [initialIso] absent ou invalide = aujourd'hui.
     * [maxToday] : aucune date après aujourd'hui (fuseau Madagascar) ; à laisser à false pour une date
     * prévue (planning, réparation). [onChange] n'est appelé que lorsque l'utilisateur choisit une date.
     */
    fun dateField(
        context: Context,
        initialIso: String?,
        maxToday: Boolean = true,
        onChange: (String) -> Unit = {},
    ): HydriaDateField = HydriaDateField(context, maxToday).also {
        it.select(initialIso)
        it.onChange = onChange
    }

    /**
     * Section repliable (carte plate) : en-tête de 48 dp minimum avec [title], [summary] sur une ligne (ce qui
     * est caché dedans : « Remarque obligatoire », « 2 cartes »...) et chevron ; toucher l'en-tête ouvre ou ferme.
     * [content] est posé dans le corps de la carte (marges de 16 dp déjà faites) et ne doit pas avoir de parent.
     * L'ouverture par code passe par [HydriaCollapsible.setOpen], qui ne touche jamais au focus.
     */
    fun collapsible(context: Context, title: String, summary: String, open: Boolean, content: View): HydriaCollapsible =
        HydriaCollapsible(context, title, summary, open, content)

    /**
     * Barre d'action fixe en bas d'un écran (boutons « Enregistrer... ») : fond backgroundDeep, filet de 1 dp en
     * haut, padding de 10 dp. Elle réserve au-dessus des boutons un emplacement vide (GONE par défaut) pour une
     * bannière, voir [HydriaActionBar.showBanner]. À placer sous le défilement, dans un LinearLayout vertical :
     * ScrollView de poids 1, puis la barre.
     */
    fun actionBar(context: Context): HydriaActionBar = HydriaActionBar(context)

    fun overline(context: Context, value: String): TextView = TextView(context).apply {
        text = value
        textSize = 11f
        typeface = HydriaType.display(600)
        setTextColor(HydriaColors.textSecondary)
        letterSpacing = 0.09f
    }

    // ────────────────────────────────────────────────────────────────────
    //  Compatibilité v2.3 — retiré écran par écran au fil de la refonte.
    // ────────────────────────────────────────────────────────────────────

    /** Ancien badge pilule. Remplacé à terme par chip()/syncChip()/taskRow(). */
    fun badge(context: Context, value: String, tone: Tone = Tone.NEUTRAL): TextView {
        val foreground = toneColor(tone)
        val fill = Color.argb(35, Color.red(foreground), Color.green(foreground), Color.blue(foreground))
        return TextView(context).apply {
            text = value
            textSize = 11f
            setTextColor(toneTextColor(tone))
            typeface = HydriaType.display(600)
            gravity = Gravity.CENTER
            setPadding(dpi(context, 10f), dpi(context, 5f), dpi(context, 10f), dpi(context, 5f))
            background = rounded(
                context,
                fill,
                10f,
                Color.argb(90, Color.red(foreground), Color.green(foreground), Color.blue(foreground)),
            )
            contentDescription = value
        }
    }

    /** Alias de compatibilité : primaryButton(). */
    fun stylePrimary(button: Button) = primaryButton(button)

    /** Alias de compatibilité : secondaryButton(). */
    fun styleSecondary(button: Button, active: Boolean = false) = secondaryButton(button, active)

    fun styleSpinner(spinner: Spinner) = spinner.apply {
        background = rounded(context, HydriaColors.surface, 14f, HydriaColors.fieldOutline)
        setPadding(dpi(context, 12f), 0, dpi(context, 12f), 0)
    }
}

/**
 * Champ de date créé par [HydriaUi.dateField]. Un EditText mis en forme comme les autres champs, mais ni
 * focalisable ni éditable : le clavier ne s'ouvre jamais, un toucher ouvre le sélecteur de date.
 * La date est lue avec [iso] (toujours une date réelle, jamais le texte affiché).
 */
class HydriaDateField(context: Context, private val maxToday: Boolean) : EditText(context) {
    /** Appelé quand l'utilisateur choisit une date dans le sélecteur (pas lors d'un [select] programmatique). */
    var onChange: (String) -> Unit = {}

    /** Date choisie au format ISO (AAAA-MM-JJ). */
    var iso: String = HydriaDates.normalize(null, maxToday)
        private set

    init {
        HydriaUi.styleInput(this)
        setSingleLine(true)
        inputType = InputType.TYPE_NULL
        isFocusable = false
        isFocusableInTouchMode = false
        isCursorVisible = false
        isLongClickable = false
        hint = "JJ/MM/AAAA"
        // Pictogramme calendrier à droite : le champ s'ouvre comme un sélecteur, il ne se tape pas.
        setCompoundDrawablesRelativeWithIntrinsicBounds(0, 0, R.drawable.ic_planning, 0)
        compoundDrawableTintList = ColorStateList.valueOf(HydriaColors.textSecondary)
        compoundDrawablePadding = HydriaUi.dpi(context, 8f)
        setOnClickListener { pick() }
        showIso()
    }

    /** Fixe la date sans notifier [onChange] : [value] absent ou invalide = aujourd'hui, borné par maxToday. */
    fun select(value: String?) {
        iso = HydriaDates.normalize(value, maxToday)
        showIso()
    }

    private fun showIso() {
        setText(HydriaDates.display(iso))
        contentDescription = "Date : ${HydriaDates.display(iso)}. Toucher pour changer."
    }

    private fun pick() {
        val today = HydriaDates.today()
        val current = HydriaDates.parse(iso) ?: today
        val dialog = DatePickerDialog(context, { _, year, month, day ->
            iso = HydriaDates.normalize(String.format(Locale.US, "%04d-%02d-%02d", year, month + 1, day), maxToday, today)
            showIso()
            onChange(iso)
        }, current.year, current.monthValue - 1, current.dayOfMonth)
        if (maxToday) dialog.datePicker.maxDate = HydriaDates.pickerMaxMillis(today)
        dialog.show()
    }
}

/**
 * Section repliable créée par [HydriaUi.collapsible]. Un toucher sur l'en-tête (toute la largeur, 48 dp
 * minimum) ouvre ou ferme le corps ; [onToggle] n'est appelé que pour ces touchers (pas pour [setOpen]), par
 * exemple pour mémoriser que l'agent a ouvert ou fermé la section lui-même.
 */
class HydriaCollapsible(
    context: Context,
    private val title: String,
    summary: String,
    open: Boolean,
    /** Contenu fourni à la fabrique, déjà placé dans le corps de la carte. */
    val content: View,
) : LinearLayout(context) {
    /** Appelé avec le nouvel état quand l'utilisateur touche l'en-tête. */
    var onToggle: (Boolean) -> Unit = {}

    private var opened = open

    val isOpen: Boolean get() = opened

    private var summaryText = summary
    private val header = LinearLayout(context)
    private val summaryView = TextView(context)
    private val chevron = TextView(context)
    private val body = LinearLayout(context)

    init {
        orientation = VERTICAL
        HydriaUi.card(this)

        header.apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = HydriaUi.dpi(context, 48f)
            background = HydriaUi.ripple(context, HydriaUi.rounded(context, Color.TRANSPARENT, 16f), HydriaColors.cyan)
            setPadding(HydriaUi.dpi(context, 16f), HydriaUi.dpi(context, 8f), HydriaUi.dpi(context, 12f), HydriaUi.dpi(context, 8f))
            isClickable = true
            isFocusable = true
            setOnClickListener { setOpen(!opened, notify = true) }
        }
        val texts = LinearLayout(context).apply {
            orientation = VERTICAL
            addView(TextView(context).apply {
                text = title
                textSize = 14.5f
                typeface = HydriaType.display(600)
                setTextColor(HydriaColors.text)
            })
            summaryView.apply {
                textSize = 12f
                typeface = HydriaType.display(500)
                setTextColor(HydriaColors.textSecondary)
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
            }
            addView(summaryView)
        }
        header.addView(texts, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
        chevron.apply {
            text = "▾"
            textSize = 18f
            setTextColor(HydriaColors.textSecondary)
            gravity = Gravity.CENTER
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }
        header.addView(chevron, LayoutParams(HydriaUi.dpi(context, 28f), LayoutParams.WRAP_CONTENT))
        addView(header, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        body.apply {
            orientation = VERTICAL
            setPadding(HydriaUi.dpi(context, 16f), HydriaUi.dpi(context, 2f), HydriaUi.dpi(context, 16f), HydriaUi.dpi(context, 14f))
            addView(content, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        }
        addView(body, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        setSummary(summary)
        showState()
    }

    /**
     * Ouvre ou ferme sans prévenir [onToggle] (sauf [notify]). Ne déplace jamais le focus : ouvrir la section
     * parce qu'une règle l'exige ne doit pas voler le clavier au champ en cours de saisie.
     */
    fun setOpen(open: Boolean, notify: Boolean = false) {
        if (open == opened) return
        opened = open
        showState()
        if (notify) onToggle(open)
    }

    /** Remplace le résumé de l'en-tête ; un résumé vide masque la ligne. */
    fun setSummary(value: String) {
        summaryText = value
        summaryView.text = value
        summaryView.visibility = if (value.isBlank()) View.GONE else View.VISIBLE
        describe()
    }

    private fun showState() {
        body.visibility = if (opened) View.VISIBLE else View.GONE
        chevron.rotation = if (opened) 180f else 0f
        describe()
    }

    private fun describe() {
        header.contentDescription = if (summaryText.isBlank()) title else "$title. $summaryText"
        ViewCompat.setStateDescription(header, if (opened) "Déplié, toucher pour replier" else "Replié, toucher pour déplier")
    }
}

/**
 * Barre d'action fixe créée par [HydriaUi.actionBar] : colonne verticale [bannerSlot] (vide, GONE) puis les
 * boutons ajoutés avec [addButton]. Fond backgroundDeep, filet de 1 dp en haut, padding de 10 dp.
 */
class HydriaActionBar(context: Context) : LinearLayout(context) {
    /**
     * Emplacement libre au-dessus des boutons, GONE tant qu'il est vide : prévu pour la bannière « Annuler »
     * qui suit un enregistrement. Annoncé aux lecteurs d'écran quand son contenu apparaît.
     */
    val bannerSlot = FrameLayout(context)

    private var buttonCount = 0

    init {
        orientation = VERTICAL
        background = LayerDrawable(arrayOf(ColorDrawable(HydriaColors.outline), ColorDrawable(HydriaColors.backgroundDeep))).apply {
            setLayerInset(1, 0, HydriaUi.dpi(context, 1f), 0, 0)
        }
        // Après le fond : un Drawable peut imposer son padding à la vue.
        val pad = HydriaUi.dpi(context, 10f)
        setPadding(pad, pad, pad, pad)
        elevation = 0f
        bannerSlot.visibility = View.GONE
        bannerSlot.accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        addView(bannerSlot, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
            bottomMargin = HydriaUi.dpi(context, 8f)
        })
    }

    /** Affiche [banner] dans l'emplacement libre (il remplace l'éventuelle bannière précédente). */
    fun showBanner(banner: View) {
        bannerSlot.removeAllViews()
        bannerSlot.addView(banner, FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        bannerSlot.visibility = View.VISIBLE
    }

    /** Vide l'emplacement et le replie (GONE : la barre reprend sa hauteur d'origine). */
    fun clearBanner() {
        bannerSlot.removeAllViews()
        bannerSlot.visibility = View.GONE
    }

    /** Ajoute un bouton pleine largeur sous la bannière, 8 dp sous le bouton précédent. */
    fun addButton(button: View) {
        addView(button, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
            if (buttonCount > 0) topMargin = HydriaUi.dpi(context, 8f)
        })
        buttonCount++
    }
}

// ── Vue héritée — encore utilisée par « Complétude par ouvrage » (histogramme de débit). ──

class SparklineView(context: Context) : View(context) {
    var values: List<Double> = emptyList()
        set(value) {
            field = value
            contentDescription = if (value.isEmpty()) "Aucun historique" else "Historique de ${value.size} mesures"
            invalidate()
        }

    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = HydriaColors.cyan
        style = Paint.Style.STROKE
        strokeWidth = HydriaUi.dp(context, 2.5f)
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(28, Color.red(HydriaColors.cyan), Color.green(HydriaColors.cyan), Color.blue(HydriaColors.cyan))
        style = Paint.Style.FILL
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (values.size < 2) return
        val min = values.minOrNull() ?: return
        val max = values.maxOrNull() ?: return
        val range = (max - min).takeIf { it > 0.000001 } ?: 1.0
        val inset = HydriaUi.dp(context, 3f)
        val path = Path()
        val fill = Path()
        values.forEachIndexed { index, value ->
            val x = inset + (width - inset * 2) * index / (values.size - 1).toFloat()
            val y = inset + (height - inset * 2) * (1f - ((value - min) / range).toFloat())
            if (index == 0) {
                path.moveTo(x, y)
                fill.moveTo(x, height - inset)
                fill.lineTo(x, y)
            } else {
                path.lineTo(x, y)
                fill.lineTo(x, y)
            }
        }
        fill.lineTo(width - inset, height - inset)
        fill.close()
        canvas.drawPath(fill, fillPaint)
        canvas.drawPath(path, linePaint)
    }
}
