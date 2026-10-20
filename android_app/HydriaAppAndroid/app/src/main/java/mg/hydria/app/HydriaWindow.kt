package mg.hydria.app

import android.app.Activity
import android.content.Context
import android.graphics.Typeface
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat

/**
 * Hydria Terrain — comportement téléphone / tablette.
 *
 * Trois classes de largeur, alignées sur les Window Size Classes d'Android :
 *
 *   COMPACT   < 600dp   téléphone           un volet, onglets en bas
 *   MEDIUM    600-839dp petite tablette     rail vertical, un volet, listes en 2 colonnes
 *   EXPANDED  >= 840dp  tablette 10"        rail vertical + 2 ou 3 volets, sélection multiple
 *
 * Règles tenues par ce fichier :
 *  - les cibles tactiles ne grandissent JAMAIS avec l'écran (64dp reste 64dp) ;
 *  - les volets latéraux ont une largeur fixe, seul le volet de détail s'étire ;
 *  - aucune fonction métier n'est réservée à la tablette : le traitement par lot
 *    est un raccourci, pas un chemin unique.
 *
 * À recalculer dans onConfigurationChanged() : rotation, mode fenêtré et écrans
 * pliables changent la largeur utile sans recréer forcément l'Activity.
 */
enum class WindowWidth { COMPACT, MEDIUM, EXPANDED;
    val isTablet: Boolean get() = this != COMPACT
    val isTwoPane: Boolean get() = this == EXPANDED
}

object HydriaWindow {

    private const val MEDIUM_DP = 600
    private const val EXPANDED_DP = 840

    /** Largeur RÉELLE de la fenêtre, pas de l'écran : gère le multi-fenêtre. */
    fun of(activity: Activity): WindowWidth {
        val metrics = activity.resources.displayMetrics
        val widthDp = metrics.widthPixels / metrics.density
        return when {
            widthDp >= EXPANDED_DP -> WindowWidth.EXPANDED
            widthDp >= MEDIUM_DP -> WindowWidth.MEDIUM
            else -> WindowWidth.COMPACT
        }
    }

    // Largeurs de volet, en dp. Le volet de détail prend le reste.
    const val RAIL_DP = 92
    const val LIST_PANE_DP = 400
    const val CAMPAIGN_PANE_DP = 340
    const val ENTRY_PANE_DP = 392
    const val SIDE_PANEL_DP = 392

    /**
     * Construit la coquille de l'application selon la largeur.
     *
     * COMPACT  : [content] au-dessus d'une barre d'onglets horizontale.
     * MEDIUM   : rail vertical + [content].
     * EXPANDED : rail vertical + [content] (volet liste) + [detail] (volet détail).
     *
     * Les render*() existants de MainActivity ne changent pas : ils reçoivent
     * simplement le conteneur d'un volet au lieu du FrameLayout unique.
     */
    fun paneScaffold(
        activity: Activity,
        width: WindowWidth,
        navigation: View,
        content: FrameLayout,
        detail: FrameLayout? = null,
    ): View {
        val context: Context = activity
        fun dp(value: Int) = HydriaUi.dpi(context, value.toFloat())

        if (width == WindowWidth.COMPACT) {
            return LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                setBackgroundColor(HydriaColors.background)
                addView(content, LinearLayout.LayoutParams(-1, 0, 1f))
                addView(navigation, LinearLayout.LayoutParams(-1, dp(74)))
            }
        }

