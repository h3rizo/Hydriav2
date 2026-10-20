package mg.hydria.reunions.conversations

import android.os.Bundle
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import mg.hydria.reunions.HydriaReunionsApi
import mg.hydria.reunions.R
import mg.hydria.reunions.ReunionsDatabase
import mg.hydria.reunions.SessionManager
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.concurrent.Executors

/**
 * Fil de discussion d'une conversation (façon WhatsApp) : bulles de messages
 * + saisie en bas. Le WebSocket (ChatWebSocketClient) est ouvert en
 * onResume/fermé en onPause — la conversation est aussi utilisable en repli
 * REST (HydriaReunionsApi.messageSend) si la connexion temps réel échoue.
 *
 * Note : quand l'envoi passe par le WebSocket, le serveur rediffuse le
 * message a tous les participants connectes au groupe de la conversation —
 * y compris l'expediteur lui-meme (voir apps.messaging.services.diffuser_message) —
 * donc pas d'affichage optimiste ici : le message apparait via onMessageNew(),
 * comme pour n'importe quel autre participant.
 */
class ChatActivity : AppCompatActivity(), ChatWebSocketClient.Listener {
    companion object {
        const val EXTRA_CONVERSATION_ID = "conversation_id"
        const val EXTRA_CONVERSATION_LABEL = "conversation_label"
    }

    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var db: ReunionsDatabase
    private lateinit var session: SessionManager
    private lateinit var conversationId: String
    private lateinit var adapter: MessageAdapter
    private lateinit var recycler: RecyclerView
    private lateinit var inputContenu: EditText
    private lateinit var textStatus: TextView
    private var socket: ChatWebSocketClient? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_chat)

        val id = intent.getStringExtra(EXTRA_CONVERSATION_ID)
        if (id == null) {
            finish()
            return
        }
        conversationId = id
        title = intent.getStringExtra(EXTRA_CONVERSATION_LABEL) ?: getString(R.string.menu_conversations)

        db = ReunionsDatabase(this)
        session = SessionManager(this)

        recycler = findViewById(R.id.recycler_messages)
        inputContenu = findViewById(R.id.input_message)
        textStatus = findViewById(R.id.text_status)

        adapter = MessageAdapter(session.employeId.orEmpty())
        recycler.layoutManager = LinearLayoutManager(this).apply { stackFromEnd = true }
        recycler.adapter = adapter

        findViewById<ImageButton>(R.id.button_send).setOnClickListener { sendCurrentInput() }

        loadFromLocalDb()
        markAsRead()
    }

    override fun onResume() {
        super.onResume()
        val token = session.token ?: return
        socket = ChatWebSocketClient(conversationId, token, this).also { it.connect() }
    }

    override fun onPause() {
        super.onPause()
        socket?.disconnect()
        socket = null
    }

    private fun loadFromLocalDb() {
        val items = db.all("messages", parentId = conversationId).sortedBy { it.optString("date_envoi") }
        adapter.submitList(items)
        if (items.isNotEmpty()) recycler.scrollToPosition(items.size - 1)
    }

    private fun markAsRead() {
        val token = session.token ?: return
        executor.execute { HydriaReunionsApi.messageRead(token, conversationId) }
    }

    private fun sendCurrentInput() {
        val contenu = inputContenu.text?.toString()?.trim().orEmpty()
        if (contenu.isBlank()) return
        inputContenu.setText("")

        val sentViaSocket = socket?.sendMessage(contenu) ?: false
        if (!sentViaSocket) {
            // Pas de connexion WebSocket active : repli REST — dans ce cas la diffusion
            // groupe ne revient pas vers ce meme appareil, donc on affiche nous-memes
            // la reponse du serveur.
            val token = session.token ?: return
            executor.execute {
                val result = HydriaReunionsApi.messageSend(token, conversationId, contenu)
                if (result.successful && result.body.optBoolean("success")) {
                    result.body.optJSONObject("message")?.let { storeAndShow(it) }
                } else {
                    runOnUiThread { Toast.makeText(this, result.error, Toast.LENGTH_SHORT).show() }
                }
            }
        }
    }

    private fun storeAndShow(message: JSONObject) {
        db.upsert("messages", message.getString("id"), conversationId, message, message.optString("date_envoi"))
        runOnUiThread { loadFromLocalDb() }
    }

    // ---- ChatWebSocketClient.Listener — attention : appels hors thread UI ----

    override fun onConnected() {
        runOnUiThread { textStatus.text = "" }
        socket?.sendRead()
    }

    override fun onDisconnected() {
        runOnUiThread { textStatus.text = getString(R.string.chat_offline) }
    }

    override fun onMessageNew(message: JSONObject) {
        if (message.optString("conversation_id") != conversationId) return
        storeAndShow(message)
        socket?.sendRead()
    }

    override fun onTyping(employeId: String, employeNom: String) {
        if (employeId == session.employeId) return
        runOnUiThread { textStatus.text = getString(R.string.chat_typing, employeNom) }
    }

    override fun onRead(employeId: String) {
        // Pas d'accuse de lecture par message affiche pour l'instant (amelioration future).
    }

    // ---- Adapter bulles de discussion ----

    private inner class MessageAdapter(private val moiId: String) :
        RecyclerView.Adapter<MessageAdapter.ViewHolder>() {

        private var items: List<JSONObject> = emptyList()
        private val timeFormat = SimpleDateFormat("HH:mm", Locale.FRANCE)
        private val isoFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.FRANCE)

        inner class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val sender: TextView = view.findViewById(R.id.text_sender)
            val content: TextView = view.findViewById(R.id.text_content)
            val time: TextView = view.findViewById(R.id.text_time)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context).inflate(R.layout.item_message, parent, false)
            return ViewHolder(view)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val message = items[position]
            val isMine = message.optString("expediteur_id") == moiId
            val gravity = if (isMine) Gravity.END else Gravity.START

            holder.content.text = message.optString("contenu")
            holder.content.setBackgroundResource(if (isMine) R.drawable.bg_bulle_moi else R.drawable.bg_bulle_autre)
            (holder.content.layoutParams as LinearLayout.LayoutParams).gravity = gravity

            holder.sender.text = message.optString("expediteur_nom")
            holder.sender.visibility = if (isMine) View.GONE else View.VISIBLE
            (holder.sender.layoutParams as LinearLayout.LayoutParams).gravity = gravity

            holder.time.text = formatTime(message.optString("date_envoi"))
            (holder.time.layoutParams as LinearLayout.LayoutParams).gravity = gravity
        }

        override fun getItemCount(): Int = items.size

        fun submitList(newItems: List<JSONObject>) {
            items = newItems
            notifyDataSetChanged()
        }

        private fun formatTime(iso: String): String {
            if (iso.isBlank()) return ""
            return try {
                val cleaned = iso.substringBefore("+").substringBefore("Z").substringBefore(".")
                isoFormat.parse(cleaned)?.let { timeFormat.format(it) } ?: ""
            } catch (_: Exception) {
                ""
            }
        }
    }
}
