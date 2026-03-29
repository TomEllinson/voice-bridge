package com.voicebridge.viewmodel

import android.app.Application
import android.content.Context
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.voicebridge.audio.AudioPlayer
import com.voicebridge.audio.AudioRecorder
import com.voicebridge.audio.VoiceActivityDetector
import com.voicebridge.network.WebSocketManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.nio.ByteBuffer

/**
 * ViewModel for Voice Chat screen.
 * Manages audio recording, WebSocket connection, VAD, and UI state.
 */
class VoiceChatViewModel(application: Application) : AndroidViewModel(application) {

    companion object {
        private const val TAG = "VoiceChatViewModel"
    }

    // Configuration
    private val prefs = application.getSharedPreferences("voice_bridge", Context.MODE_PRIVATE)
    private val serverAddress: String
        get() = prefs.getString("server_address", "100.64.1.1") ?: "100.64.1.1"

    // Audio components
    private val audioRecorder = AudioRecorder(application)
    private val audioPlayer = AudioPlayer()
    private val vad = VoiceActivityDetector()

    // WebSocket
    private var webSocketManager: WebSocketManager? = null

    // State
    data class VoiceChatState(
        val isConnected: Boolean = false,
        val isConnecting: Boolean = false,
        val isRecording: Boolean = false,
        val isPlaying: Boolean = false,
        val listeningMode: ListeningMode = ListeningMode.PUSH_TO_TALK,
        val isSpeaking: Boolean = false,  // User is speaking (VAD)
        val agentSpeaking: Boolean = false,  // Agent is speaking
        val canInterrupt: Boolean = false,
        val statusMessage: String = "Not connected",
        val errorMessage: String? = null
    )

    enum class ListeningMode {
        PUSH_TO_TALK,
        ALWAYS_LISTENING
    }

    private val _state = MutableStateFlow(VoiceChatState())
    val state: StateFlow<VoiceChatState> = _state

    // Conversation state
    private var conversationId: String? = null
    private var isUserSpeaking = false

    init {
        audioPlayer.initialize()
        setupAudioCallbacks()
    }

    private fun setupAudioCallbacks() {
        // Audio recorder callback - process VAD and send via WebSocket
        audioRecorder.onAudioData = { audioBytes ->
            processAudioData(audioBytes)
        }

        audioRecorder.onError = { error ->
            _state.value = _state.value.copy(errorMessage = error)
        }

        // Audio player callbacks
        audioPlayer.onPlaybackStarted = {
            viewModelScope.launch {
                _state.value = _state.value.copy(
                    isPlaying = true,
                    agentSpeaking = true,
                    canInterrupt = true
                )
            }
        }

        audioPlayer.onPlaybackCompleted = {
            viewModelScope.launch {
                _state.value = _state.value.copy(
                    isPlaying = false,
                    agentSpeaking = false,
                    canInterrupt = false
                )
            }
        }

        audioPlayer.onPlaybackInterrupted = {
            viewModelScope.launch {
                _state.value = _state.value.copy(
                    isPlaying = false,
                    agentSpeaking = false,
                    canInterrupt = false
                )
            }
        }
    }

    /**
     * Connect to the WebSocket server.
     */
    fun connect() {
        if (_state.value.isConnected || _state.value.isConnecting) return

        _state.value = _state.value.copy(isConnecting = true, statusMessage = "Connecting...")

        webSocketManager = WebSocketManager(
            serverAddress = serverAddress,
            listener = object : WebSocketManager.WebSocketEventListener {
                override fun onConnected() {
                    viewModelScope.launch {
                        _state.value = _state.value.copy(
                            isConnected = true,
                            isConnecting = false,
                            statusMessage = "Connected to $serverAddress"
                        )
                    }
                }

                override fun onDisconnected() {
                    viewModelScope.launch {
                        _state.value = _state.value.copy(
                            isConnected = false,
                            isConnecting = false,
                            statusMessage = "Disconnected"
                        )
                    }
                }

                override fun onTextMessage(message: String) {
                    handleTextMessage(message)
                }

                override fun onBinaryMessage(data: ByteArray) {
                    // Incoming audio from agent
                    val buffer = ByteBuffer.wrap(data)
                    audioPlayer.queueAudio(buffer)
                }

                override fun onError(error: String) {
                    viewModelScope.launch {
                        _state.value = _state.value.copy(
                            isConnected = false,
                            isConnecting = false,
                            errorMessage = error,
                            statusMessage = "Connection error"
                        )
                    }
                }
            }
        )

        webSocketManager?.connect()
        audioPlayer.startPlayback(viewModelScope)
    }

    /**
     * Disconnect from the server.
     */
    fun disconnect() {
        webSocketManager?.disconnect()
        webSocketManager = null
        audioPlayer.stopPlayback()
        _state.value = _state.value.copy(
            isConnected = false,
            statusMessage = "Disconnected"
        )
    }

