package com.voicebridge.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import kotlinx.coroutines.*
import java.nio.ByteBuffer
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * Audio player for playing synthesized voice responses.
 * Supports interruption during playback.
 */
class AudioPlayer(
    private val sampleRate: Int = 24000,  // TTS output is typically 24kHz
    private val channelConfig: Int = AudioFormat.CHANNEL_OUT_MONO,
    private val audioFormat: Int = AudioFormat.ENCODING_PCM_16BIT
) {
    companion object {
        private const val TAG = "AudioPlayer"
        private const val BUFFER_SIZE = 8192
    }

    private var audioTrack: AudioTrack? = null
    private var playbackJob: Job? = null
    private val audioQueue = ConcurrentLinkedQueue<ByteArray>()

    // State
    @Volatile
    private var isPlaying = false
    @Volatile
    private var isPaused = false

    // Callbacks
    var onPlaybackStarted: (() -> Unit)? = null
    var onPlaybackCompleted: (() -> Unit)? = null
    var onPlaybackInterrupted: (() -> Unit)? = null

    /**
     * Initialize the audio track.
     */
    fun initialize() {
        try {
            val minBufferSize = AudioTrack.getMinBufferSize(sampleRate, channelConfig, audioFormat)
            val bufferSize = maxOf(minBufferSize, BUFFER_SIZE)

            audioTrack = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setSampleRate(sampleRate)
                        .setEncoding(audioFormat)
                        .setChannelMask(channelConfig)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()

            Log.d(TAG, "Audio track initialized")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize audio track", e)
        }
    }

    /**
     * Start playback.
     */
    fun startPlayback(scope: CoroutineScope) {
        if (isPlaying) {
            Log.w(TAG, "Already playing")
            return
        }

        audioTrack?.play()
        isPlaying = true
        isPaused = false
        onPlaybackStarted?.invoke()

        playbackJob = scope.launch(Dispatchers.IO) {
            while (isActive && isPlaying) {
                if (!isPaused) {
                    val data = audioQueue.poll()
                    if (data != null) {
                        try {
                            audioTrack?.write(data, 0, data.size)
                        } catch (e: Exception) {
                            Log.e(TAG, "Error writing audio", e)
                        }
                    } else {
                        // Small delay when queue is empty
                        delay(10)
                    }
                } else {
                    delay(10)
                }
            }
        }
    }

    /**
     * Queue audio data for playback.
     */
    fun queueAudio(audioData: ByteArray) {
        audioQueue.offer(audioData)
    }

    /**
     * Queue audio from ByteBuffer.
     */
    fun queueAudio(buffer: ByteBuffer) {
        val bytes = ByteArray(buffer.remaining())
        buffer.get(bytes)
        queueAudio(bytes)
    }

    /**
     * Interrupt playback (user started speaking while playing).
     */
    fun interrupt() {
        if (isPlaying) {
            Log.d(TAG, "Playback interrupted")
            audioQueue.clear()
            audioTrack?.pause()
            audioTrack?.flush()
            isPaused = false
            onPlaybackInterrupted?.invoke()
        }
    }

    /**
     * Resume playback after interruption.
     */
    fun resume() {
        if (isPlaying) {
            isPaused = false
            audioTrack?.play()
        }
    }

    /**
     * Stop playback completely.
     */
    fun stopPlayback() {
        isPlaying = false
        playbackJob?.cancel()
        playbackJob = null

        audioQueue.clear()

        try {
            audioTrack?.pause()
            audioTrack?.flush()
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping playback", e)
        }

        Log.d(TAG, "Playback stopped")
    }

    /**
     * Release resources.
     */
    fun release() {
        stopPlayback()
        try {
            audioTrack?.release()
        } catch (e: Exception) {
            Log.e(TAG, "Error releasing audio track", e)
        }
        audioTrack = null
    }

    /**
     * Check if currently playing.
     */
    fun isPlaying(): Boolean = isPlaying

    /**
     * Check if playing and can be interrupted.
     */
    fun canBeInterrupted(): Boolean = isPlaying && !isPaused
}
