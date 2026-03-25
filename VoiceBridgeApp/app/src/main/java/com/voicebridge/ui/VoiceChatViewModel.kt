package com.voicebridge.ui

import android.app.Application
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.voicebridge.service.VoiceBridgeService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/**
 * ViewModel for the voice chat screen.
 * Manages connection to the service and UI state.
 */
class VoiceChatViewModel(application: Application) : AndroidViewModel(application) {

    // Service connection
    private var voiceService: VoiceBridgeService? = null
    private var isBound = false

    // UI State
    private val _uiState = MutableStateFlow(VoiceChatUiState())
    val uiState: StateFlow<VoiceChatUiState> = _uiState

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, service: IBinder?) {
            val binder = service as? VoiceBridgeService.LocalBinder
            voiceService = binder?.getService()
            isBound = true
            observeServiceState()
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            voiceService = null
            isBound = false
        }
    }

    /**
     * Bind to the VoiceBridgeService.
     */
    fun bindService() {
        if (isBound) return

        val intent = Intent(getApplication(), VoiceBridgeService::class.java)
        getApplication<Application>().bindService(
            intent,
            serviceConnection,
            Context.BIND_AUTO_CREATE
        )
    }

    /**
     * Unbind from the service.
     */
    fun unbindService() {
        if (isBound) {
            getApplication<Application>().unbindService(serviceConnection)
            isBound = false
            voiceService = null
        }
    }

    /**
     * Observe service state and update UI.
     */
    private fun observeServiceState() {
        viewModelScope.launch {
            voiceService?.connectionState?.collect { connectionState ->
                _uiState.value = _uiState.value.copy(
                    connectionStatus = when (connectionState) {
                        is VoiceBridgeService.ConnectionState.Connected -> ConnectionStatus.CONNECTED
                        is VoiceBridgeService.ConnectionState.Connecting -> ConnectionStatus.CONNECTING
                        is VoiceBridgeService.ConnectionState.Disconnected -> ConnectionStatus.DISCONNECTED
                        is VoiceBridgeService.ConnectionState.Error -> ConnectionStatus.ERROR
                    },
                    statusMessage = if (connectionState is VoiceBridgeService.ConnectionState.Error)
                        connectionState.message else _uiState.value.statusMessage
                )
            }
        }

        viewModelScope.launch {
            voiceService?.isListening?.collect { isListening ->
                _uiState.value = _uiState.value.copy(isListening = isListening)
            }
        }

        viewModelScope.launch {
            voiceService?.isSpeaking?.collect { isSpeaking ->
                _uiState.value = _uiState.value.copy(isSpeaking = isSpeaking)
            }
        }

        viewModelScope.launch {
            voiceService?.conversationMode?.collect { mode ->
                _uiState.value = _uiState.value.copy(conversationMode = mode)
            }
        }

        viewModelScope.launch {
            voiceService?.transcription?.collect { text ->
                if (text.isNotEmpty()) {
                    _uiState.value = _uiState.value.copy(
                        lastTranscription = text,
                        messages = _uiState.value.messages + Message.User(text)
                    )
                }
            }
        }

        viewModelScope.launch {
            voiceService?.agentResponse?.collect { text ->
                if (text.isNotEmpty()) {
                    _uiState.value = _uiState.value.copy(
                        messages = _uiState.value.messages + Message.Agent(text)
                    )
                }
            }
        }
    }

    /**
     * Set the server address (Tailscale IP).
     */
    fun setServerAddress(address: String) {
        _uiState.value = _uiState.value.copy(serverAddress = address)
    }

    /**
     * Connect to the server.
     */
    fun connect() {
        val address = _uiState.value.serverAddress
        if (address.isBlank()) {
            _uiState.value = _uiState.value.copy(
                statusMessage = "Please enter server address"
            )
            return
        }
        voiceService?.connect(address)
    }

    /**
     * Disconnect from the server.
     */
    fun disconnect() {
        voiceService?.disconnect()
    }

    /**
     * Start push-to-talk recording.
     */
    fun startPushToTalk() {
        voiceService?.startPushToTalk()
    }

    /**
     * Stop push-to-talk recording.
     */
    fun stopPushToTalk() {
        voiceService?.stopPushToTalk()
    }

    /**
     * Toggle conversation mode.
     */
    fun toggleMode() {
        voiceService?.toggleConversationMode()
    }

    /**
     * Interrupt current playback.
     */
    fun interrupt() {
        voiceService?.interruptPlayback()
    }

    override fun onCleared() {
        super.onCleared()
        unbindService()
    }
}

/**
 * UI State data class.
 */
data class VoiceChatUiState(
    val connectionStatus: ConnectionStatus = ConnectionStatus.DISCONNECTED,
    val isListening: Boolean = false,
    val isSpeaking: Boolean = false,
    val conversationMode: VoiceBridgeService.ConversationMode = VoiceBridgeService.ConversationMode.PUSH_TO_TALK,
    val serverAddress: String = "",
    val lastTranscription: String = "",
    val statusMessage: String = "Enter Tailscale IP (100.x.x.x)",
    val messages: List<Message> = emptyList()
)

/**
 * Connection status enum.
 */
enum class ConnectionStatus {
    DISCONNECTED,
    CONNECTING,
    CONNECTED,
    ERROR
}

/**
 * Message types for conversation history.
 */
sealed class Message(val text: String) {
    class User(text: String) : Message(text)
    class Agent(text: String) : Message(text)
}