    /**
     * Start recording (Push to Talk mode).
     */
    fun startRecording() {
        if (!_state.value.isConnected) {
            _state.value = _state.value.copy(errorMessage = "Not connected to server")
            return
        }

        if (audioRecorder.isAvailable()) {
            // Interrupt agent if speaking
            if (_state.value.canInterrupt) {
                interruptAgent()
            }

            audioRecorder.startRecording(viewModelScope)
            _state.value = _state.value.copy(
                isRecording = true,
                statusMessage = "Recording..."
            )

            // Send start message
            sendStartMessage()
        } else {
            _state.value = _state.value.copy(errorMessage = "Microphone not available")
        }
    }

    /**
     * Stop recording.
     */
    fun stopRecording() {
        audioRecorder.stopRecording()
        _state.value = _state.value.copy(
            isRecording = false,
            isSpeaking = false,
            statusMessage = "Processing..."
        )

        // Send end message
        sendEndMessage()
    }

    /**
     * Toggle listening mode.
     */
    fun setListeningMode(mode: ListeningMode) {
        _state.value = _state.value.copy(listeningMode = mode)

        if (mode == ListeningMode.ALWAYS_LISTENING) {
            startAlwaysListening()
        } else {
            stopAlwaysListening()
        }
    }

    /**
     * Start always-listening mode with VAD.
     */
    private fun startAlwaysListening() {
        if (!_state.value.isConnected) {
            _state.value = _state.value.copy(errorMessage = "Not connected to server")
            return
        }

        if (audioRecorder.isAvailable()) {
            vad.reset()
            audioRecorder.startRecording(viewModelScope)
            _state.value = _state.value.copy(
                isRecording = true,
                statusMessage = "Always listening..."
            )
            sendStartMessage()
        }
    }

    /**
     * Stop always-listening mode.
     */
    private fun stopAlwaysListening() {
        audioRecorder.stopRecording()
        vad.reset()
        _state.value = _state.value.copy(
            isRecording = false,
            isSpeaking = false,
            statusMessage = "Stopped listening"
        )
        sendEndMessage()
    }

    /**
     * Interrupt agent playback (user barged in).
     */
    fun interruptAgent() {
        Log.d(TAG, "Interrupting agent")
        audioPlayer.interrupt()

        // Send interrupt message to server
        val message = JSONObject().apply {
            put("type", "interrupt")
            put("conversation_id", conversationId)
        }
        webSocketManager?.sendMessage(message.toString())
    }

    /**
     * Process audio data from recorder.
     */
    private fun processAudioData(audioBytes: ByteArray) {
        // Convert to shorts for VAD
        val shorts = audioRecorder.bytesToShorts(audioBytes)

        // Run VAD
        val result = vad.process(shorts)

        // Update speaking state
        if (result.isSpeech != isUserSpeaking) {
            isUserSpeaking = result.isSpeech
            viewModelScope.launch {
                _state.value = _state.value.copy(isSpeaking = isUserSpeaking)
            }
        }

        // Detect speech start/end for interrupt handling
        if (result.isSpeechStart && _state.value.canInterrupt) {
            interruptAgent()
        }

        // Send audio to server
        webSocketManager?.sendAudio(audioBytes)
    }

    /**
     * Handle text messages from server.
     */
    private fun handleTextMessage(message: String) {
        try {
            val json = JSONObject(message)
            val type = json.optString("type")

            when (type) {
                "conversation_started" -> {
                    conversationId = json.optString("conversation_id")
                    Log.d(TAG, "Conversation started: $conversationId")
                }
                "status" -> {
                    val status = json.optString("message")
                    viewModelScope.launch {
                        _state.value = _state.value.copy(statusMessage = status)
                    }
                }
                "error" -> {
                    val error = json.optString("message")
                    viewModelScope.launch {
                        _state.value = _state.value.copy(errorMessage = error)
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse message", e)
        }
    }

    private fun sendStartMessage() {
        val message = JSONObject().apply {
            put("type", "start")
            put("conversation_id", conversationId ?: JSONObject.NULL)
        }
        webSocketManager?.sendMessage(message.toString())
    }

    private fun sendEndMessage() {
        val message = JSONObject().apply {
            put("type", "end")
            put("conversation_id", conversationId ?: JSONObject.NULL)
        }
        webSocketManager?.sendMessage(message.toString())
    }

    /**
     * Clear error message.
     */
    fun clearError() {
        _state.value = _state.value.copy(errorMessage = null)
    }

    /**
     * Update server address.
     */
    fun setServerAddress(address: String) {
        prefs.edit().putString("server_address", address).apply()
    }

    override fun onCleared() {
        super.onCleared()
        disconnect()
        audioRecorder.stopRecording()
        audioPlayer.release()
    }
}
