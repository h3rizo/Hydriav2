package mg.hydria.reunions.conversations

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.floatingactionbutton.FloatingActionButton
import mg.hydria.reunions.HydriaReunionsApi
import mg.hydria.reunions.R
import mg.hydria.reunions.ReunionsDatabase
import mg.hydria.reunions.SessionManager
import mg.hydria.reunions.SyncManager
import mg.hydria.reunions.ui.SimpleListAdapter
import org.json.JSONObject
import java.util.concurrent.Executors

/**
 * Liste des conversations (façon liste de discussions WhatsApp). Les échanges
 * temps réel se passent dans ChatActivity (WebSocket) ; cet écran liste les
 * conversations déjà synchronisées et permet d'en démarrer une nouvelle
 * depuis l'annuaire du personnel (employes_annuaire, renvoyé par
 * messaging/bootstrap — voir SyncManager.applyMessagingBootstrap).
 */
class ConversationsActivity : AppCompatActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var db: ReunionsDatabase
    private lateinit var sync: SyncManager
    private lateinit var session: SessionManager
    private lateinit var adapter: SimpleListAdapter<JSONObject>
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var textEmpty: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_list)
        title = getString(R.string.menu_conversations)

        db = ReunionsDatabase(this)
        sync = SyncManager(db)
        session = SessionManager(this)
        swipeRefresh = findViewById(R.id.swipe_refresh)
        textEmpty = findViewById(R.id.text_empty)

        adapter = SimpleListAdapter(
            items = emptyList(),
            title = { conv -> displayName(conv) },
            subtitle = { conv -> conversationSubtitle(conv) },
            onClick = { conv -> openChat(conv.getString("id"), displayName(conv)) },
        )
        findViewById<RecyclerView>(R.id.recycler_view).apply {
            layoutManager = LinearLayoutManager(this@ConversationsActivity)
            adapter = this@ConversationsActivity.adapter
        }

        findViewById<FloatingActionButton>(R.id.fab_add).apply {
            visibility = View.VISIBLE
            setOnClickListener { showNewConversationDialog() }
        }

        swipeRefresh.setOnRefreshListener { refreshFromServer() }
        loadFromLocalDb()
    }

    override fun onResume() {
        super.onResume()
        loadFromLocalDb()
    }

    private fun displayName(conv: JSONObject): String =
        conv.optString("nom_affiche").ifBlank { conv.optString("nom_groupe") }.ifBlank { "Conversation" }

    private fun conversationSubtitle(conv: JSONObject): String {
        val dernier = conv.optJSONObject("dernier_message")
        val apercu = dernier?.optString("contenu")?.take(60)?.ifBlank { null } ?: "Aucun message"
        val nonLus = conv.optInt("messages_non_lus", 0)
        return if (nonLus > 0) "$apercu · $nonLus non lu(s)" else apercu
    }

    private fun openChat(conversationId: String, label: String) {
        startActivity(
            Intent(this, ChatActivity::class.java)
                .putExtra(ChatActivity.EXTRA_CONVERSATION_ID, conversationId)
                .putExtra(ChatActivity.EXTRA_CONVERSATION_LABEL, label),
        )
    }

    private fun loadFromLocalDb() {
        val items = db.all("conversations").sortedByDescending { it.optString("derniere_activite") }
        adapter.submitList(items)
        textEmpty.visibility = if (items.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun refreshFromServer() {
        val token = session.token
        if (token == null) {
            swipeRefresh.isRefreshing = false
            return
        }
        executor.execute {
            val result = HydriaReunionsApi.messagingBootstrap(token)
            if (result.successful) {
                sync.applyMessagingBootstrap(result.body.getJSONObject("payload"))
            }
            runOnUiThread {
                swipeRefresh.isRefreshing = false
                loadFromLocalDb()
            }
        }
    }

    private fun showNewConversationDialog() {
        val moi = session.employeId ?: sync.currentEmployeId()
        val employes = sync.employesAnnuaire().filter { it.optString("id") != moi }
        if (employes.isEmpty()) {
            Toast.makeText(this, "Annuaire vide — synchronisez d'abord (glisser vers le bas).", Toast.LENGTH_SHORT).show()
            return
        }
        val noms = employes.map { it.optString("nom") }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Nouvelle conversation")
            .setItems(noms) { _, which ->
                val employe = employes[which]
                startDirectConversation(employe.optString("id"), employe.optString("nom"))
            }
            .setNegativeButton("Annuler", null)
            .show()
    }

    private fun startDirectConversation(employeId: String, employeNom: String) {
        val token = session.token ?: return
        executor.execute {
            val result = HydriaReunionsApi.conversationCreate(token, "direct", listOf(employeId))
            if (result.successful && result.body.optBoolean("success")) {
                val conversationId = result.body.optString("conversation_id")
                val bootstrap = HydriaReunionsApi.messagingBootstrap(token)
                if (bootstrap.successful) sync.applyMessagingBootstrap(bootstrap.body.getJSONObject("payload"))
                runOnUiThread {
                    loadFromLocalDb()
                    openChat(conversationId, employeNom)
                }
            } else {
                runOnUiThread { Toast.makeText(this, result.error, Toast.LENGTH_SHORT).show() }
            }
        }
    }
}
