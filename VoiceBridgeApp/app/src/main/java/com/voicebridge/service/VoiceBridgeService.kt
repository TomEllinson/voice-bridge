package com.voicebridge.service

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.voicebridge.MainActivity
import com.voicebridge.R
import com.voicebridge.audio.VoiceActivityDetector
import com.voicebridge.audio.BluetoothAudioManager
import com.voicebridge.network.WebSocketManager
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Voice Bridge Service - Background service for real-time voice chat.
 *
 * Features:
 * - Real-time audio streaming via WebSocket (Tailscale-only)
 * - Voice Activity Detection (VAD)
 * - Multiple listening modes (Always-listening, Voice-activated, Push-to-talk)
 * - Interruption handling for natural conversation flow
 * - Foreground service with notification
 */
class VoiceBridgeService : Service() {

    companion object {
        private const val TAG = "VoiceBridgeService"
        private const val SAMPLE_RATE = 16000
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
        private const val BUFFER_SIZE = 1024 * 4
        private const val NOTIFICATION_ID = 1
        private const val CHANNEL_ID = "voice_bridge_service"
        const val ACTION_STOP = "STOP_SERVICE"
    }

    // Service binder for activity communication
    inner class LocalBinder : Binder() {
        fun getService(): VoiceBridgeService = this@VoiceBridgeService
    }

    private val binder = LocalBinder()

    // Coroutine scope for background operations
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    // WebSocket connection
    private var webSocketManager: WebSocketManager? = null

    // Bluetooth audio management
    private lateinit var bluetoothAudioManager: BluetoothAudioManager

    // Audio components
    private var audioRecord: AudioRecord? = null
    private var mediaPlayer: MediaPlayer? = null
    private val isRecording = AtomicBoolean(false)
    private var isPlaying = AtomicBoolean(false)

    // Voice Activity Detection
    private var vad: VoiceActivityDetector? = null
    private var currentMode: RecordingMode = RecordingMode.ALWAYS_LISTENING

    // State callbacks for UI (legacy support)
    var onStatusUpdate: ((String) -> Unit)? = null
    var onConnectionStateChange: ((Boolean) -> Unit)? = null

    // StateFlows for ViewModel
    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val connectionState: StateFlow<ConnectionState> = _connectionState

    private val _isListening = MutableStateFlow(false)
    val isListening: StateFlow<Boolean> = _isListening

    private val _isSpeaking = MutableStateFlow(false)
    val isSpeaking: StateFlow<Boolean> = _isSpeaking

    private val _conversationMode = MutableStateFlow(ConversationMode.PUSH_TO_TALK)
    val conversationMode: StateFlow<ConversationMode> = _conversationMode

    private val _transcription = MutableStateFlow("")
    val transcription: StateFlow<String> = _transcription

    private val _agentResponse = MutableStateFlow("")
    val agentResponse: StateFlow<String> = _agentResponse

