package com.voicebridge.websocket

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.*
import okio.ByteString
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * WebSocket client using OkHttp for real-time audio streaming.
 * Enforces Tailscale-only connections (100.x.x.x).
 */
class WebSocketClient(
    private val serverUrl: String,
    private val onMessage: (ByteArray) -> Unit,
    private val onConnected: () -> Unit = {},
    private val onDisconnected: () -> Unit = {},
    private val onError: (String) -> Unit = {}
) {
    companion object {
        private const val TAG = "WebSocketClient"
        private const val NORMAL_CLOSURE_STATUS = 1000
        private const val PING_INTERVAL_MS = 20000L
    }

    private val client: OkHttpClient = OkHttpClient.Builder()
        .pingInterval(PING_INTERVAL_MS, TimeUnit.MILLISECONDS)
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS) // No timeout for streaming
        .writeTimeout(10, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private val isConnected = AtomicBoolean(false)

    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val connectionState: StateFlow<ConnectionState> = _connectionState

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    enum class ConnectionState {
        Disconnected,
        Connecting,
        Connected,
        Error
    }

    /**
     * Connect to the WebSocket server.
     * Only allows Tailscale IPs (100.x.x.x).
     */
    fun connect() {
        if (isConnected.get()) {
            Log.w(TAG, "Already connected")
            return
        }

        // Validate Tailscale IP range (100.x.x.x)
        if (!isTailscaleIp(serverUrl)) {
            val error = "Only Tailscale IPs (100.x.x.x) are allowed"
            Log.e(TAG, error)
            onError(error)
            _connectionState.value = ConnectionState.Error
            return
        }

        _connectionState.value = ConnectionState.Connecting

        val request = Request.Builder()
            .url(serverUrl)
            .build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.d(TAG, "WebSocket connected to $serverUrl")
                isConnected.set(true)
                _connectionState.value = ConnectionState.Connected
                onConnected()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                Log.d(TAG, "Text message received: $text")
                // Handle text control messages
                handleTextMessage(text)
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                // Handle binary audio data
                onMessage(bytes.toByteArray())
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket closing: $code - $reason")
                webSocket.close(code, reason)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket closed: $code - $reason")
                isConnected.set(false)
                _connectionState.value = ConnectionState.Disconnected
                onDisconnected()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                val error = t.message ?: "WebSocket connection failed"
                Log.e(TAG, "WebSocket error: $error", t)
                isConnected.set(false)
                _connectionState.value = ConnectionState.Error
                onError(error)
            }
        })
    }

    /**
     * Disconnect from the WebSocket server.
     */
    fun disconnect() {
        isConnected.set(false)
        webSocket?.close(NORMAL_CLOSURE_STATUS, "Client disconnecting")
        webSocket = null
        scope.cancel()
        onDisconnected()
        _connectionState.value = ConnectionState.Disconnected
    }

    /**
     * Send audio data to the server.
     */
    fun sendAudio(audioData: ByteArray) {
        if (isConnected.get() && webSocket != null) {
            webSocket?.send(ByteString.of(*audioData))
        }
    }

    /**
     * Send text message to the server.
     */
    fun sendText(text: String) {
        if (isConnected.get() && webSocket != null) {
            webSocket?.send(text)
        }
    }

    /**
     * Send interrupt signal to the server.
     */
    fun sendInterrupt() {
        sendText("INTERRUPT")
    }

    private fun handleTextMessage(message: String) {
        // Text messages are handled by the listener
        // Binary messages are passed to onMessage callback
    }

    private fun isTailscaleIp(url: String): Boolean {
        return try {
            val cleanUrl = url.replace("ws://", "")
                .replace("wss://", "")
                .split("/").first()
                .split(":").first()
            cleanUrl.startsWith("100.")
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Release resources.
     */
    fun release() {
        disconnect()
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
    }
}
