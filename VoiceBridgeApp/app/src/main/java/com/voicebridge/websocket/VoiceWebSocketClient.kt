package com.voicebridge.websocket

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.*
import okio.ByteString
import java.util.concurrent.TimeUnit

sealed class ConnectionState {
    object Disconnected : ConnectionState()
    object Connecting : ConnectionState()
    object Connected : ConnectionState()
    data class Error(val message: String) : ConnectionState()
}

sealed class VoiceMessage {
    data class AudioData(val data: ByteArray) : VoiceMessage()
    data class TextMessage(val text: String) : VoiceMessage()
    object StartStreaming : VoiceMessage()
    object StopStreaming : VoiceMessage()
}

/**
 * Voice WebSocket client using OkHttp for real-time audio streaming.
 * Supports automatic reconnection and Tailscale-only networking.
 */
class VoiceWebSocketClient(
    private val serverUrl: String,
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
) {
    companion object {
        private const val TAG = "VoiceWebSocket"
        private const val RECONNECT_DELAY = 2000L // 2 seconds
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
    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val connectionState: StateFlow<ConnectionState> = _connectionState

    private val _incomingMessages = MutableStateFlow<VoiceMessage?>(null)
    val incomingMessages: StateFlow<VoiceMessage?> = _incomingMessages

    private var reconnectAttempts = 0
    private val maxReconnectAttempts = 5

    /**
     * Validates that the server URL uses a Tailscale address (100.x.x.x).
     */
    private fun isTailscaleUrl(url: String): Boolean {
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

    fun connect() {
        if (_connectionState.value == ConnectionState.Connecting ||
            _connectionState.value == ConnectionState.Connected) {
            return
        }

        // Security check - only allow Tailscale addresses
        if (!isTailscaleUrl(serverUrl)) {
            Log.e(TAG, "Security violation: Only Tailscale addresses (100.x.x.x) are allowed")
            _connectionState.value = ConnectionState.Error("Only Tailscale addresses (100.x.x.x) are allowed")
            return
        }

        _connectionState.value = ConnectionState.Connecting
        reconnectAttempts = 0

        scope.launch {
            connectInternal()
        }
    }

    private suspend fun connectInternal() {
        try {
            val request = Request.Builder()
                .url(serverUrl)
                .build()

            webSocket = client.newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    Log.d(TAG, "WebSocket connected")
                    _connectionState.value = ConnectionState.Connected
                    reconnectAttempts = 0
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    Log.d(TAG, "Received text: ${text.take(100)}")
                    _incomingMessages.value = VoiceMessage.TextMessage(text)
                }

                override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                    _incomingMessages.value = VoiceMessage.AudioData(bytes.toByteArray())
                }

                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    Log.d(TAG, "WebSocket closing: $reason")
                    webSocket.close(code, reason)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    Log.d(TAG, "WebSocket closed: $reason")
                    _connectionState.value = ConnectionState.Disconnected
                    attemptReconnect()
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Log.e(TAG, "WebSocket error", t)
                    _connectionState.value = ConnectionState.Error(t.message ?: "Unknown error")
                    attemptReconnect()
                }
            })
        } catch (e: Exception) {
            Log.e(TAG, "Connection failed", e)
            _connectionState.value = ConnectionState.Error(e.message ?: "Connection failed")
            attemptReconnect()
        }
    }

    private fun attemptReconnect() {
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++
            scope.launch {
                delay(RECONNECT_DELAY * reconnectAttempts)
                connectInternal()
            }
        }
    }

    fun sendAudio(audioData: ByteArray) {
        if (_connectionState.value == ConnectionState.Connected) {
            webSocket?.send(ByteString.of(*audioData))
        }
    }

    fun sendMessage(message: String) {
        if (_connectionState.value == ConnectionState.Connected) {
            webSocket?.send(message)
        }
    }

    fun sendInterrupt() {
        sendMessage("INTERRUPT")
    }

    fun startStreaming() {
        sendMessage("""{"type": "start_streaming"}""")
    }

    fun stopStreaming() {
        sendMessage("""{"type": "stop_streaming"}""")
    }

    fun disconnect() {
        scope.cancel()
        webSocket?.close(NORMAL_CLOSURE_STATUS, "Client disconnecting")
        webSocket = null
        _connectionState.value = ConnectionState.Disconnected
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
    }
}
