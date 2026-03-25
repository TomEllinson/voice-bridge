package com.voicebridge.websocket

import android.util.Log
import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import java.net.URI
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

class WebSocketClient(
    private val url: String,
    private val onMessage: (ByteArray) -> Unit,
    private val onConnected: () -> Unit = {},
    private val onDisconnected: () -> Unit = {},
    private val onError: (String) -> Unit = {}
) {
    companion object {
        private const val TAG = "WebSocketClient"
    }

    private var webSocket: WebSocketClientImpl? = null
    private var isConnected = AtomicBoolean(false)

    fun connect() {
        if (isConnected.get()) {
            Log.w(TAG, "Already connected")
            return
        }

        try {
            val uri = URI(url)
            // Validate Tailscale IP range (100.x.x.x)
            val host = uri.host
            if (!host.startsWith("100.")) {
                onError("Only Tailscale IPs (100.x.x.x) are allowed")
                return
            }

            webSocket = WebSocketClientImpl(uri)
            webSocket?.connect()
        } catch (e: Exception) {
            Log.e(TAG, "Connection error: ${e.message}")
            onError(e.message ?: "Unknown error")
        }
    }

    fun disconnect() {
        isConnected.set(false)
        webSocket?.close()
        webSocket = null
        onDisconnected()
    }

    fun sendAudio(audioData: ByteArray) {
        if (isConnected.get() && webSocket?.isOpen == true) {
            webSocket?.send(audioData)
        }
    }

    fun sendText(text: String) {
        if (isConnected.get() && webSocket?.isOpen == true) {
            webSocket?.send(text)
        }
    }

    private inner class WebSocketClientImpl(uri: URI) : WebSocketClient(uri) {
        override fun onOpen(handshakedata: ServerHandshake?) {
            Log.d(TAG, "WebSocket connected to $url")
            isConnected.set(true)
            onConnected()
        }

        override fun onMessage(message: String?) {
            Log.d(TAG, "Text message received: $message")
        }

        override fun onMessage(bytes: ByteBuffer?) {
            bytes?.let {
                val data = ByteArray(it.remaining())
                it.get(data)
                onMessage(data)
            }
        }

        override fun onClose(code: Int, reason: String?, remote: Boolean) {
            Log.d(TAG, "WebSocket closed: $reason")
            isConnected.set(false)
            onDisconnected()
        }

        override fun onError(ex: Exception?) {
            Log.e(TAG, "WebSocket error: ${ex?.message}")
            isConnected.set(false)
            onError(ex?.message ?: "WebSocket error")
        }
    }
}