        return LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(HydriaColors.background)
            addView(navigation, LinearLayout.LayoutParams(dp(RAIL_DP), -1))
            if (width == WindowWidth.EXPANDED && detail != null) {
                addView(content, LinearLayout.LayoutParams(dp(LIST_PANE_DP), -1))
                addView(divider(context), LinearLayout.LayoutParams(dp(1), -1))
                addView(detail, LinearLayout.LayoutParams(0, -1, 1f))
            } else {
                addView(content, LinearLayout.LayoutParams(0, -1, 1f))
            }
        }
    }

    private fun divider(context: Context) = View(context).apply {
        setBackgroundColor(HydriaColors.outlineSoft)
    }

    /**
     * Rail de navigation vertical (MEDIUM et EXPANDED). Même jeu d'onglets que
     * la barre du bas : mêmes libellés, mêmes icônes, même ordre.
     */
    fun navigationRail(
        context: Context,
        tabs: List<RailTab>,
        selectedId: String,
        footer: View? = null,
    ): View = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER_HORIZONTAL
        setBackgroundColor(HydriaColors.backgroundDeep)
        setPadding(0, HydriaUi.dpi(context, 16f), 0, HydriaUi.dpi(context, 18f))

        addView(ImageView(context).apply {
            setImageResource(R.drawable.hydria_vase_foreground)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            contentDescription = context.getString(R.string.app_name)
        }, LinearLayout.LayoutParams(HydriaUi.dpi(context, 38f), HydriaUi.dpi(context, 38f)).apply {
            bottomMargin = HydriaUi.dpi(context, 20f)
        })

        tabs.forEach { tab ->
            addView(railItem(context, tab, tab.id == selectedId), LinearLayout.LayoutParams(
                HydriaUi.dpi(context, 72f), HydriaUi.dpi(context, 68f),
            ).apply { bottomMargin = HydriaUi.dpi(context, 10f) })
        }

        addView(View(context), LinearLayout.LayoutParams(0, 0, 1f))
        if (footer != null) addView(footer)
    }

    data class RailTab(
        val id: String,
        val label: String,
        val iconRes: Int,
        val badge: Int = 0,
        val onClick: () -> Unit,
    )

    private fun railItem(context: Context, tab: RailTab, selected: Boolean): View {
        val column = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            isClickable = true
            isFocusable = true
            isSelected = selected
            background = if (selected)
                HydriaUi.rounded(context, HydriaColors.surfaceRaised, 16f)
            else null
            setOnClickListener { tab.onClick() }
            contentDescription =
                if (selected) "${tab.label}, onglet sélectionné" else "${tab.label}, onglet"
        }
        column.addView(ImageView(context).apply {
            setImageDrawable(ContextCompat.getDrawable(context, tab.iconRes)?.mutate())
            imageTintList = android.content.res.ColorStateList.valueOf(
                if (selected) HydriaColors.cyan else HydriaColors.textSecondary,
            )
        }, LinearLayout.LayoutParams(HydriaUi.dpi(context, 24f), HydriaUi.dpi(context, 24f)))
        column.addView(TextView(context).apply {
            text = tab.label
            textSize = 10.5f
            typeface = HydriaType.display(if (selected) 600 else 500)
            setTextColor(if (selected) HydriaColors.cyan else HydriaColors.textSecondary)
            gravity = Gravity.CENTER
            setPadding(0, HydriaUi.dpi(context, 5f), 0, 0)
        }, LinearLayout.LayoutParams(-2, -2))

        if (tab.badge <= 0) return column

        // Pastille de compteur, posée par-dessus l'icône.
        return FrameLayout(context).apply {
            addView(column, FrameLayout.LayoutParams(-1, -1))
            addView(TextView(context).apply {
                text = if (tab.badge > 99) "99+" else tab.badge.toString()
                textSize = 10f
                typeface = HydriaType.numeral(700)
                setTextColor(HydriaColors.onAccent)
                gravity = Gravity.CENTER
                minWidth = HydriaUi.dpi(context, 17f)
                minHeight = HydriaUi.dpi(context, 17f)
                setPadding(HydriaUi.dpi(context, 4f), 0, HydriaUi.dpi(context, 4f), 0)
                background = HydriaUi.rounded(context, HydriaColors.error, 9f)
                contentDescription = "${tab.badge} en retard"
            }, FrameLayout.LayoutParams(-2, HydriaUi.dpi(context, 17f), Gravity.TOP or Gravity.END).apply {
                topMargin = HydriaUi.dpi(context, 8f)
                marginEnd = HydriaUi.dpi(context, 12f)
            })
        }
    }

    /**
     * Nombre de colonnes pour une grille de cartes, selon la largeur.
     * Aucun contenu ne dépasse 720dp : au-delà on ajoute une colonne, on n'étire pas.
     */
    fun gridColumns(width: WindowWidth): Int = when (width) {
        WindowWidth.COMPACT -> 1
        WindowWidth.MEDIUM -> 2
        WindowWidth.EXPANDED -> 3
    }

    /** La sélection multiple et la barre d'actions par lot n'existent qu'en EXPANDED. */
    fun supportsBatchSelection(width: WindowWidth): Boolean = width == WindowWidth.EXPANDED

    /**
     * En EXPANDED, l'historique et les factures deviennent un volet permanent :
     * showInvoicesDialog() ne doit alors PAS ouvrir d'AlertDialog.
     */
    fun showsDetailInline(width: WindowWidth): Boolean = width == WindowWidth.EXPANDED

    /** En-tête de volet : surtitre + titre, mêmes tailles qu'en COMPACT. */
    fun paneHeader(context: Context, overline: String, title: String, subtitle: String? = null): View =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(
                HydriaUi.dpi(context, 22f), HydriaUi.dpi(context, 20f),
                HydriaUi.dpi(context, 22f), HydriaUi.dpi(context, 16f),
            )
            addView(HydriaUi.overline(context, overline))
            addView(TextView(context).apply {
                text = title
                textSize = 24f
                typeface = HydriaType.display(700)
                setTextColor(HydriaColors.text)
                letterSpacing = -0.02f
            })
            if (subtitle != null) addView(TextView(context).apply {
                text = subtitle
                textSize = 12.5f
                typeface = HydriaType.display(400)
                setTextColor(HydriaColors.textSecondary)
            })
        }
}

/** Petit utilitaire : Typeface.create garde le poids sous API 28. */
private fun Typeface.orDefault(): Typeface = this
