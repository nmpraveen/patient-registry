package com.naveenhospital.medtrack.feature.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Fingerprint
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import kotlinx.coroutines.launch

@Composable
fun UnlockScreen(
    patternEnabled: Boolean,
    biometricEnabled: Boolean,
    biometricAvailable: Boolean,
    biometricMessage: String?,
    onPatternUnlock: suspend (List<Int>) -> String?,
    onBiometricUnlock: () -> Unit,
    onUsePasswordLogin: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var pattern by rememberSaveable { mutableStateOf(emptyList<Int>()) }
    var isLoading by rememberSaveable { mutableStateOf(false) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(MedtrackColors.PrimaryDark, MedtrackColors.Primary, MedtrackColors.Surface),
                ),
            )
            .padding(16.dp),
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.TopCenter)
                .padding(top = 58.dp),
            shape = RoundedCornerShape(28.dp),
            color = MedtrackColors.Card,
            shadowElevation = 14.dp,
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Surface(shape = RoundedCornerShape(18.dp), color = MedtrackColors.PrimarySoft) {
                    Icon(
                        imageVector = Icons.Outlined.Lock,
                        contentDescription = null,
                        tint = MedtrackColors.Primary,
                        modifier = Modifier.padding(14.dp),
                    )
                }
                Text(text = "MEDTRACK locked", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = MedtrackColors.Ink)
                Text(text = "Use your saved device unlock.", color = MedtrackColors.Muted, style = MaterialTheme.typography.bodySmall)
                if (error != null) {
                    Text(text = error.orEmpty(), color = MedtrackColors.Danger)
                }

                if (patternEnabled) {
                    Text(text = "Pattern", fontWeight = FontWeight.Bold, color = MedtrackColors.Ink)
                    PatternLockView(
                        selectedDots = pattern,
                        onDotSelected = { dot -> pattern = pattern + dot },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                        OutlinedButton(onClick = { pattern = emptyList() }, modifier = Modifier.weight(1f).height(46.dp)) {
                            Text("Reset")
                        }
                        Button(
                            onClick = {
                                scope.launch {
                                    isLoading = true
                                    error = null
                                    runCatching { onPatternUnlock(pattern) }
                                        .onSuccess { failureMessage ->
                                            if (!failureMessage.isNullOrBlank()) {
                                                error = failureMessage
                                            } else {
                                                pattern = emptyList()
                                            }
                                        }
                                        .onFailure { error = it.message ?: "Unlock failed" }
                                    isLoading = false
                                }
                            },
                            modifier = Modifier.weight(1f).height(46.dp),
                            enabled = pattern.isNotEmpty() && !isLoading,
                            colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Ink),
                        ) {
                            if (isLoading) {
                                CircularProgressIndicator(color = Color.White)
                            } else {
                                Text("Unlock")
                            }
                        }
                    }
                }

                if (biometricEnabled) {
                    if (!biometricMessage.isNullOrBlank()) {
                        Text(text = biometricMessage, color = MedtrackColors.Muted, style = MaterialTheme.typography.bodySmall)
                    }
                    Button(
                        onClick = onBiometricUnlock,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(50.dp),
                        enabled = biometricAvailable,
                        colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Primary),
                    ) {
                        Icon(imageVector = Icons.Outlined.Fingerprint, contentDescription = null)
                        Text("Use biometric")
                    }
                }

                OutlinedButton(
                    onClick = onUsePasswordLogin,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(50.dp),
                ) {
                    Text("Use password login")
                }
            }
        }
    }
}
