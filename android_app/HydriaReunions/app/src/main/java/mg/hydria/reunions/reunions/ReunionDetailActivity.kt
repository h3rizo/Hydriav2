package mg.hydria.reunions.reunions

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import com.google.android.material.textfield.TextInputEditText
import mg.hydria.reunions.HydriaReunionsApi
import mg.hydria.reunions.OutboxSyncer
import mg.hydria.reunions.R
import mg.hydria.reunions.ReunionsDatabase
import mg.hydria.reunions.SessionManager
import mg.hydria.reunions.notes.NotesActivity
import org.json.JSONObject
import java.io.File
import java.util.UUID
import java.util.concurrent.Executors

/**
 * Détail d'une réunion : compte-rendu/recommandations (édition + sauvegarde),
 * décisions de suivi, participants, pièces jointes (photo) et accès aux
 * notes avancées. Toute écriture passe d'abord en local (OutboxSyncer),
 * l'utilisateur voit son changement immédiatement même hors ligne.
 */
class ReunionDetailActivity : AppCompatActivity() {
    companion object {
        const val EXTRA_REUNION_JSON = "reunion_json"
    }

    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var reunion: JSONObject
    private lateinit var db: ReunionsDatabase
    private lateinit var outbox: OutboxSyncer
    private lateinit var session: SessionManager
    private var pendingPhotoFile: File? = null

