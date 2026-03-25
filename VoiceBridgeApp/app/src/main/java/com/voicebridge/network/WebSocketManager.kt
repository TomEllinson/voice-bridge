package com.voicebridge.network

import android.util.Log
import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import java.net.URI
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

/**
 * WebSocket manager for real-time audio streaming to OpenClaw voice bridge.
 * Enforces Tailscale-only networking (100.x.x.x addresses) for security.
 */
class WebSocketManager(
    private val serverAddress: String,
    private val port: Int = 8765,
    private val listener: WebSocketListener
) {
    companion object {
        private const val TAG = "WebSocketManager"
    }

    private var webSocketClient: WebSocketClient? = null
    private val isConnected = AtomicBoolean(false)
    private val isConnecting = AtomicBoolean(false)

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
            return false
        }

        isConnecting.set(true)

        try {
            val uri = URI("ws://$serverAddress:$port/ws")
            webSocketClient = object : WebSocketClient(uri) {
                override fun onOpen(handshake: ServerHandshake) {
                    Log.d(TAG, "WebSocket connected to $serverAddress:$port")
                    isConnected.set(true)
                    isConnecting.set(false)
                    listener.onConnected()
                }

                override fun onMessage(message: String) {
                    listener.onTextMessage(message)
                }

                override fun onMessage(bytes: ByteBuffer) {
                    listener.onBinaryMessage(bytes)
                }

                override fun onClose(code: Int, reason: String, remote: Boolean) {
                    Log.d(TAG, "WebSocket closed: $reason (code: $code)")
                    isConnected.set(false)
                    isConnecting.set(false)
                    listener.onDisconnected()
                }

                override fun onError(ex: Exception) {
                    Log.e(TAG, "WebSocket error", ex)
                    isConnecting.set(false)
                    listener.onError(ex.message ?: "Unknown error")
                }
            }

            webSocketClient?.connect()
            return true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create WebSocket", e)
            isConnecting.set(false)
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
            webSocketClient?.send(audioData)
            true
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
            webSocketClient?.send(message)
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send message", e)
            false
        }
    }

    /**
     * Disconnect from the server.
     */
    fun disconnect() {
        try {
            webSocketClient?.close()
        } catch (e: Exception) {
            Log.e(TAG, "Error closing WebSocket", e)
        }
        isConnected.set(false)
        isConnecting.set(false)
    }

    fun isConnected(): Boolean = isConnected.get()

    /**
     * Interface for WebSocket events.
     */
    interface WebSocketListener {
        fun onConnected()
        fun onDisconnected()
        fun onTextMessage(message: String)
        fun onBinaryMessage(data: ByteBuffer)
        fun onError(error: String)
    }
}
