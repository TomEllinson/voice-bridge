package com.voicebridge.audio

import android.util.Log
import kotlin.math.abs
import kotlin.math.max

/**
 * Voice Activity Detection using energy-based thresholding.
 * Optimized for real-time streaming on Android devices.
 *
 * This implementation uses RMS energy calculation with adaptive thresholding
 * to detect speech vs silence. It's lightweight and efficient for mobile use.
 */
class VoiceActivityDetector(
    private val sampleRate: Int = 16000,
    private val frameSizeMs: Int = 30,
    /**
     * Energy threshold for speech detection (in dB).
     * Higher values make detection less sensitive.
     */
    private var energyThreshold: Float = 40.0f,
    /**
     * Minimum duration of speech to trigger detection (in frames).
     * Helps filter out short noise spikes.
     */
    private val minSpeechFrames: Int = 5,
    /**
     * Number of silence frames before declaring end of speech.
     * Allows for natural pauses in speech.
     */
    private val silenceFrames: Int = 15
) {
    companion object {
        private const val TAG = "VoiceActivityDetector"
    }

    // Calculated frame size in samples
    private val frameSizeSamples = (sampleRate * frameSizeMs) / 1000

    // State tracking
    private var speechFrameCount = 0
    private var silenceFrameCount = 0
    private var isSpeaking = false
    private var noiseFloor = 0f
    private val noiseFloorAlpha = 0.95f

    // Audio buffer for frame accumulation
    private val audioBuffer = mutableListOf<Short>()

    data class VADResult(
        val isSpeech: Boolean,
        val isSpeechStart: Boolean = false,
        val isSpeechEnd: Boolean = false,
        val energy: Float = 0f
    )

    /**
     * Process audio samples and return VAD detection result.
     * @param audioData 16-bit PCM audio samples
     * @return VADResult indicating speech detection state
     */
    fun process(audioData: ShortArray): VADResult {
        audioBuffer.addAll(audioData.toList())

        // Process complete frames
        val results = mutableListOf<VADResult>()
        while (audioBuffer.size >= frameSizeSamples) {
            val frame = audioBuffer.take(frameSizeSamples).toShortArray()
            repeat(frameSizeSamples) { audioBuffer.removeAt(0) }
            results.add(processFrame(frame))
        }

        // Return the most significant result
        return results.lastOrNull() ?: VADResult(isSpeech = false)
    }

    /**
     * Process a single frame of audio.
     */
    private fun processFrame(frame: ShortArray): VADResult {
        // Calculate RMS energy
        val energy = calculateEnergy(frame)
        val energyDb = 10 * kotlin.math.log10(max(energy, 1f))

        // Update noise floor (minimum energy when not speaking)
        if (!isSpeaking && energyDb < energyThreshold + 10) {
            noiseFloor = noiseFloorAlpha * noiseFloor + (1 - noiseFloorAlpha) * energyDb
        }

        // Detect speech based on energy above threshold and noise floor
        val adjustedThreshold = max(energyThreshold, noiseFloor + 10)
        val frameIsSpeech = energyDb > adjustedThreshold

        var isSpeechStart = false
        var isSpeechEnd = false

        if (frameIsSpeech) {
            silenceFrameCount = 0
            speechFrameCount++

            if (!isSpeaking && speechFrameCount >= minSpeechFrames) {
                isSpeaking = true
                isSpeechStart = true
                Log.d(TAG, "Speech detected (energy: ${energyDb.toInt()} dB)")
            }
        } else {
            speechFrameCount = 0
            silenceFrameCount++

            if (isSpeaking && silenceFrameCount >= silenceFrames) {
                isSpeaking = false
                isSpeechEnd = true
                Log.d(TAG, "Speech ended (silence frames: $silenceFrames)")
            }
        }

        return VADResult(
            isSpeech = isSpeaking,
            isSpeechStart = isSpeechStart,
            isSpeechEnd = isSpeechEnd,
            energy = energyDb
        )
    }

    /**
     * Calculate RMS energy of audio frame.
     */
    private fun calculateEnergy(frame: ShortArray): Float {
        var sum = 0L
        for (sample in frame) {
            sum += sample.toLong() * sample.toLong()
        }
        return sum.toFloat() / (frame.size * frame.size)
    }

    /**
     * Reset detector state.
     */
    fun reset() {
        speechFrameCount = 0
        silenceFrameCount = 0
        isSpeaking = false
        audioBuffer.clear()
        Log.d(TAG, "VAD reset")
    }

    /**
     * Update energy threshold at runtime.
     */
    fun setThreshold(threshold: Float) {
        energyThreshold = threshold
        Log.d(TAG, "VAD threshold updated to $threshold")
    }

    /**
     * Check if currently detecting speech.
     */
    fun isCurrentlySpeaking(): Boolean = isSpeaking
}
