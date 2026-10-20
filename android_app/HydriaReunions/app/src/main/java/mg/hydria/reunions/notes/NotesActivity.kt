package mg.hydria.reunions.notes

import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import mg.hydria.reunions.HydriaReunionsApi
import mg.hydria.reunions.R
import mg.hydria.reunions.SessionManager
import mg.hydria.reunions.ui.SimpleListAdapter
import org.json.JSONObject
import java.util.concurrent.Executors

/**
 * Prise de note avancée attachée à une réunion ou une représentante
 * (adaptateur mobile au-dessus de l'app notes/ côté serveur — voir
 * apps.usagers.mobile_api_v1.notes_for_entity). Reste utilisable même si
 * les notes sont désactivées côté serveur (ENABLE_NOTES=False) : l'écran
 * affiche alors un message clair plutôt que de planter.
 */
class NotesActivity : AppCompatActivity() {
    companion object {
        const val EXTRA_ENTITY_TYPE = "entity_type"
        const val EXTRA_ENTITY_ID = "entity_id"
        const val EXTRA_ENTITY_LABEL = "entity_label"
    }

    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var session: SessionManager
    private lateinit var adapter: SimpleListAdapter<JSONObject>
    private lateinit var entityType: String
    private lateinit var entityId: String

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_notes)
        title = "Notes avancées"

        entityType = intent.getStringExtra(EXTRA_ENTITY_TYPE) ?: return finish()
        entityId = intent.getStringExtra(EXTRA_ENTITY_ID) ?: return finish()
        session = SessionManager(this)

        findViewById<TextView>(R.id.text_entity_label).text = intent.getStringExtra(EXTRA_ENTITY_LABEL) ?: ""

        adapter = SimpleListAdapter(
            items = emptyList(),
            title = { it.optString("title") },
            subtitle = { it.optString("content_text").take(120) },
            onClick = {},
        )
        findViewById<RecyclerView>(R.id.recycler_notes).apply {
            layoutManager = LinearLayoutManager(this@NotesActivity)
            adapter = this@NotesActivity.adapter
        }

        findViewById<android.widget.Button>(R.id.button_add_note).setOnClickListener { showAddNoteDialog() }

        loadNotes()
    }

    private fun loadNotes() {
        val token = session.token ?: return
        executor.execute {
            val result = HydriaReunionsApi.notesForEntity(token, entityType, entityId)
            runOnUiThread {
                if (result.successful && result.body.optString("error") == "NOTES_DISABLED") {
                    findViewById<TextView>(R.id.text_disabled).visibility = android.view.View.VISIBLE
                } else if (result.successful) {
                    val results = result.body.optJSONArray("results")
                    val notes = mutableListOf<JSONObject>()
                    if (results != null) for (i in 0 until results.length()) notes.add(results.getJSONObject(i))
                    adapter.submitList(notes)
                }
            }
        }
    }

    private fun showAddNoteDialog() {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 24, 48, 0)
        }
        val inputTitle = android.widget.EditText(this).apply { hint = "Titre" }
        val inputContent = android.widget.EditText(this).apply { hint = "Contenu" }
        container.addView(inputTitle)
        container.addView(inputContent)

        AlertDialog.Builder(this)
            .setTitle("Nouvelle note")
            .setView(container)
            .setPositiveButton("Créer") { _, _ ->
                val titleText = inputTitle.text?.toString()?.trim().orEmpty()
                if (titleText.isBlank()) return@setPositiveButton
                val token = session.token ?: return@setPositiveButton
                executor.execute {
                    val result = HydriaReunionsApi.notesQuickCreate(
                        token, entityType, entityId, titleText, inputContent.text?.toString()?.trim().orEmpty(),
                    )
                    runOnUiThread {
                        if (result.successful && result.body.optBoolean("success")) {
                            loadNotes()
                        } else {
                            Toast.makeText(this, result.error, Toast.LENGTH_SHORT).show()
                        }
                    }
                }
            }
            .setNegativeButton("Annuler", null)
            .show()
    }
}
