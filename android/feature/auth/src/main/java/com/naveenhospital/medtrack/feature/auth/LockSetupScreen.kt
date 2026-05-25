package com.naveenhospital.medtrack.feature.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Fingerprint
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackIconBadge

@Composable
fun LockSetupScreen(
    biometricEnabled: Boolean,
    biometricAvailable: Boolean,
    biometricMessage: String?,
    onSavePattern: (List<Int>) -> Unit,
    onEnableBiometric: () -> Unit,
    onContinue: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var pattern by rememberSaveable { mutableStateOf(emptyList<Int>()) }
    var message by rememberSaveable { mutableStateOf<String?>(null) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(MedtrackColors.PrimaryDark, MedtrackColors.Primary, MedtrackColors.Surface),
                ),
            )
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Secure unlock", color = Color.White, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text("Protect the mobile worklist on this device.", color = Color.White.copy(alpha = 0.82f), style = MaterialTheme.typography.bodySmall)

        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(26.dp),
            color = MedtrackColors.Card,
            shadowElevation = 12.dp,
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(text = "Set pattern", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = MedtrackColors.Ink)
                Text(text = "Choose at least 4 dots.", color = MedtrackColors.Muted)
                PatternLockView(
                    selectedDots = pattern,
                    onDotSelected = { dot -> pattern = pattern + dot },
                    modifier = Modifier.fillMaxWidth(),
                )
                if (message != null) {
                    Text(text = message.orEmpty(), color = MedtrackColors.Success)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    OutlinedButton(onClick = { pattern = emptyList() }, modifier = Modifier.weight(1f).height(46.dp)) {
                        Text("Reset")
                    }
                    Button(
                        onClick = {
                            onSavePattern(pattern)
                            message = "Pattern saved"
                        },
                        modifier = Modifier.weight(1f).height(46.dp),
                        enabled = pattern.size >= 4,
                        colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Ink),
                    ) {
                        Text("Save")
                    }
                }
            }
        }

        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(22.dp),
            color = MedtrackColors.Card,
            shadowElevation = 6.dp,
        ) {
            Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    MedtrackIconBadge(icon = Icons.Outlined.Fingerprint, tint = MedtrackColors.Primary)
                    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(text = "Biometric", fontWeight = FontWeight.Bold, color = MedtrackColors.Ink)
                        Text(
                            text = biometricMessage ?: if (biometricEnabled) {
                                "Biometric unlock is enabled."
                            } else if (biometricAvailable) {
                                "Use device biometric unlock when available."
                            } else {
                                "Biometric unlock is not available on this device."
                            },
                            color = MedtrackColors.Muted,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
                Button(
                    onClick = onEnableBiometric,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !biometricEnabled && biometricAvailable,
                    colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Primary),
                ) {
                    Text(if (biometricEnabled) "Enabled" else "Enable biometric")
                }
            }
        }

        Button(
            onClick = onContinue,
            modifier = Modifier
                .fillMaxWidth()
                .height(50.dp),
            enabled = biometricEnabled || message == "Pattern saved",
            colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Ink),
        ) {
            Text("Continue")
        }
    }
}
