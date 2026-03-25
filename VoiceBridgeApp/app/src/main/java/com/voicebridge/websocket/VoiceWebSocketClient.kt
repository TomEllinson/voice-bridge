package com.voicebridge.websocket

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import java.net.URI
import java.nio.ByteBuffer

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

class VoiceWebSocketClient(
    private val serverUrl: String,
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
) {
    private var webSocket: WebSocketClient? = null
    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val connectionState: StateFlow<ConnectionState> = _connectionState

    private val _incomingMessages = MutableStateFlow<VoiceMessage?>(null)
    val incomingMessages: StateFlow<VoiceMessage?> = _incomingMessages

    private var reconnectAttempts = 0
    private val maxReconnectAttempts = 5

    fun connect() {
        if (_connectionState.value == ConnectionState.Connecting ||
            _connectionState.value == ConnectionState.Connected) {
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
            val uri = URI(serverUrl)

            webSocket = object : WebSocketClient(uri) {
                override fun onOpen(handshakedata: ServerHandshake?) {
                    Log.d(TAG, "WebSocket connected")
                    _connectionState.value = ConnectionState.Connected
                    reconnectAttempts = 0
                }

                override fun onMessage(message: String?) {
                    message?.let {
                        Log.d(TAG, "Received text: ${it.take(100)}")
                        _incomingMessages.value = VoiceMessage.TextMessage(it)
                    }
                }

                override fun onMessage(bytes: ByteBuffer?) {
                    bytes?.let {
                        val data = ByteArray(it.remaining())
                        it.get(data)
                        _incomingMessages.value = VoiceMessage.AudioData(data)
                    }
                }

                override fun onClose(code: Int, reason: String?, remote: Boolean) {
                    Log.d(TAG, "WebSocket closed: $reason")
                    _connectionState.value = ConnectionState.Disconnected
                    attemptReconnect()
                }

                override fun onError(ex: Exception?) {
                    Log.e(TAG, "WebSocket error", ex)
                    _connectionState.value = ConnectionState.Error(ex?.message ?: "Unknown error")
                }
            }

            webSocket?.connect()
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
            webSocket?.send(audioData)
        }
    }

    fun sendMessage(message: String) {
        if (_connectionState.value == ConnectionState.Connected) {
            webSocket?.send(message)
        }
    }

    fun startStreaming() {
        sendMessage("""{"type": "start_streaming"}""")
    }

    fun stopStreaming() {
        sendMessage("""{"type": "stop_streaming"}""")
    }

    fun disconnect() {
        scope.cancel()
        webSocket?.close()
        webSocket = null
        _connectionState.value = ConnectionState.Disconnected
    }

    companion object {
        private const val TAG = "VoiceWebSocket"
        private const val RECONNECT_DELAY = 2000L // 2 seconds
    }
}
