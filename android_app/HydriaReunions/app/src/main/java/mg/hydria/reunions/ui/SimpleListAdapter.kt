package mg.hydria.reunions.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import mg.hydria.reunions.R

/**
 * Adapter RecyclerView générique (titre + sous-titre), réutilisé par toutes
 * les listes simples de l'app (représentantes, réunions, conversations)
 * pour ne pas réécrire le même ViewHolder à chaque écran.
 */
class SimpleListAdapter<T>(
    private var items: List<T>,
    private val title: (T) -> String,
    private val subtitle: (T) -> String,
    private val onClick: (T) -> Unit,
) : RecyclerView.Adapter<SimpleListAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val title: TextView = view.findViewById(R.id.text_title)
        val subtitle: TextView = view.findViewById(R.id.text_subtitle)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_two_line, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = items[position]
        holder.title.text = title(item)
        holder.subtitle.text = subtitle(item)
        holder.itemView.setOnClickListener { onClick(item) }
    }

    override fun getItemCount(): Int = items.size

    fun submitList(newItems: List<T>) {
        items = newItems
        notifyDataSetChanged()
    }
}
