package com.voicebridge.audio

import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Audio recorder for real-time voice capture with VAD integration.
 * Uses AudioRecord for low-latency audio capture.
 */
class AudioRecorder(
    private val context: Context,
    private val sampleRate: Int = 16000,
    private val channelConfig: Int = AudioFormat.CHANNEL_IN_MONO,
    private val audioFormat: Int = AudioFormat.ENCODING_PCM_16BIT
) {
    companion object {
        private const val TAG = "AudioRecorder"
        private const val BUFFER_SIZE_FACTOR = 2
    }

    private var audioRecord: AudioRecord? = null
    private var recordingJob: Job? = null

    // State
    private val _isRecording = MutableStateFlow(false)
    val isRecording: StateFlow<Boolean> = _isRecording

    // Audio callback
    var onAudioData: ((ByteArray) -> Unit)? = null
    var onError: ((String) -> Unit)? = null

    private val bufferSize: Int by lazy {
        val minBufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)
        minBufferSize * BUFFER_SIZE_FACTOR
    }

    /**
     * Check if recording is available (permissions granted, hardware available).
     */
    fun isAvailable(): Boolean {
        return try {
            val tempRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sampleRate,
                channelConfig,
                audioFormat,
                bufferSize
            )
            val available = tempRecord.state == AudioRecord.STATE_INITIALIZED
            tempRecord.release()
            available
        } catch (e: Exception) {
            Log.e(TAG, "Audio not available", e)
            false
        }
    }

    /**
     * Start recording audio.
     * @param scope Coroutine scope for the recording loop
     * @return true if recording started successfully
     */
    fun startRecording(scope: CoroutineScope): Boolean {
        if (_isRecording.value) {
            Log.w(TAG, "Already recording")
            return true
        }

        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sampleRate,
                channelConfig,
                audioFormat,
                bufferSize
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                onError?.invoke("Failed to initialize audio recorder")
                return false
            }

            audioRecord?.startRecording()
            _isRecording.value = true

            // Start recording loop in coroutine
            recordingJob = scope.launch(Dispatchers.IO) {
                val buffer = ByteArray(bufferSize)
                while (isActive && _isRecording.value) {
                    val read = audioRecord?.read(buffer, 0, buffer.size) ?: -1
                    if (read > 0) {
                        // Copy the data (buffer gets reused)
                        val audioData = buffer.copyOf(read)
                        onAudioData?.invoke(audioData)
                    } else if (read < 0) {
                        Log.e(TAG, "Audio read error: $read")
                        onError?.invoke("Audio read error: $read")
                        break
                    }
                }
            }

            Log.d(TAG, "Recording started")
            return true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start recording", e)
            onError?.invoke("Failed to start recording: ${e.message}")
            release()
            return false
        }
    }

    /**
     * Stop recording.
     */
    fun stopRecording() {
        _isRecording.value = false
        recordingJob?.cancel()
        recordingJob = null

        try {
            audioRecord?.stop()
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping recording", e)
        }

        release()
        Log.d(TAG, "Recording stopped")
    }

    /**
     * Release audio resources.
     */
    private fun release() {
        audioRecord?.release()
        audioRecord = null
    }

    /**
     * Convert ByteArray to ShortArray for processing.
     * Assumes 16-bit PCM audio.
     */
    fun bytesToShorts(bytes: ByteArray): ShortArray {
        val shorts = ShortArray(bytes.size / 2)
        for (i in shorts.indices) {
            shorts[i] = ((bytes[i * 2].toInt() and 0xFF) or
                    (bytes[i * 2 + 1].toInt() shl 8)).toShort()
        }
        return shorts
    }

    /**
     * Convert ShortArray back to ByteArray for transmission.
     */
    fun shortsToBytes(shorts: ShortArray): ByteArray {
        val bytes = ByteArray(shorts.size * 2)
        for (i in shorts.indices) {
            bytes[i * 2] = (shorts[i].toInt() and 0xFF).toByte()
            bytes[i * 2 + 1] = ((shorts[i].toInt() shr 8) and 0xFF).toByte()
        }
        return bytes
    }
}
