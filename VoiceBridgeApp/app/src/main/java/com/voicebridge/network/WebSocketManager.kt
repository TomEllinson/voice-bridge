package com.voicebridge.network

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.*
import okio.ByteString
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * WebSocket manager for real-time audio streaming to OpenClaw voice bridge.
 * Uses OkHttp for WebSocket connections.
 * Enforces Tailscale-only networking (100.x.x.x addresses) for security.
 */
class WebSocketManager(
    private val serverAddress: String,
    private val port: Int = 8765,
    private val listener: WebSocketListener
) {
    companion object {
        private const val TAG = "WebSocketManager"
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
    private val isConnecting = AtomicBoolean(false)

    private val _connectionState = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionState: StateFlow<ConnectionState> = _connectionState

    enum class ConnectionState {
        DISCONNECTED,
        CONNECTING,
        CONNECTED,
        ERROR
    }

    /**
     * Validates that the server address is in the Tailscale range (100.x.x.x).
     * This is a security requirement - we only connect through Tailscale mesh.
     */
    private fun isTailscaleAddress(address: String): Boolean {
        return address.startsWith("100.")
    }

    /**
     * Connect to the WebSocket server.
     * Returns true if connection was initiated, false if already connected or connecting.
     */
    fun connect(): Boolean {
        if (isConnected.get() || isConnecting.get()) {
            Log.d(TAG, "Already connected or connecting")
            return false
        }

        // Security check - only allow Tailscale addresses
        if (!isTailscaleAddress(serverAddress)) {
            Log.e(TAG, "Security violation: Attempted to connect to non-Tailscale address: $serverAddress")
            listener.onError("Only Tailscale addresses (100.x.x.x) are allowed")
            _connectionState.value = ConnectionState.ERROR
            return false
        }

        isConnecting.set(true)
        _connectionState.value = ConnectionState.CONNECTING

        try {
            val request = Request.Builder()
                .url("ws://$serverAddress:$port/ws")
                .build()

            webSocket = client.newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    Log.d(TAG, "WebSocket connected to $serverAddress:$port")
                    isConnected.set(true)
                    isConnecting.set(false)
                    _connectionState.value = ConnectionState.CONNECTED
                    listener.onConnected()
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    listener.onTextMessage(text)
                }

                override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                    listener.onBinaryMessage(bytes.toByteArray())
                }

                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    Log.d(TAG, "WebSocket closing: $reason (code: $code)")
                    webSocket.close(code, reason)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    Log.d(TAG, "WebSocket closed: $reason (code: $code)")
                    isConnected.set(false)
                    isConnecting.set(false)
                    _connectionState.value = ConnectionState.DISCONNECTED
                    listener.onDisconnected()
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Log.e(TAG, "WebSocket error", t)
                    isConnected.set(false)
                    isConnecting.set(false)
                    _connectionState.value = ConnectionState.ERROR
                    listener.onError(t.message ?: "Unknown error")
                }
            })

            return true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create WebSocket", e)
            isConnecting.set(false)
            _connectionState.value = ConnectionState.ERROR
            listener.onError(e.message ?: "Failed to connect")
            return false
        }
    }

    /**
     * Send audio data to the server.
     */
    fun sendAudio(audioData: ByteArray): Boolean {
        if (!isConnected.get()) {
            Log.w(TAG, "Cannot send audio - not connected")
            return false
        }

        return try {
            webSocket?.send(ByteString.of(*audioData)) ?: false
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send audio", e)
            false
        }
    }

    /**
     * Send a text control message to the server.
     */
    fun sendMessage(message: String): Boolean {
        if (!isConnected.get()) {
            Log.w(TAG, "Cannot send message - not connected")
            return false
        }

        return try {
            webSocket?.send(message) ?: false
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send message", e)
            false
        }
    }

    /**
     * Send interrupt signal to the server.
     */
    fun sendInterrupt(): Boolean {
        return sendMessage("INTERRUPT")
    }

    /**
     * Disconnect from the server.
     */
    fun disconnect() {
        try {
            webSocket?.close(NORMAL_CLOSURE_STATUS, "Client disconnecting")
        } catch (e: Exception) {
            Log.e(TAG, "Error closing WebSocket", e)
        }
        isConnected.set(false)
        isConnecting.set(false)
        _connectionState.value = ConnectionState.DISCONNECTED
    }

    fun isConnected(): Boolean = isConnected.get()

    /**
     * Release resources.
     */
    fun release() {
        disconnect()
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
    }

    /**
     * Interface for WebSocket events.
     */
    interface WebSocketListener {
        fun onConnected()
        fun onDisconnected()
        fun onTextMessage(message: String)
        fun onBinaryMessage(data: ByteArray)
        fun onError(error: String)
    }
}
