package com.voicebridge.audio

import android.content.Context
import android.util.Log
import org.tensorflow.lite.Interpreter
import java.io.FileInputStream
import java.nio.MappedByteBuffer
import java.nio.channels.FileChannel
import kotlin.math.abs
import kotlin.math.max

/**
 * TensorFlow Lite Voice Activity Detector.
 * Uses a TFLite model for more accurate speech detection than energy-based methods.
 * Falls back to energy-based detection if TFLite model is not available.
 *
 * Features:
 * - Model-based speech probability estimation
 * - Frame-level predictions
 * - Smoothing with hangover logic
 * - Fallback to energy-based detection
 */
class TFLiteVoiceActivityDetector(
    private val context: Context,
    private val sampleRate: Int = 16000,
    private val frameSizeMs: Int = 30,
    /**
     * Probability threshold for speech detection (0.0 - 1.0).
     * Higher values make detection less sensitive.
     */
    private val probabilityThreshold: Float = 0.5f,
    /**
     * Minimum duration of speech to trigger detection (in frames).
     * Helps filter out short noise spikes.
     */
    private val minSpeechFrames: Int = 5,
    /**
     * Number of silence frames before declaring end of speech.
     * Allows for natural pauses in speech.
     */
    private val silenceFrames: Int = 15,
    /**
     * Model filename in assets. If null, uses energy-based detection.
     */
    private val modelFile: String? = "vad.tflite"
) {
    companion object {
        private const val TAG = "TFLiteVAD"
        private const val SAMPLE_RATE_16K = 16000
        private const val SAMPLE_RATE_8K = 8000
    }

    // TFLite interpreter
    private var interpreter: Interpreter? = null
    private val isModelLoaded: Boolean
        get() = interpreter != null

    // Calculated frame size in samples
    private val frameSizeSamples = (sampleRate * frameSizeMs) / 1000

    // State tracking
    private var speechFrameCount = 0
    private var silenceFrameCount = 0
    private var isSpeaking = false
    private var noiseFloor = 0f
    private val noiseFloorAlpha = 0.95f
    private var energyThreshold = 40.0f

    // Audio buffer for frame accumulation
    private val audioBuffer = mutableListOf<Short>()

    // Input buffer for TFLite (normalized float values)
    private val inputBuffer: FloatArray by lazy {
        FloatArray(frameSizeSamples)
    }

    // Output buffer for TFLite
    private val outputBuffer: Array<FloatArray> by lazy {
        Array(1) { FloatArray(1) }
    }

    data class VADResult(
        val isSpeech: Boolean,
        val isSpeechStart: Boolean = false,
        val isSpeechEnd: Boolean = false,
        val probability: Float = 0f,
        val energy: Float = 0f
    )

    init {
        loadModel()
    }

    /**
     * Load TFLite model from assets.
     */
    private fun loadModel() {
        if (modelFile == null) {
            Log.w(TAG, "No model file specified, using energy-based detection")
            return
        }

        try {
            val model = loadModelFile(modelFile)
            val options = Interpreter.Options().apply {
                setNumThreads(2)
                setUseXNNPACK(true)
            }
            interpreter = Interpreter(model, options)
            Log.d(TAG, "TFLite VAD model loaded successfully")
        } catch (e: Exception) {
            Log.w(TAG, "Failed to load TFLite model: ${e.message}")
            Log.w(TAG, "Falling back to energy-based detection")
            interpreter = null
        }
    }

    /**
     * Load model file from assets.
     */
    private fun loadModelFile(modelFile: String): MappedByteBuffer {
        val assetFileDescriptor = context.assets.openFd(modelFile)
        val inputStream = FileInputStream(assetFileDescriptor.fileDescriptor)
        val fileChannel = inputStream.channel
        val startOffset = assetFileDescriptor.startOffset
        val declaredLength = assetFileDescriptor.declaredLength
        return fileChannel.map(FileChannel.MapMode.READ_ONLY, startOffset, declaredLength)
    }

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
        // Calculate RMS energy for fallback
        val energy = calculateEnergy(frame)
        val energyDb = 10 * kotlin.math.log10(max(energy, 1f))

        // Get speech probability from TFLite model or energy
        val speechProbability = if (isModelLoaded) {
            runInference(frame)
        } else {
            // Energy-based fallback
            val adjustedThreshold = max(energyThreshold, noiseFloor + 10)
            if (energyDb > adjustedThreshold) 0.8f else 0.2f
        }

        // Update noise floor (minimum energy when not speaking)
        if (!isSpeaking && energyDb < energyThreshold + 10) {
            noiseFloor = noiseFloorAlpha * noiseFloor + (1 - noiseFloorAlpha) * energyDb
        }

        // Detect speech based on probability
        val frameIsSpeech = speechProbability > probabilityThreshold

        var isSpeechStart = false
        var isSpeechEnd = false

        if (frameIsSpeech) {
            silenceFrameCount = 0
            speechFrameCount++

            if (!isSpeaking && speechFrameCount >= minSpeechFrames) {
                isSpeaking = true
                isSpeechStart = true
                Log.d(TAG, "Speech detected (probability: ${(speechProbability * 100).toInt()}%)")
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
            probability = speechProbability,
            energy = energyDb
        )
    }

    /**
     * Run TFLite inference on audio frame.
     */
    private fun runInference(frame: ShortArray): Float {
        return try {
            // Normalize audio samples to float range [-1.0, 1.0]
            for (i in frame.indices) {
                inputBuffer[i] = frame[i].toFloat() / Short.MAX_VALUE
            }

            // Run inference
            interpreter?.run(inputBuffer, outputBuffer)

            // Return speech probability
            outputBuffer[0][0]
        } catch (e: Exception) {
            Log.e(TAG, "Inference error: ${e.message}")
            0.5f // Neutral probability on error
        }
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
     * Update probability threshold at runtime.
     */
    fun setThreshold(threshold: Float) {
        probabilityThreshold.coerceIn(0.0f, 1.0f)
        Log.d(TAG, "VAD threshold updated to $threshold")
    }

    /**
     * Check if currently detecting speech.
     */
    fun isCurrentlySpeaking(): Boolean = isSpeaking

    /**
     * Check if TFLite model is loaded.
     */
    fun isTFLiteModelLoaded(): Boolean = isModelLoaded

    /**
     * Release resources.
     */
    fun release() {
        interpreter?.close()
        interpreter = null
        Log.d(TAG, "TFLite VAD resources released")
    }
}
