package mg.hydria.app

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.LayerDrawable
import android.graphics.drawable.RippleDrawable
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.core.content.res.ResourcesCompat

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
        display = ResourcesCompat.getFont(context, R.font.archivo)
        mono = ResourcesCompat.getFont(context, R.font.roboto_mono)
    }

    fun display(weight: Int = 600): Typeface =
        Typeface.create(display ?: Typeface.SANS_SERIF, weight, false)

    /** Chiffres : toujours en mono, pour que les colonnes de valeurs s'alignent. */
    fun numeral(weight: Int = 700): Typeface =
        Typeface.create(mono ?: Typeface.MONOSPACE, weight, false)
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

    fun toneWash(tone: Tone): Int = when (tone) {
        Tone.INFO -> HydriaColors.cyanWash
        Tone.SUCCESS -> HydriaColors.successWash
        Tone.WARNING -> HydriaColors.warningWash
        Tone.ERROR -> HydriaColors.errorWash
        Tone.NEUTRAL -> HydriaColors.surface
    }

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
    fun card(view: View, raised: Boolean = false) = view.apply {
        background = rounded(
            context,
            if (raised) HydriaColors.surfaceRaised else HydriaColors.surface,
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
            cornerRadii = floatArrayOf(radius, radius, 0f, 0f, 0f, 0f, radius, radius)
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
        setTextColor(if (active) HydriaColors.cyan else HydriaColors.textSecondary)
        isAllCaps = false
        textSize = 13f
        typeface = HydriaType.display(600)
        minHeight = dpi(context, 52f)
        stateListAnimator = null
        elevation = 0f
        setPadding(dpi(context, 14f), 0, dpi(context, 14f), 0)
    }

    /** Chip de filtre : 34dp, à utiliser en rangée horizontale scrollable. */
    fun chip(context: Context, label: String, active: Boolean): TextView = TextView(context).apply {
        text = label
        textSize = 12f
        typeface = HydriaType.display(600)
        gravity = Gravity.CENTER
        setTextColor(if (active) HydriaColors.cyan else HydriaColors.textSecondary)
        background = rounded(
            context,
            if (active) HydriaColors.surfaceRaised else HydriaColors.surface,
            17f,
            if (active) HydriaColors.cyan else HydriaColors.outline,
        )
        minHeight = dpi(context, 34f)
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
            setTextColor(accent)
            gravity = Gravity.CENTER
            minHeight = dpi(context, 38f)
            setPadding(dpi(context, 13f), 0, dpi(context, 13f), 0)
            background = rounded(
                context,
                Color.argb(36, Color.red(accent), Color.green(accent), Color.blue(accent)),
                19f,
                Color.argb(115, Color.red(accent), Color.green(accent), Color.blue(accent)),
            )
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
        row.addView(TextView(context).apply {
            text = if (count > 0) count.toString() else "✓"
            textSize = if (count > 0) 24f else 17f
            typeface = if (count > 0) HydriaType.numeral(700) else HydriaType.display(700)
            setTextColor(toneColor(if (count == 0) Tone.SUCCESS else tone))
            gravity = Gravity.END
            letterSpacing = -0.03f
        }, LinearLayout.LayoutParams(dpi(context, 44f), LinearLayout.LayoutParams.WRAP_CONTENT))

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

    /** Barre de progression plate — remplace CompletionRingView. */
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

    fun styleInput(field: EditText) = field.apply {
        background = rounded(context, HydriaColors.surface, 14f, HydriaColors.outline)
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

    fun overline(context: Context, value: String): TextView = TextView(context).apply {
        text = value
        textSize = 11f
        typeface = HydriaType.display(600)
        setTextColor(HydriaColors.textSecondary)
        letterSpacing = 0.09f
    }
}
