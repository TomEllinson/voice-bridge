package com.voicebridge.audio

import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothHeadset
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.media.MediaRecorder
import android.os.Build
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Manages Bluetooth headset audio routing for hands-free operation.
 *
 * Features:
 * - Automatic Bluetooth headset detection
 * - Audio routing to Bluetooth SCO
 * - Connection state monitoring
 * - Fallback to built-in microphone
 */
class BluetoothAudioManager(private val context: Context) {

    companion object {
        private const val TAG = "BluetoothAudioManager"
    }

    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager

    private var bluetoothHeadset: BluetoothHeadset? = null
    private var connectedDevice: BluetoothDevice? = null

    private val _isBluetoothConnected = MutableStateFlow(false)
    val isBluetoothConnected: StateFlow<Boolean> = _isBluetoothConnected

    private val _isScoConnected = MutableStateFlow(false)
    val isScoConnected: StateFlow<Boolean> = _isScoConnected

    private val _deviceName = MutableStateFlow<String?>(null)
    val deviceName: StateFlow<String?> = _deviceName

    private val profileListener = object : BluetoothProfile.ServiceListener {
        override fun onServiceConnected(profile: Int, proxy: BluetoothProfile) {
            if (profile == BluetoothProfile.HEADSET) {
                bluetoothHeadset = proxy as BluetoothHeadset
                updateConnectedDevice()
            }
        }

        override fun onServiceDisconnected(profile: Int) {
            if (profile == BluetoothProfile.HEADSET) {
                bluetoothHeadset = null
                _isBluetoothConnected.value = false
                _isScoConnected.value = false
                _deviceName.value = null
            }
        }
    }

    private val broadcastReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                BluetoothHeadset.ACTION_CONNECTION_STATE_CHANGED -> {
                    val state = intent.getIntExtra(BluetoothProfile.EXTRA_STATE, BluetoothProfile.STATE_DISCONNECTED)
                    when (state) {
                        BluetoothProfile.STATE_CONNECTED -> {
                            Log.d(TAG, "Bluetooth headset connected")
                            updateConnectedDevice()
                        }
                        BluetoothProfile.STATE_DISCONNECTED -> {
                            Log.d(TAG, "Bluetooth headset disconnected")
                            _isBluetoothConnected.value = false
                            _isScoConnected.value = false
                            _deviceName.value = null
                            connectedDevice = null
                        }
                    }
                }
                AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED -> {
                    val state = intent.getIntExtra(AudioManager.EXTRA_SCO_AUDIO_STATE, AudioManager.SCO_AUDIO_STATE_DISCONNECTED)
                    when (state) {
                        AudioManager.SCO_AUDIO_STATE_CONNECTED -> {
                            Log.d(TAG, "SCO audio connected")
                            _isScoConnected.value = true
                        }
                        AudioManager.SCO_AUDIO_STATE_DISCONNECTED -> {
                            Log.d(TAG, "SCO audio disconnected")
                            _isScoConnected.value = false
                        }
                        AudioManager.SCO_AUDIO_STATE_CONNECTING -> {
                            Log.d(TAG, "SCO audio connecting...")
                        }
                    }
                }
            }
        }
    }

    fun initialize() {
        // Get BluetoothHeadset proxy
        bluetoothManager?.adapter?.getProfileProxy(context, profileListener, BluetoothProfile.HEADSET)

        // Register broadcast receiver
        val filter = IntentFilter().apply {
            addAction(BluetoothHeadset.ACTION_CONNECTION_STATE_CHANGED)
            addAction(AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED)
        }
        context.registerReceiver(broadcastReceiver, filter)

        // Check initial state
        checkBluetoothState()
    }

    fun cleanup() {
        stopScoAudio()
        try {
            context.unregisterReceiver(broadcastReceiver)
        } catch (e: IllegalArgumentException) {
            // Receiver not registered
        }
        bluetoothHeadset?.let {
            bluetoothManager?.adapter?.closeProfileProxy(BluetoothProfile.HEADSET, it)
        }
    }

    /**
     * Start SCO audio connection for Bluetooth headset microphone.
     * This must be called before starting audio recording.
     */
    fun startScoAudio(): Boolean {
        if (!_isBluetoothConnected.value) {
            Log.w(TAG, "Cannot start SCO: No Bluetooth headset connected")
            return false
        }

        if (_isScoConnected.value) {
            Log.d(TAG, "SCO already connected")
            return true
        }

        // Stop any media playback to free audio focus
        audioManager.stopBluetoothSco()
        audioManager.isBluetoothScoOn = false

        // Request SCO connection
        audioManager.startBluetoothSco()
        audioManager.isBluetoothScoOn = true

        Log.d(TAG, "Started Bluetooth SCO")
        return true
    }

    /**
     * Stop SCO audio connection.
     */
    fun stopScoAudio() {
        if (audioManager.isBluetoothScoOn) {
            audioManager.isBluetoothScoOn = false
            audioManager.stopBluetoothSco()
            Log.d(TAG, "Stopped Bluetooth SCO")
        }
    }

    /**
     * Get the best audio source for recording.
     * Returns REMOTE_SUBMIX if Bluetooth SCO is active, otherwise MIC.
     */
    fun getAudioSource(): Int {
        return if (_isScoConnected.value && _isBluetoothConnected.value) {
            // Use built-in mic but audio is routed through BT
            MediaRecorder.AudioSource.MIC
        } else {
            MediaRecorder.AudioSource.MIC
        }
    }

    /**
     * Check if a Bluetooth headset is available and preferred.
     */
    fun isBluetoothPreferred(): Boolean {
        return _isBluetoothConnected.value && _isScoConnected.value
    }

    /**
     * Force audio routing to Bluetooth headset.
     */
    fun routeToBluetooth(): Boolean {
        if (!_isBluetoothConnected.value) {
            return false
        }

        // Start SCO if not already connected
        if (!_isScoConnected.value) {
            return startScoAudio()
        }

        return true
    }

    /**
     * Route audio to speakerphone (for when BT is not available).
     */
    fun routeToSpeaker() {
        stopScoAudio()
        audioManager.isSpeakerphoneOn = true
        Log.d(TAG, "Audio routed to speakerphone")
    }

    private fun checkBluetoothState() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            // Check connected audio devices
            val devices = audioManager.getDevices(AudioManager.GET_DEVICES_OUTPUTS)
            val hasBtDevice = devices.any { device ->
                device.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                device.type == AudioDeviceInfo.TYPE_BLUETOOTH_A2DP
            }

            if (hasBtDevice) {
                updateConnectedDevice()
            }
        }
    }

    private fun updateConnectedDevice() {
        bluetoothHeadset?.let { headset ->
            val devices = headset.connectedDevices
            if (devices.isNotEmpty()) {
                connectedDevice = devices[0]
                _isBluetoothConnected.value = true
                _deviceName.value = connectedDevice?.name ?: "Bluetooth Headset"
                Log.d(TAG, "Connected to: ${_deviceName.value}")
            }
        }
    }

    /**
     * Get a list of connected Bluetooth audio devices.
     */
    fun getConnectedDevices(): List<String> {
        return bluetoothHeadset?.connectedDevices?.map { it.name ?: "Unknown Device" } ?: emptyList()
    }
}
