package mg.hydria.app

import android.content.Context
import android.graphics.Typeface
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.Filter
import android.widget.Filterable
import android.widget.TextView
import androidx.appcompat.widget.AppCompatAutoCompleteTextView
import mg.hydria.shared.rules.forms.AutocompleteMatch

/**
 * Champ « Ouvrage » avec autocomplétion, remplaçant les listes déroulantes :
 * l'utilisateur tape quelques lettres et choisit dans les propositions.
 * [selectedIndex] = position dans [labels] (-1 tant qu'aucun choix valide).
 */
class HydriaAutocomplete(
    context: Context,
    labels: List<String>,
    hintText: String = "Rechercher un ouvrage…",
) : AppCompatAutoCompleteTextView(context) {

    var labels: List<String> = labels
        set(value) { field = value; adapterImpl.reset(); selectedIndex = -1; setText("", false) }

    var selectedIndex: Int = -1
        private set

    /** Appelé à chaque choix valide (ou -1 quand la saisie ne correspond plus à rien). */
    var onSelected: ((Int) -> Unit)? = null

    private var programmatic = false
    private val adapterImpl = Adapter()

    init {
        hint = hintText
        setSingleLine(true)
        threshold = 1
        HydriaUi.styleInput(this)
        setAdapter(adapterImpl)
        setOnItemClickListener { _, _, position, _ ->
            val index = adapterImpl.indexAt(position)
            if (index >= 0) applySelection(index, notify = true)
        }
        // Afficher toute la liste au toucher, même sans saisie.
        setOnClickListener { if (adapterImpl.count > 0 || text.isNullOrEmpty()) { adapterImpl.filter.filter(text); showDropDown() } }
        setOnFocusChangeListener { _, focused ->
            if (focused) { adapterImpl.filter.filter(text); post { if (hasFocus()) showDropDown() } }
            else resolveTypedText()
        }
        addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                if (programmatic) return
                if (selectedIndex >= 0 && s?.toString() != labels.getOrNull(selectedIndex)) {
                    selectedIndex = -1
                    onSelected?.invoke(-1)
                }
            }
        })
    }

    override fun enoughToFilter(): Boolean = true

    /** Sélection par code (ex. valeur existante d'un formulaire). -1 vide le champ. */
    fun select(index: Int, notify: Boolean = false) {
        if (index !in labels.indices) {
            programmatic = true; setText("", false); programmatic = false
            selectedIndex = -1
            if (notify) onSelected?.invoke(-1)
            return
        }
        applySelection(index, notify)
    }

    private fun applySelection(index: Int, notify: Boolean) {
        programmatic = true
        setText(labels[index], false)
        setSelection(text?.length ?: 0)
        programmatic = false
        selectedIndex = index
        if (notify) onSelected?.invoke(index)
    }

    /** Saisie complète sans clic dans la liste : retenir le libellé s'il correspond exactement. */
    private fun resolveTypedText() {
        if (selectedIndex >= 0) return
        val typed = AutocompleteMatch.normalize(text?.toString().orEmpty())
        if (typed.isEmpty()) return
        val exact = labels.indexOfFirst { AutocompleteMatch.normalize(it) == typed }
        val single = AutocompleteMatch.filter(labels, typed).singleOrNull()
        (if (exact >= 0) exact else single)?.let { applySelection(it, notify = true) }
    }

    private inner class Adapter : BaseAdapter(), Filterable {
        private var visible: List<Int> = labels.indices.toList()

        fun reset() { visible = labels.indices.toList(); notifyDataSetChanged() }
        fun indexAt(position: Int): Int = visible.getOrElse(position) { -1 }

        override fun getCount() = visible.size
        override fun getItem(position: Int): String = labels[visible[position]]
        override fun getItemId(position: Int) = visible[position].toLong()

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
            val view = (convertView as? TextView) ?: TextView(parent.context).apply {
                setPadding(HydriaUi.dpi(context, 16f), HydriaUi.dpi(context, 14f), HydriaUi.dpi(context, 16f), HydriaUi.dpi(context, 14f))
                textSize = 15f
                typeface = Typeface.create("sans-serif", Typeface.NORMAL)
                setTextColor(HydriaColors.text)
                setBackgroundColor(HydriaColors.surface)
            }
            view.text = getItem(position)
            return view
        }

        override fun getFilter(): Filter = object : Filter() {
            override fun performFiltering(constraint: CharSequence?): FilterResults {
                // Le texte exact du choix courant ne doit pas masquer les autres options.
                val query = constraint?.toString().orEmpty()
                val showAll = selectedIndex >= 0 && query == labels.getOrNull(selectedIndex)
                val result = if (showAll) labels.indices.toList() else AutocompleteMatch.filter(labels, query)
                return FilterResults().apply { values = result; count = result.size }
            }

            @Suppress("UNCHECKED_CAST")
            override fun publishResults(constraint: CharSequence?, results: FilterResults?) {
                visible = (results?.values as? List<Int>) ?: emptyList()
                notifyDataSetChanged()
            }

            override fun convertResultToString(resultValue: Any?): CharSequence = resultValue?.toString().orEmpty()
        }
    }
}