    private val takePicture = registerForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        val file = pendingPhotoFile
        if (success && file != null) uploadPhoto(file)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_reunion_detail)

        reunion = JSONObject(intent.getStringExtra(EXTRA_REUNION_JSON) ?: "{}")
        db = ReunionsDatabase(this)
        session = SessionManager(this)
        outbox = OutboxSyncer(db, session)
        title = reunion.optString("objet", "Réunion")

        findViewById<TextView>(R.id.text_objet).text = reunion.optString("objet")
        findViewById<TextView>(R.id.text_meta).text =
            "${reunion.optString("date_reunion")} · ${reunion.optString("lieu_affiche")}"
        findViewById<TextInputEditText>(R.id.input_compte_rendu).setText(reunion.optString("compte_rendu"))
        findViewById<TextInputEditText>(R.id.input_recommandations).setText(reunion.optString("recommandations"))

        findViewById<android.widget.Button>(R.id.button_save_reunion).setOnClickListener { saveReunion() }
        findViewById<android.widget.Button>(R.id.button_add_decision).setOnClickListener { showAddDecisionDialog() }
        findViewById<android.widget.Button>(R.id.button_add_participant).setOnClickListener { showAddParticipantDialog() }
        findViewById<android.widget.Button>(R.id.button_add_photo).setOnClickListener { launchCamera() }
        findViewById<android.widget.Button>(R.id.button_notes).setOnClickListener {
            startActivity(
                Intent(this, NotesActivity::class.java)
                    .putExtra(NotesActivity.EXTRA_ENTITY_TYPE, "reunion")
                    .putExtra(NotesActivity.EXTRA_ENTITY_ID, reunion.getString("id"))
                    .putExtra(NotesActivity.EXTRA_ENTITY_LABEL, reunion.optString("objet")),
            )
        }

        renderDecisions()
        renderParticipants()
        renderPieces()
    }

    private fun saveReunion() {
        val payload = JSONObject().apply {
            put("id", reunion.getString("id"))
            put("compte_rendu", findViewById<TextInputEditText>(R.id.input_compte_rendu).text?.toString().orEmpty())
            put("recommandations", findViewById<TextInputEditText>(R.id.input_recommandations).text?.toString().orEmpty())
        }
        outbox.enqueue("reunion.update", payload)
        reunion.put("compte_rendu", payload.getString("compte_rendu"))
        reunion.put("recommandations", payload.getString("recommandations"))
        db.upsert("reunions", reunion.getString("id"), null, reunion, reunion.optString("updated_at"))
        Toast.makeText(this, "Enregistré (synchronisation en cours)", Toast.LENGTH_SHORT).show()
        executor.execute { outbox.flush() }
    }

    // --- Décisions ---

    private fun renderDecisions() {
        val container = findViewById<LinearLayout>(R.id.container_decisions)
        container.removeAllViews()
        val decisions = db.all("decisions", parentId = reunion.getString("id"))
        if (decisions.isEmpty()) {
            container.addView(simpleLine("Aucune décision enregistrée."))
        }
        decisions.forEach { d ->
            val ligne = "${d.optString("description")} — ${d.optString("statut")}" +
                d.optString("date_echeance").takeIf { it.isNotBlank() }?.let { " (échéance $it)" }.orEmpty()
            container.addView(simpleLine(ligne))
        }
    }

    private fun showAddDecisionDialog() {
        val input = TextInputEditText(this).apply { hint = "Description de la décision" }
        AlertDialog.Builder(this)
            .setTitle("Nouvelle décision")
            .setView(input)
            .setPositiveButton("Ajouter") { _, _ ->
                val description = input.text?.toString()?.trim().orEmpty()
                if (description.isBlank()) return@setPositiveButton
                val decisionId = UUID.randomUUID().toString()
                val payload = JSONObject()
                    .put("id", decisionId)
                    .put("reunion_id", reunion.getString("id"))
                    .put("description", description)
                    .put("statut", "a_faire")
                outbox.enqueue("decision.create", payload)
                db.upsert("decisions", decisionId, reunion.getString("id"), payload, null)
                renderDecisions()
                executor.execute { outbox.flush() }
            }
            .setNegativeButton("Annuler", null)
            .show()
    }

    // --- Participants ---

    private fun renderParticipants() {
        val container = findViewById<LinearLayout>(R.id.container_participants)
        container.removeAllViews()
        val participants = db.all("participants", parentId = reunion.getString("id"))
        if (participants.isEmpty()) {
            container.addView(simpleLine("Aucun participant enregistré."))
        }
        participants.forEach { p ->
            container.addView(simpleLine("${p.optString("nom_affiche")} (${p.optString("type_participant")})"))
        }
    }

    private fun showAddParticipantDialog() {
        val representantes = db.all("representantes")
        if (representantes.isEmpty()) {
            Toast.makeText(this, "Aucune représentante synchronisée pour l'instant.", Toast.LENGTH_SHORT).show()
            return
        }
        val noms = representantes.map { it.optString("nom", "Sans nom") }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Ajouter une représentante")
            .setItems(noms) { _, index ->
                val representant = representantes[index]
                val participantId = UUID.randomUUID().toString()
                val payload = JSONObject()
                    .put("id", participantId)
                    .put("reunion_id", reunion.getString("id"))
                    .put("type_participant", "representant")
                    .put("representant_id", representant.getString("id"))
                outbox.enqueue("participant.create", payload)
                payload.put("nom_affiche", representant.optString("nom"))
                db.upsert("participants", participantId, reunion.getString("id"), payload, null)
                renderParticipants()
                executor.execute { outbox.flush() }
            }
            .show()
    }

    // --- Pièces jointes ---

    private fun renderPieces() {
        val container = findViewById<LinearLayout>(R.id.container_pieces)
        container.removeAllViews()
        val pieces = db.all("pieces_jointes", parentId = reunion.getString("id"))
        if (pieces.isEmpty()) {
            container.addView(simpleLine("Aucune pièce jointe."))
        }
        pieces.forEach { p ->
            container.addView(simpleLine("${p.optString("type_piece")} — ${p.optString("legende").ifBlank { "sans légende" }}"))
        }
    }

    private fun launchCamera() {
        val file = File.createTempFile("reunion_photo_", ".jpg", cacheDir)
        pendingPhotoFile = file
        val uri: Uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
        takePicture.launch(uri)
    }

    private fun uploadPhoto(file: File) {
        val token = session.token
        if (token == null) {
            Toast.makeText(this, "Connectez-vous pour envoyer une photo.", Toast.LENGTH_SHORT).show()
            return
        }
        Toast.makeText(this, "Envoi de la photo…", Toast.LENGTH_SHORT).show()
        executor.execute {
            val result = HydriaReunionsApi.uploadPieceJointe(
                token = token, reunionId = reunion.getString("id"), file = file, typePiece = "photo", legende = "",
            )
            runOnUiThread {
                if (result.successful) {
                    val piece = result.body.optJSONObject("piece_jointe")
                    if (piece != null) {
                        db.upsert("pieces_jointes", piece.getString("id"), reunion.getString("id"), piece, null)
                    }
                    renderPieces()
                    Toast.makeText(this, "Photo ajoutée.", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(this, "Échec de l'envoi : ${result.error}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun simpleLine(text: String): TextView = TextView(this).apply {
        this.text = text
        setTextColor(getColor(R.color.hydria_text))
        setPadding(0, 8, 0, 8)
        visibility = View.VISIBLE
    }
}
