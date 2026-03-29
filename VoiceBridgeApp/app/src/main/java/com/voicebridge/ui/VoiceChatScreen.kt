package com.voicebridge.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.voicebridge.service.VoiceBridgeService

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VoiceChatScreen(
    service: () -> VoiceBridgeService?,
    isServiceBound: () -> Boolean
) {
    var serverIp by remember { mutableStateOf("100.64.1.1") }
    var port by remember { mutableStateOf("8765") }
    var isConnected by remember { mutableStateOf(false) }
    var isRecording by remember { mutableStateOf(false) }
    var listeningMode by remember { mutableStateOf(VoiceBridgeService.RecordingMode.ALWAYS_LISTENING) }
    var statusText by remember { mutableStateOf("Ready to connect") }
    var logMessages by remember { mutableStateOf(listOf<String>()) }

    val scrollState = rememberScrollState()

    // Set up status callback
    LaunchedEffect(isServiceBound()) {
        service()?.let { svc ->
            svc.onStatusUpdate = { status ->
                statusText = status
                logMessages = logMessages + status
            }
            svc.onConnectionStateChange = { connected ->
                isConnected = connected
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Voice Bridge") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                    titleContentColor = MaterialTheme.colorScheme.onPrimaryContainer
                )
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp)
        ) {
            // Connection status card
            ConnectionStatusCard(
                isConnected = isConnected,
                statusText = statusText
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Server connection settings
            ServerConnectionSection(
                serverIp = serverIp,
                onServerIpChange = { serverIp = it },
                port = port,
                onPortChange = { port = it },
                isConnected = isConnected,
                onConnect = {
                    service()?.connectToServer(serverIp, port.toIntOrNull() ?: 8765)
                },
                onDisconnect = {
                    service()?.disconnect()
                }
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Listening mode selector
            ListeningModeSelector(
                currentMode = listeningMode,
                onModeChange = { mode ->
                    listeningMode = mode
                    service()?.setListeningMode(mode)
                }
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Recording controls
            RecordingControls(
                isRecording = isRecording,
                currentMode = listeningMode,
                onStartRecording = {
                    isRecording = true
                    service()?.startRecording(listeningMode)
                },
                onStopRecording = {
                    isRecording = false
                    service()?.stopRecording()
                }
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Log output
            Text(
                text = "Log",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(scrollState)
                        .padding(8.dp)
                ) {
                    logMessages.takeLast(50).forEach { message ->
                        Text(
                            text = message,
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.padding(vertical = 2.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun ConnectionStatusCard(
    isConnected: Boolean,
    statusText: String
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (isConnected)
                MaterialTheme.colorScheme.primaryContainer
            else
                MaterialTheme.colorScheme.errorContainer
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = if (isConnected) Icons.Default.CheckCircle else Icons.Default.Error,
                contentDescription = null,
                tint = if (isConnected)
                    MaterialTheme.colorScheme.onPrimaryContainer
                else
                    MaterialTheme.colorScheme.onErrorContainer
            )

            Spacer(modifier = Modifier.width(12.dp))

            Column {
                Text(
                    text = if (isConnected) "Connected" else "Disconnected",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = if (isConnected)
                        MaterialTheme.colorScheme.onPrimaryContainer
                    else
                        MaterialTheme.colorScheme.onErrorContainer
                )
                Text(
                    text = statusText,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (isConnected)
                        MaterialTheme.colorScheme.onPrimaryContainer
                    else
                        MaterialTheme.colorScheme.onErrorContainer
                )
            }
        }
    }
}

@Composable
fun ServerConnectionSection(
    serverIp: String,
    onServerIpChange: (String) -> Unit,
    port: String,
    onPortChange: (String) -> Unit,
    isConnected: Boolean,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = "Server Settings",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(
                    value = serverIp,
                    onValueChange = onServerIpChange,
                    label = { Text("Tailscale IP") },
                    placeholder = { Text("100.64.1.1") },
                    modifier = Modifier.weight(2f),
                    enabled = !isConnected,
                    singleLine = true
                )

                OutlinedTextField(
                    value = port,
                    onValueChange = onPortChange,
                    label = { Text("Port") },
                    modifier = Modifier.weight(1f),
                    enabled = !isConnected,
                    singleLine = true
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            Button(
                onClick = if (isConnected) onDisconnect else onConnect,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isConnected)
                        MaterialTheme.colorScheme.error
                    else
                        MaterialTheme.colorScheme.primary
                )
            ) {
                Icon(
                    imageVector = if (isConnected) Icons.Default.Close else Icons.Default.PlayArrow,
                    contentDescription = null
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(if (isConnected) "Disconnect" else "Connect")
            }
        }
    }
}

@Composable
fun ListeningModeSelector(
    currentMode: VoiceBridgeService.RecordingMode,
    onModeChange: (VoiceBridgeService.RecordingMode) -> Unit
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = "Listening Mode",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )

            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                ModeButton(
                    icon = Icons.Default.Mic,
                    label = "Always",
                    isSelected = currentMode == VoiceBridgeService.RecordingMode.ALWAYS_LISTENING,
                    onClick = { onModeChange(VoiceBridgeService.RecordingMode.ALWAYS_LISTENING) },
                    modifier = Modifier.weight(1f)
                )

                ModeButton(
                    icon = Icons.Default.RecordVoiceOver,
                    label = "Voice Act.",
                    isSelected = currentMode == VoiceBridgeService.RecordingMode.VOICE_ACTIVATED,
                    onClick = { onModeChange(VoiceBridgeService.RecordingMode.VOICE_ACTIVATED) },
                    modifier = Modifier.weight(1f)
                )

                ModeButton(
                    icon = Icons.Default.TouchApp,
                    label = "Push to Talk",
                    isSelected = currentMode == VoiceBridgeService.RecordingMode.PUSH_TO_TALK,
                    onClick = { onModeChange(VoiceBridgeService.RecordingMode.PUSH_TO_TALK) },
                    modifier = Modifier.weight(1f)
                )
            }
        }
    }
}

@Composable
fun ModeButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    isSelected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .background(
                color = if (isSelected)
                    MaterialTheme.colorScheme.primaryContainer
                else
                    MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(8.dp)
            )
            .padding(8.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        IconButton(onClick = onClick) {
            Icon(
                imageVector = icon,
                contentDescription = label,
                tint = if (isSelected)
                    MaterialTheme.colorScheme.onPrimaryContainer
                else
                    MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = if (isSelected)
                MaterialTheme.colorScheme.onPrimaryContainer
            else
                MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
fun RecordingControls(
    isRecording: Boolean,
    currentMode: VoiceBridgeService.RecordingMode,
    onStartRecording: () -> Unit,
    onStopRecording: () -> Unit
) {
    val isPushToTalk = currentMode == VoiceBridgeService.RecordingMode.PUSH_TO_TALK

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            if (isPushToTalk) {
                // Push to talk button with press detection
                var isPressed by remember { mutableStateOf(false) }

                Button(
                    onClick = {},
                    modifier = Modifier
                        .size(120.dp)
                        .pointerInput(Unit) {
                            detectTapGestures(
                                onPress = {
                                    isPressed = true
                                    if (!isRecording) onStartRecording()
                                    tryAwaitRelease()
                                    isPressed = false
                                    if (isRecording) onStopRecording()
                                }
                            )
                        },
                    shape = RoundedCornerShape(60.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isRecording || isPressed)
                            MaterialTheme.colorScheme.error
                        else
                            MaterialTheme.colorScheme.primary
                    )
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            imageVector = if (isRecording)
                                Icons.Default.Stop
                            else
                                Icons.Default.Mic,
                            contentDescription = null,
                            modifier = Modifier.size(40.dp)
                        )
                        Text(
                            if (isRecording) "Recording..." else "Hold to Talk",
                            fontSize = 12.sp
                        )
                    }
                }
            } else {
                // Toggle button for always-listening and voice-activated modes
                Button(
                    onClick = if (isRecording) onStopRecording else onStartRecording,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(80.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isRecording)
                            MaterialTheme.colorScheme.error
                        else
                            MaterialTheme.colorScheme.primary
                    )
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = if (isRecording)
                                Icons.Default.Stop
                            else
                                Icons.Default.Mic,
                            contentDescription = null,
                            modifier = Modifier.size(32.dp)
                        )
                        Spacer(modifier = Modifier.width(12.dp))
                        Text(
                            text = if (isRecording) "Stop Listening" else "Start Listening",
                            fontSize = 20.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }

            if (isRecording) {
                Spacer(modifier = Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(12.dp)
                            .background(Color.Red, RoundedCornerShape(6.dp))
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "Recording...",
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
        }
    }
}
