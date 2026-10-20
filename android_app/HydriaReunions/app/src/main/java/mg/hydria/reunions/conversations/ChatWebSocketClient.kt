package mg.hydria.reunions.conversations

import mg.hydria.reunions.HydriaReunionsApi
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Client WebSocket pour une conversation (voir apps.messaging.consumers.ChatConsumer
 * cote serveur). Protocole JSON avec un champ 'action' :
 *  - sortant : message.send { contenu, type, message_repondu_id? }, typing, message.read
 *  - entrant : message.new { message }, typing { employe_id, employe_nom }, message.read { employe_id }
 *
 * Authentification par le meme jeton mobile que le reste de l'app, passe en
 * query string (?token=...) — accepte tel quel par ChatConsumer._authenticate().
 *
 * Les callbacks de Listener arrivent sur un thread OkHttp, pas le thread UI :
 * l'appelant (ChatActivity) doit passer par runOnUiThread avant de toucher les vues.
 */
class ChatWebSocketClient(
    private val conversationId: String,
    private val token: String,
    private val listener: Listener,
) {
    interface Listener {
        fun onConnected() {}
        fun onDisconnected() {}
        fun onMessageNew(message: JSONObject)
        fun onTyping(employeId: String, employeNom: String)
        fun onRead(employeId: String)
    }

    private var webSocket: WebSocket? = null

    private val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .pingInterval(20, TimeUnit.SECONDS)
            .build()
    }

    fun connect() {
        val url = "${HydriaReunionsApi.WS_BASE_URL}/ws/messaging/conversations/$conversationId/?token=$token"
        val request = Request.Builder().url(url).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                listener.onConnected()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleIncoming(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, null)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                listener.onDisconnected()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                listener.onDisconnected()
            }
        })
    }

    /** Ferme proprement la connexion. A appeler dans onPause/onDestroy de l'ecran de discussion. */
    fun disconnect() {
        webSocket?.close(1000, "fermeture normale")
        webSocket = null
    }

    fun sendMessage(contenu: String, type: String = "text", messageResponduId: String? = null): Boolean {
        val payload = JSONObject().put("action", "message.send").put("contenu", contenu).put("type", type)
        messageResponduId?.let { payload.put("message_repondu_id", it) }
        return webSocket?.send(payload.toString()) ?: false
    }

    fun sendTyping(): Boolean =
        webSocket?.send(JSONObject().put("action", "typing").toString()) ?: false

    fun sendRead(): Boolean =
        webSocket?.send(JSONObject().put("action", "message.read").toString()) ?: false

    private fun handleIncoming(text: String) {
        val data = try {
            JSONObject(text)
        } catch (_: Exception) {
            return
        }
        when (data.optString("action")) {
            "message.new" -> data.optJSONObject("message")?.let { listener.onMessageNew(it) }
            "typing" -> listener.onTyping(data.optString("employe_id"), data.optString("employe_nom"))
            "message.read" -> listener.onRead(data.optString("employe_id"))
        }
    }
}