    // Reconnection
    private var reconnectJob: Job? = null
    private var serverAddress: String = ""
    private var serverPort: Int = 8765

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "Service created")
        initializeVAD()
        initializeBluetooth()
    }

    private fun initializeBluetooth() {
        bluetoothAudioManager = BluetoothAudioManager(this)
        bluetoothAudioManager.initialize()

        // Monitor Bluetooth state
        serviceScope.launch {
            bluetoothAudioManager.isBluetoothConnected.collect { connected ->
                if (connected) {
                    updateStatus("Bluetooth headset connected")
                } else {
                    updateStatus("Bluetooth headset disconnected")
                }
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }

        startForeground()
        return START_STICKY
    }

    private fun initializeVAD() {
        vad = VoiceActivityDetector(
            sampleRate = SAMPLE_RATE,
            energyThreshold = 20.0f,  // Lowered from 40.0f for better sensitivity
            minSpeechFrames = 3,       // Lowered from 5
            silenceFrames = 20         // Increased from 15 to avoid cutting off
        )
    }

    private fun startForeground() {
        val notification = createNotification("Voice Bridge - Ready")

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun createNotification(contentText: String): Notification {
        val notificationIntent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, notificationIntent, PendingIntent.FLAG_IMMUTABLE
        )

        val stopIntent = Intent(this, VoiceBridgeService::class.java).apply {
            action = ACTION_STOP
        }
        val stopPendingIntent = PendingIntent.getService(
            this, 0, stopIntent, PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Voice Bridge")
            .setContentText(contentText)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pendingIntent)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Disconnect", stopPendingIntent)
            .setOngoing(true)
            .build()
    }

    fun connectToServer(serverIp: String, port: Int = 8765) {
        // Security: Only allow Tailscale IPs
        if (!isTailscaleIp(serverIp)) {
            updateStatus("Error: Only Tailscale IPs (100.x.x.x) allowed")
            _connectionState.value = ConnectionState.Error("Only Tailscale IPs allowed")
            return
        }

        serverAddress = serverIp
        serverPort = port
        _connectionState.value = ConnectionState.Connecting

        serviceScope.launch {
            try {
                webSocketManager?.disconnect()

                webSocketManager = WebSocketManager(
                    serverAddress = serverIp,
                    port = port,
                    listener = object : WebSocketManager.WebSocketEventListener {
                        override fun onConnected() {
                            Log.d(TAG, "WebSocket connected")
                            updateStatus("Connected to $serverIp")
                            onConnectionStateChange?.invoke(true)
                            _connectionState.value = ConnectionState.Connected
                            updateNotification("Connected - Listening...")

                            // Start recording if in always-listening mode
                            if (currentMode == RecordingMode.ALWAYS_LISTENING) {
                                startRecording(currentMode)
                            }
                        }

                        override fun onDisconnected() {
                            Log.d(TAG, "WebSocket disconnected")
                            onConnectionStateChange?.invoke(false)
                            _connectionState.value = ConnectionState.Disconnected
                            updateStatus("Disconnected")
                            updateNotification("Disconnected")
                            stopRecording()
                        }

                        override fun onTextMessage(message: String) {
                            handleServerMessage(message)
                        }

                        override fun onBinaryMessage(data: ByteArray) {
                            playAudioResponse(data)
                        }

                        override fun onError(error: String) {
                            Log.e(TAG, "WebSocket error: $error")
                            updateStatus("Error: $error")
                            onConnectionStateChange?.invoke(false)
                            _connectionState.value = ConnectionState.Error(error)
                        }
                    }
                )

                webSocketManager?.connect()
            } catch (e: Exception) {
                Log.e(TAG, "Connection failed", e)
                updateStatus("Connection failed: ${e.message}")
                onConnectionStateChange?.invoke(false)
                _connectionState.value = ConnectionState.Error(e.message ?: "Connection failed")
            }
        }
    }

    fun disconnect() {
        reconnectJob?.cancel()
        serviceScope.launch {
            stopRecording()
            webSocketManager?.disconnect()
            webSocketManager = null
            updateStatus("Disconnected")
            onConnectionStateChange?.invoke(false)
        }
    }

    fun startRecording(mode: RecordingMode = RecordingMode.ALWAYS_LISTENING) {
        if (isRecording.get()) return

        currentMode = mode
        _isListening.value = true
        _conversationMode.value = when(mode) {
            RecordingMode.PUSH_TO_TALK -> ConversationMode.PUSH_TO_TALK
            RecordingMode.VOICE_ACTIVATED -> ConversationMode.VOICE_ACTIVATED
            RecordingMode.ALWAYS_LISTENING -> ConversationMode.ALWAYS_LISTENING
        }
        _conversationMode.value = when(mode) {
            RecordingMode.PUSH_TO_TALK -> ConversationMode.PUSH_TO_TALK
            RecordingMode.VOICE_ACTIVATED -> ConversationMode.VOICE_ACTIVATED
            RecordingMode.ALWAYS_LISTENING -> ConversationMode.ALWAYS_LISTENING
        }

        // Send start_listening control message to server
        val sent = webSocketManager?.sendMessage("""{"type": "start_listening"}""")
        Log.d(TAG, "Sent start_listening message: $sent")

        serviceScope.launch(Dispatchers.IO) {
            try {
                // Start Bluetooth SCO audio if headset is connected
                if (::bluetoothAudioManager.isInitialized) {
                    bluetoothAudioManager.startScoAudio()
                }

                audioRecord = AudioRecord(
                    bluetoothAudioManager.getAudioSource(),
                    SAMPLE_RATE,
                    CHANNEL_CONFIG,
                    AUDIO_FORMAT,
                    BUFFER_SIZE
                )

                if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                    Log.e(TAG, "AudioRecord initialization failed")
                    updateStatus("Microphone initialization failed")
                    return@launch
                }

                isRecording.set(true)
                _isListening.value = true
                audioRecord?.startRecording()
                updateStatus("Recording started (${mode.name})")
                updateNotification("Listening...")

                val buffer = ShortArray(BUFFER_SIZE)

                while (isRecording.get() && isActive) {
                    val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0

                    if (read > 0) {
                        val audioData = buffer.copyOf(read)

                        when (mode) {
                            RecordingMode.VOICE_ACTIVATED -> {
                                // Apply VAD
                                val result = vad?.process(audioData)
                                if (result?.isSpeech == true) {
                                    sendAudioData(audioData)
                                    if (result.isSpeechStart) {
                                        updateStatus("Speech detected...")
                                    }
                                }
                            }
                            RecordingMode.ALWAYS_LISTENING,
                            RecordingMode.PUSH_TO_TALK -> {
                                // Send all audio
                                sendAudioData(audioData)
                            }
                        }
                    }

                    yield() // Allow coroutine cancellation
                }
            } catch (e: Exception) {
                Log.e(TAG, "Recording error", e)
                updateStatus("Recording error: ${e.message}")
                isRecording.set(false)
            }
        }
    }

    fun stopRecording() {
        isRecording.set(false)
        _isListening.value = false
        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping recording", e)
        }
        audioRecord = null

        // Stop Bluetooth SCO audio
        if (::bluetoothAudioManager.isInitialized) {
            bluetoothAudioManager.stopScoAudio()
        }

        updateStatus("Recording stopped")
        updateNotification("Connected - Idle")
    }

    fun setListeningMode(mode: RecordingMode) {
        currentMode = mode
        if (isRecording.get()) {
            stopRecording()
            startRecording(mode)
        }
    }

    private fun sendAudioData(shortData: ShortArray) {
        // Convert ShortArray to ByteArray for transmission
        val byteData = ByteArray(shortData.size * 2)
        for (i in shortData.indices) {
            byteData[i * 2] = (shortData[i].toInt() and 0xFF).toByte()
            byteData[i * 2 + 1] = ((shortData[i].toInt() shr 8) and 0xFF).toByte()
        }

        val sent = webSocketManager?.sendAudio(byteData)
        if (sent == true) {
            Log.v(TAG, "Sent audio chunk: ${byteData.size} bytes")
        } else {
            Log.w(TAG, "Failed to send audio chunk")
        }
    }

    private fun handleServerMessage(message: String) {
        when {
            message.startsWith("TEXT:") -> {
                val text = message.substring(5)
                updateStatus("Heard: $text")
            }
            message.startsWith("RESPONSE:") -> {
                val response = message.substring(9)
                updateStatus("Response: $response")
            }
            message == "INTERRUPT" -> {
                // Server detected interruption - stop playing audio
                handleInterruption()
            }
            message == "START_OF_RESPONSE" -> {
                // Server is about to send audio
                isPlaying.set(true)
                updateStatus("Receiving response...")
            }
            message == "END_OF_RESPONSE" -> {
                isPlaying.set(false)
                updateStatus("Response complete")
            }
        }
    }

    private fun handleInterruption() {
        if (isPlaying.get()) {
            serviceScope.launch(Dispatchers.Main) {
                mediaPlayer?.stop()
                mediaPlayer?.release()
                mediaPlayer = null
                isPlaying.set(false)
                updateStatus("Interrupted by user")
            }
        }
    }

    private fun playAudioResponse(audioData: ByteArray) {
        serviceScope.launch(Dispatchers.Main) {
            try {
                isPlaying.set(true)
                updateStatus("Playing response...")

                // Stop any current playback
                mediaPlayer?.stop()
                mediaPlayer?.release()

                // Save audio to temp file and play
                val tempFile = File(cacheDir, "response_${System.currentTimeMillis()}.wav")
                FileOutputStream(tempFile).use { it.write(audioData) }

                mediaPlayer = MediaPlayer().apply {
                    setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_MEDIA)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                            .build()
                    )
                    setDataSource(tempFile.absolutePath)
                    prepare()
                    start()
                    setOnCompletionListener {
                        this@VoiceBridgeService.isPlaying.set(false)
                        tempFile.delete()
                        updateStatus("Response complete")
                    }
                    setOnErrorListener { _, what, extra ->
                        Log.e(TAG, "MediaPlayer error: $what, $extra")
                        this@VoiceBridgeService.isPlaying.set(false)
                        tempFile.delete()
                        true
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Playback error", e)
                isPlaying.set(false)
                updateStatus("Playback error: ${e.message}")
            }
        }
    }

    private fun isTailscaleIp(ip: String): Boolean {
        // Extract IP from possible URL format
        val cleanIp = ip.replace("ws://", "").replace("wss://", "").split(":").first()
        return cleanIp.startsWith("100.")
    }

    private fun updateStatus(status: String) {
        Log.d(TAG, status)
        onStatusUpdate?.invoke(status)
    }

    private fun updateNotification(text: String) {
        val notification = createNotification(text)
        val notificationManager = getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager
        notificationManager.notify(NOTIFICATION_ID, notification)
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "Service destroyed")
        serviceScope.cancel()
        stopRecording()
        webSocketManager?.disconnect()
        mediaPlayer?.release()

        // Cleanup Bluetooth manager
        if (::bluetoothAudioManager.isInitialized) {
            bluetoothAudioManager.cleanup()
        }
    }

    enum class RecordingMode {
        ALWAYS_LISTENING,
        VOICE_ACTIVATED,
        PUSH_TO_TALK
    }

    // Sealed class for connection state (used by ViewModel)
    sealed class ConnectionState {
        object Disconnected : ConnectionState()
        object Connecting : ConnectionState()
        object Connected : ConnectionState()
        data class Error(val message: String) : ConnectionState()
    }

    // Conversation mode (used by ViewModel)
    enum class ConversationMode {
        PUSH_TO_TALK,
        VOICE_ACTIVATED,
        ALWAYS_LISTENING
    }

    // Methods expected by ViewModel
    fun connect(address: String) {
        val parts = address.split(":")
        val ip = parts[0]
        val port = parts.getOrNull(1)?.toIntOrNull() ?: 8765
        connectToServer(ip, port)
    }

    fun startPushToTalk() {
        startRecording(RecordingMode.PUSH_TO_TALK)
    }

    fun stopPushToTalk() {
        stopRecording()
    }

    fun toggleConversationMode() {
        val modes = ConversationMode.values()
        val currentIndex = modes.indexOf(_conversationMode.value)
        val nextIndex = (currentIndex + 1) % modes.size
        _conversationMode.value = modes[nextIndex]
    }

    fun interruptPlayback() {
        handleInterruption()
    }
}
