package mg.hydria.reunions.representantes

import android.content.Intent
import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import mg.hydria.reunions.R
import mg.hydria.reunions.ReunionsDatabase
import mg.hydria.reunions.notes.NotesActivity
import mg.hydria.reunions.reunions.AvisFormActivity
import mg.hydria.reunions.ui.SimpleListAdapter
import org.json.JSONObject

class RepresentantDetailActivity : AppCompatActivity() {
    companion object {
        const val EXTRA_REPRESENTANT_JSON = "representant_json"
    }

    private lateinit var representant: JSONObject
    private lateinit var db: ReunionsDatabase

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_representant_detail)

        representant = JSONObject(intent.getStringExtra(EXTRA_REPRESENTANT_JSON) ?: "{}")
        db = ReunionsDatabase(this)
        title = representant.optString("nom", "Représentante")

        findViewById<TextView>(R.id.text_nom).text = representant.optString("nom", "Sans nom")
        findViewById<TextView>(R.id.text_village).text =
            "${representant.optString("village_nom")} · ${representant.optString("commune_nom")}"
        findViewById<TextView>(R.id.text_contact).text = representant.optString("contact").ifBlank { "Pas de contact enregistré" }

        findViewById<android.widget.Button>(R.id.button_new_avis).setOnClickListener {
            startActivity(
                Intent(this, AvisFormActivity::class.java)
                    .putExtra(AvisFormActivity.EXTRA_REPRESENTANT_ID, representant.getString("id"))
                    .putExtra(AvisFormActivity.EXTRA_REPRESENTANT_NOM, representant.optString("nom")),
            )
        }
        findViewById<android.widget.Button>(R.id.button_notes).setOnClickListener {
            startActivity(
                Intent(this, NotesActivity::class.java)
                    .putExtra(NotesActivity.EXTRA_ENTITY_TYPE, "representant")
                    .putExtra(NotesActivity.EXTRA_ENTITY_ID, representant.getString("id"))
                    .putExtra(NotesActivity.EXTRA_ENTITY_LABEL, representant.optString("nom")),
            )
        }

        val adapter = SimpleListAdapter<JSONObject>(
            items = emptyList(),
            title = { it.optString("date_avis") },
            subtitle = { "Satisfaction : ${it.optInt("score_satisfaction")}/4" + if (it.optBoolean("est_negatif")) " · À suivre" else "" },
            onClick = {},
        )
        findViewById<RecyclerView>(R.id.recycler_avis).apply {
            layoutManager = LinearLayoutManager(this@RepresentantDetailActivity)
            this.adapter = adapter
        }
        val avis = db.all("avis", parentId = representant.getString("id")).sortedByDescending { it.optString("date_avis") }
        adapter.submitList(avis)
    }
}
