package mg.hydria.app

import android.content.Context
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.LinearLayout
import android.widget.Spinner
import android.widget.TextView
import mg.hydria.shared.rules.forms.ActivityCascadeTree
import org.json.JSONObject

/**
 * Trois listes en cascade : Groupe, puis Type d'activité, puis Activité.
 * Remplace la longue liste « Type - Activité » des formulaires Planning,
 * Réparation et Pointage. [selectedActivity] = l'activité choisie.
 */
class HydriaActivityCascade(
    context: Context,
    activities: List<JSONObject>,
    /** false : groupe masqué, toutes les activités fournies sont rangées sous un seul groupe. */
    private val showGroup: Boolean = true,
) : LinearLayout(context) {
    private val tree = if (showGroup) ActivityCascadeTree.build(activities) else ActivityCascadeTree.buildWithoutGroups(activities)
    private val groupSpinner = spinner()
    private val typeSpinner = spinner()
    private val activitySpinner = spinner()
    // Positions déjà appliquées : un Spinner rappelle onItemSelected de façon différée après
    // setSelection ; on ne réagit qu'à un vrai changement (sinon la présélection serait perdue).
    private var appliedGroup = -1
    private var appliedType = -1

    /** Appelé quand l'activité choisie change (règles de cible / composants à réappliquer). */
    var onActivityChanged: ((JSONObject?) -> Unit)? = null
    private var lastActivityId: String? = null

    val selectedActivity: JSONObject?
        get() = tree.getOrNull(groupSpinner.selectedItemPosition)
            ?.children?.getOrNull(typeSpinner.selectedItemPosition)
            ?.children?.getOrNull(activitySpinner.selectedItemPosition)?.activity

    init {
        orientation = VERTICAL
        if (showGroup) addLevel("Groupe", groupSpinner)
        addLevel("Type d'activité", typeSpinner)
        addLevel("Activité", activitySpinner)
        fill(groupSpinner, tree.map { it.name }, 0)
        fillTypes(0, 0)
        groupSpinner.onItemSelectedListener = listener { if (it != appliedGroup) fillTypes(it, 0) }
        typeSpinner.onItemSelectedListener = listener { if (it != appliedType) fillActivities(appliedGroup, it, 0) }
        activitySpinner.onItemSelectedListener = listener { notifyIfChanged() }
    }

    private fun notifyIfChanged() {
        val activity = selectedActivity
        val id = activity?.optString("id")
        if (id == lastActivityId) return
        lastActivityId = id
        onActivityChanged?.invoke(activity)
    }

    /** Verrouille la cascade (planning validé : l'activité ne peut plus changer). */
    fun setLocked(locked: Boolean) {
        listOf(groupSpinner, typeSpinner, activitySpinner).forEach {
            it.isEnabled = !locked && it.adapter != null && it.adapter.count > 0
            it.alpha = if (locked) 0.55f else 1f
        }
    }

    /** Présélectionne une activité existante (formulaire de modification). */
    fun select(activityId: String) {
        val (g, t, a) = ActivityCascadeTree.pathOf(tree, activityId) ?: return
        groupSpinner.setSelection(g, false)
        fillTypes(g, t, a)
    }

    private fun fillTypes(group: Int, type: Int, activity: Int = 0) {
        appliedGroup = group
        fill(typeSpinner, tree.getOrNull(group)?.children.orEmpty().map { it.name }, type)
        fillActivities(group, type, activity)
    }

    private fun fillActivities(group: Int, type: Int, activity: Int) {
        appliedType = type
        fill(activitySpinner, tree.getOrNull(group)?.children?.getOrNull(type)?.children.orEmpty().map { it.name }, activity)
        notifyIfChanged()
    }

    private fun fill(spinner: Spinner, labels: List<String>, selection: Int) {
        spinner.adapter = ArrayAdapter(context, android.R.layout.simple_spinner_dropdown_item, labels)
        if (labels.isNotEmpty()) spinner.setSelection(selection.coerceIn(0, labels.lastIndex), false)
        // Toujours une vraie liste déroulante, même avec un seul choix.
        spinner.isEnabled = labels.isNotEmpty()
        spinner.alpha = if (labels.isEmpty()) 0.45f else 1f
    }

    private fun spinner() = Spinner(context).apply { HydriaUi.styleSpinner(this) }

    private fun addLevel(title: String, spinner: Spinner) {
        addView(TextView(context).apply {
            text = title
            textSize = 12f
            setTextColor(HydriaColors.textSecondary)
            setPadding(0, HydriaUi.dpi(context, 6f), 0, HydriaUi.dpi(context, 2f))
        })
        // Le style Hydria du Spinner remplace son fond et donc la flèche native : on la redessine
        // pour qu'on voie qu'il s'agit d'une liste déroulante.
        addView(android.widget.FrameLayout(context).apply {
            addView(spinner, android.widget.FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
            addView(TextView(context).apply {
                text = "▾"
                textSize = 18f
                setTextColor(HydriaColors.textSecondary)
                isClickable = false
                isFocusable = false
            }, android.widget.FrameLayout.LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT,
                android.view.Gravity.END or android.view.Gravity.CENTER_VERTICAL).apply { marginEnd = HydriaUi.dpi(context, 14f) })
        }, LayoutParams(LayoutParams.MATCH_PARENT, HydriaUi.dpi(context, 50f)))
    }

    private fun listener(onPick: (Int) -> Unit) = object : AdapterView.OnItemSelectedListener {
        override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) = onPick(position)
        override fun onNothingSelected(parent: AdapterView<*>?) {}
    }
}
